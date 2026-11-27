import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect, useState } from "react";
import { flushSync } from "react-dom";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import { InsightTabs, type InsightGroup } from "./InsightTabs";

function tabs(groups: InsightGroup[]) {
  return render(
    <MantineProvider>
      <InsightTabs groups={groups} data-testid="insights" />
    </MantineProvider>,
  );
}

const group = (key: string, label: string, ...texts: string[]): InsightGroup => ({
  key,
  label,
  node: <>{texts.map((t) => <div key={t}>{t}</div>)}</>,
});

/** A group whose cards all have nothing to say — the shape most of this app's
 *  analysis cards take when they have no data (they fetch it themselves and
 *  return null). */
const silent = (key: string, label: string): InsightGroup => ({
  key, label, node: null,
});

/** A card that only appears after an async settle, like one whose query resolves
 *  a tick after mount. The parent does not re-render for this. */
function LateCard({ text }: { text: string }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setReady(true), 150);
    return () => clearTimeout(t);
  }, []);
  return ready ? <div>{text}</div> : null;
}

describe("InsightTabs", () => {
  it("never paints a tab for a silent group, not even on the first frame", () => {
    // The pre-measurement fallback offers every group a tab. Measuring in a
    // passive effect left that fallback on screen for a frame — a "Newest | Best"
    // strip flashing over a Dashboard with nothing to rank, and the race that
    // reddened main's frontend CI (Dashboard.test "gives no tab to a group whose
    // cards have nothing to say"). Render outside act(): `flushSync` commits and
    // runs layout effects (and the sync update they schedule) but not a passive
    // effect's update, so the DOM here is what the browser would first paint.
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    const g = globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean };
    const was = g.IS_REACT_ACT_ENVIRONMENT;
    g.IS_REACT_ACT_ENVIRONMENT = false;
    try {
      flushSync(() => root.render(
        <MantineProvider>
          <InsightTabs groups={[group("newest", "Newest", "M31"), silent("best", "Best")]} />
        </MantineProvider>,
      ));
      expect(host.querySelectorAll('[role="tab"]')).toHaveLength(0);
      expect(host).toHaveTextContent("M31");
    } finally {
      flushSync(() => root.unmount());
      g.IS_REACT_ACT_ENVIRONMENT = was;
      host.remove();
    }
  });

  it("shows one group at a time instead of stacking them all", async () => {
    tabs([
      group("overview", "Overview", "Last night's session"),
      group("quality", "Quality", "Focus trend", "Transparency"),
      group("planning", "Planning", "Your next window"),
    ]);

    await waitFor(() => expect(screen.getByText("Last night's session")).toBeVisible());
    // The other groups are mounted (so nothing refetches on a switch) but out of
    // the way — the whole point of the slice.
    expect(screen.getByText("Focus trend")).not.toBeVisible();
    expect(screen.getByText("Your next window")).not.toBeVisible();
    expect(screen.getAllByRole("tab")).toHaveLength(3);
  });

  it("switches group in one click, and everything stays mounted", async () => {
    tabs([
      group("overview", "Overview", "Last night's session"),
      group("quality", "Quality", "Focus trend"),
    ]);

    await waitFor(() => expect(screen.getByText("Last night's session")).toBeVisible());
    fireEvent.click(screen.getByRole("tab", { name: "Quality" }));

    await waitFor(() => expect(screen.getByText("Focus trend")).toBeVisible());
    expect(screen.getByText("Last night's session")).not.toBeVisible();
  });

  it("gives no tab to a group whose cards have nothing to say", async () => {
    tabs([
      group("overview", "Overview", "Last night's session"),
      silent("quality", "Quality"),
      group("planning", "Planning", "Your next window"),
    ]);

    await waitFor(() => expect(screen.getAllByRole("tab")).toHaveLength(2));
    expect(screen.queryByRole("tab", { name: "Quality" })).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Planning" })).toBeInTheDocument();
  });

  it("drops the tab strip entirely when only one group has anything", async () => {
    tabs([
      group("overview", "Overview", "Last night's session"),
      silent("quality", "Quality"),
    ]);

    await waitFor(() => expect(screen.getByText("Last night's session")).toBeVisible());
    // One tab is not a choice — it's a label taking up space.
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
  });

  it("renders nothing at all when no group has anything to say", async () => {
    tabs([silent("overview", "Overview"), silent("quality", "Quality")]);

    await waitFor(() =>
      expect(screen.getByTestId("insights")).not.toBeVisible());
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
  });

  it("gives a late-arriving card its tab back", async () => {
    tabs([
      group("overview", "Overview", "Last night's session"),
      { key: "quality", label: "Quality", node: <LateCard text="Focus trend" /> },
    ]);

    // Its query hasn't resolved yet, so only one group is speaking and there is
    // no tab strip at all...
    await waitFor(() =>
      expect(screen.queryByRole("tab", { name: "Quality" })).not.toBeInTheDocument());
    // ...and once it speaks, the observer picks it up without a parent re-render.
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Quality" })).toBeInTheDocument());
    expect(screen.getAllByRole("tab")).toHaveLength(2);
    expect(screen.getByText("Focus trend")).toBeInTheDocument();
  });

  it("keeps the chosen tab open across a re-render", async () => {
    const { rerender } = tabs([
      group("overview", "Overview", "Last night's session"),
      group("quality", "Quality", "Focus trend"),
    ]);

    fireEvent.click(await screen.findByRole("tab", { name: "Quality" }));
    await waitFor(() => expect(screen.getByText("Focus trend")).toBeVisible());

    rerender(
      <MantineProvider>
        <InsightTabs
          groups={[
            group("overview", "Overview", "Last night's session"),
            group("quality", "Quality", "Focus trend", "Transparency"),
          ]}
          data-testid="insights"
        />
      </MantineProvider>,
    );

    expect(screen.getByText("Focus trend")).toBeVisible();
    expect(screen.getByText("Last night's session")).not.toBeVisible();
  });
});

describe("lazy groups (audit 2026-11-26: Planning fetched 11 s of data on every open)", () => {
  it("does not render a lazy group's cards until its tab is opened, but offers the tab", async () => {
    let mounted = 0;
    function Costly() {
      mounted += 1;
      return <p>Your next window</p>;
    }
    render(
      <MantineProvider>
        <InsightTabs groups={[
          { key: "overview", label: "Overview", node: <p>Hello</p> },
          { key: "planning", label: "Planning", node: <Costly />, lazy: true,
            lazyEmpty: <p>Nothing to plan</p> },
        ]} />
      </MantineProvider>,
    );
    expect(await screen.findByRole("tab", { name: "Planning" })).toBeInTheDocument();
    expect(mounted).toBe(0);
    fireEvent.click(screen.getByRole("tab", { name: "Planning" }));
    expect(await screen.findByText("Your next window")).toBeInTheDocument();
    expect(mounted).toBeGreaterThan(0);
  });

  it("says so when an opened lazy group has nothing", async () => {
    render(
      <MantineProvider>
        <InsightTabs groups={[
          { key: "overview", label: "Overview", node: <p>Hello</p> },
          { key: "planning", label: "Planning", node: null, lazy: true,
            lazyEmpty: <p>Nothing to plan</p> },
        ]} />
      </MantineProvider>,
    );
    fireEvent.click(await screen.findByRole("tab", { name: "Planning" }));
    expect(await screen.findByText("Nothing to plan")).toBeInTheDocument();
  });
});
