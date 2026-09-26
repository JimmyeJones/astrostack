import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { CompareWithLastCard } from "./CompareWithLastCard";
import type { StackRun } from "../api/client";

function run(id: number, over: Partial<StackRun> = {}): StackRun {
  return {
    id,
    timestamp_utc: "2026-05-02T00:00:00Z",
    n_frames_used: 100,
    canvas_w: 1000,
    canvas_h: 800,
    has_preview: true,
    has_fits: true,
    has_tiff: false,
    ...over,
  } as StackRun;
}

// The card now carries the matched-crop strip, which asks the backend whether
// there is an honest patch to show — so the tree needs a query client. The strip
// itself fetches nothing until its button is pressed (see NoiseDeltaStrip), so
// these tests still exercise the card without any network stubbing.
function renderCard(runs?: StackRun[] | null) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <CompareWithLastCard safe="M_42" runs={runs} />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

describe("CompareWithLastCard", () => {
  it("renders nothing at all until there are two pictures to compare", () => {
    const { container } = renderCard([run(9)]);
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
    expect(screen.queryByTestId("compare-with-last")).toBeNull();
    // …which is what keeps the Story tab itself hidden (InsightTabs measures DOM).
    renderCard(undefined);
    expect(screen.queryByTestId("compare-with-last")).toBeNull();
  });

  it("links the newest picture against the one before it", () => {
    renderCard([run(9), run(7), run(3)]);
    const link = screen.getByRole("link", { name: /Compare with my last one/ });
    expect(link).toHaveAttribute("href", "/compare?a=M_42:9&b=M_42:7");
  });

  it("names the two nights by when the subs were SHOT, not when the stack ran", () => {
    // A re-stack of a back catalogue runs years after the capture; dating the
    // sides by `timestamp_utc` would say they were both taken today.
    renderCard([
      run(9, {
        capture_night_start: "2024-11-18T20:00:00Z",
        capture_night_end: "2024-11-18T23:00:00Z",
        capture_nights: 1,
      }),
      run(7, {
        capture_night_start: "2024-11-15T20:00:00Z",
        capture_night_end: "2024-11-15T23:00:00Z",
        capture_nights: 1,
      }),
    ]);
    expect(screen.getByTestId("compare-with-last")).toHaveTextContent(/2024/);
    expect(screen.getByTestId("compare-with-last")).not.toHaveTextContent(/2026/);
  });

  it("still offers the link when neither run carries a usable date", () => {
    renderCard([run(9), run(7)]);
    expect(screen.getByRole("link", { name: /Compare with my last one/ }))
      .toHaveAttribute("href", "/compare?a=M_42:9&b=M_42:7");
  });

  it("offers 'How far you've come' — the first picture, not the previous one", () => {
    renderCard([run(9), run(7), run(3)]);
    const link = screen.getByRole("link", { name: /How far you.ve come/ });
    // `a` is the newest on BOTH links, so the two comparisons read the same way
    // round across the divider.
    expect(link).toHaveAttribute("href", "/compare?a=M_42:9&b=M_42:3");
    expect(screen.getByTestId("first-vs-now-hint")).toBeInTheDocument();
  });

  it("offers only ONE button on a two-picture target, where both links would be the same URL", () => {
    renderCard([run(9), run(7)]);
    expect(screen.getByRole("link", { name: /Compare with my last one/ }))
      .toHaveAttribute("href", "/compare?a=M_42:9&b=M_42:7");
    expect(screen.queryByTestId("first-vs-now")).toBeNull();
    expect(screen.queryByTestId("first-vs-now-hint")).toBeNull();
  });

  it("counts only comparable runs when deciding the two are the same pair", () => {
    // Three rows, but the oldest has no picture — so the first comparable one IS
    // the previous one and the second button must still stand down.
    renderCard([run(9), run(7), run(3, { has_preview: false })]);
    expect(screen.queryByTestId("first-vs-now")).toBeNull();
  });

  it("dates the first picture by when its subs were shot", () => {
    renderCard([
      run(9, { capture_night_start: "2026-05-01" }),
      run(7, { capture_night_start: "2026-04-01" }),
      run(3, { capture_night_start: "2025-09-14", timestamp_utc: "2026-05-02T00:00:00Z" }),
    ]);
    expect(screen.getByTestId("first-vs-now-hint").textContent)
      .toMatch(/14 Sep 2025/);
  });

  it("offers the matched-crop picture, and asks for nothing until it is wanted", () => {
    // The strip is the picture half of the same question. It must be *offered*
    // whenever the links are (a pair exists), and must not fetch on render: the
    // two crops cost a pass over both masters to place, and this card sits on a
    // page the owner opens constantly.
    renderCard([run(9), run(7)]);
    expect(screen.getByTestId("noise-delta-show")).toBeInTheDocument();
    expect(screen.queryByTestId("noise-delta-strip")).toBeNull();
  });

  it("offers no picture when there is no pair to compare", () => {
    renderCard([run(9)]);
    expect(screen.queryByTestId("noise-delta-show")).toBeNull();
  });
});
