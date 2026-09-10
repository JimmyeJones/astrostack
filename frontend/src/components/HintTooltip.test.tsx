import { Badge, MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HintTooltip } from "./HintTooltip";

const HINT = "Shot through haze — median transparency well below this target's clearest nights.";

function renderBadge(props: Partial<Parameters<typeof HintTooltip>[0]> = {}) {
  return render(
    <MantineProvider>
      <HintTooltip label={HINT} multiline w={260} {...props}>
        <Badge>Hazy night</Badge>
      </HintTooltip>
    </MantineProvider>,
  );
}

describe("HintTooltip — a badge's explanation has to be reachable without a mouse", () => {
  it("shows the sentence on a tap, which is the only gesture a phone has", async () => {
    renderBadge();
    expect(screen.queryByText(HINT)).toBeNull();
    fireEvent.click(screen.getByText("Hazy night"));
    expect(await screen.findByText(HINT)).toBeInTheDocument();
  });

  it("dismisses on a second tap, and on losing focus", async () => {
    renderBadge();
    const badge = screen.getByText("Hazy night");
    fireEvent.click(badge);
    expect(await screen.findByText(HINT)).toBeInTheDocument();
    fireEvent.click(badge);
    await waitFor(() => expect(screen.queryByText(HINT)).toBeNull());
    // No outside-click handler, same as HintIcon: on touch, tapping anything
    // else takes focus away, and that is how a tapped hint is put away.
    fireEvent.click(badge);
    expect(await screen.findByText(HINT)).toBeInTheDocument();
    fireEvent.blur(badge);
    await waitFor(() => expect(screen.queryByText(HINT)).toBeNull());
  });

  it("still opens on hover, and now on keyboard focus too", async () => {
    renderBadge();
    const badge = screen.getByText("Hazy night");
    fireEvent.mouseEnter(badge);
    expect(await screen.findByText(HINT)).toBeInTheDocument();
    fireEvent.mouseLeave(badge);
    await waitFor(() => expect(screen.queryByText(HINT)).toBeNull());

    fireEvent.focus(badge);
    expect(await screen.findByText(HINT)).toBeInTheDocument();
  });

  it("opens on Enter and on Space, and swallows Space so the page can't scroll", async () => {
    renderBadge();
    const badge = screen.getByText("Hazy night");
    fireEvent.keyDown(badge, { key: "Enter" });
    expect(await screen.findByText(HINT)).toBeInTheDocument();
    fireEvent.keyDown(badge, { key: "Enter" });
    await waitFor(() => expect(screen.queryByText(HINT)).toBeNull());

    const space = fireEvent.keyDown(badge, { key: " " });
    expect(space).toBe(false);   // preventDefault() was called
    expect(await screen.findByText(HINT)).toBeInTheDocument();
  });

  it("is a real tab stop, so a keyboard can reach it at all", () => {
    renderBadge();
    // The trigger is the Badge's *root*, not the label span `getByText` finds —
    // Mantine wraps the words in an inner element, so the role and the tab stop
    // land one level up. A click on the words still reaches it by bubbling.
    const root = screen.getByRole("button", { name: "Hazy night" });
    expect(root).toHaveAttribute("tabindex", "0");
    expect(root.textContent).toBe("Hazy night");
  });

  it("keeps the badge's own words as its name — nothing looking it up has to know", () => {
    renderBadge();
    // The badge is found by what it says, exactly as before: unlike `HintIcon`,
    // which needs an invented aria-label, the trigger here already has a name.
    expect(screen.getByRole("button", { name: "Hazy night" })).toBeInTheDocument();
  });

  it("with nothing to say, the badge is left exactly as it was", () => {
    renderBadge({ label: null });
    expect(screen.queryByRole("button")).toBeNull();
    fireEvent.click(screen.getByText("Hazy night"));
    expect(screen.queryByText(HINT)).toBeNull();
  });

  it("`disabled` does the same, so a conditional hint doesn't advertise itself", () => {
    renderBadge({ disabled: true });
    expect(screen.queryByRole("button")).toBeNull();
    fireEvent.click(screen.getByText("Hazy night"));
    expect(screen.queryByText(HINT)).toBeNull();
  });

  it("runs the trigger's own handler as well as opening the hint", async () => {
    const onClick = vi.fn();
    render(
      <MantineProvider>
        <HintTooltip label={HINT} multiline w={260}>
          <Badge onClick={onClick}>Hazy night</Badge>
        </HintTooltip>
      </MantineProvider>,
    );
    fireEvent.click(screen.getByText("Hazy night"));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(HINT)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// The drift guard. Four slices of this entry have each fixed the sites that
// existed; nothing stopped the next one being written the old way — which is
// how a `<Tooltip>` around a Badge survived three of them. A `Badge` has no
// action, so a plain `<Tooltip>` around one is *only* ever reachable by hover:
// on the device this app is mostly read on it is not written at all.
// ---------------------------------------------------------------------------

/** `<Tooltip …>` whose first child element is a `<Badge`, as "file:line". */
function tooltipsWrappingABadge(sources: { name: string; text: string }[]): string[] {
  const hits: string[] = [];
  for (const { name, text } of sources) {
    const lines = text.split("\n");
    lines.forEach((line, i) => {
      const at = line.indexOf("<Tooltip");
      if (at < 0) return;
      // Only the *first* element under the opening tag decides: that is the
      // trigger Mantine clones, and the one a tap would land on.
      for (let j = i; j < Math.min(i + 14, lines.length); j++) {
        const rest = j === i ? lines[j].slice(at + "<Tooltip".length) : lines[j];
        const m = /<([A-Za-z][A-Za-z0-9.]*)/.exec(rest);
        if (!m) continue;
        if (m[1] === "Badge") hits.push(`${name}:${i + 1}`);
        return;
      }
    });
  }
  return hits;
}

/** Every non-test `.tsx` in the app, as { name, text }.
 *
 * Read through Vite's own `import.meta.glob` rather than `node:fs`: the app has
 * no `@types/node`, and this keeps the guard running on exactly the files the
 * bundler would compile.
 */
function frontendSources(): { name: string; text: string }[] {
  const raw = import.meta.glob("../**/*.tsx", {
    query: "?raw", import: "default", eager: true,
  }) as Record<string, string>;
  return Object.entries(raw)
    .filter(([name]) => !name.endsWith(".test.tsx"))
    .map(([name, text]) => ({ name: name.replace(/^\.\.\//, ""), text }));
}

describe("no Tooltip may be wrapped around a Badge", () => {
  it("finds none in the app — they are all HintTooltip", () => {
    const sources = frontendSources();
    // An empty result is what a clean tree and a mis-scanned one both look
    // like, so pin that the sweep really walked the app first.
    expect(sources.length).toBeGreaterThan(80);
    expect(sources.some((s) => s.name.endsWith("HazyNightBadge.tsx"))).toBe(true);
    expect(sources.some((s) => s.name.endsWith("routes/Tonight.tsx"))).toBe(true);
    expect(tooltipsWrappingABadge(sources)).toEqual([]);
  });

  it("and the guard is armed — it flags one written the old way", () => {
    expect(tooltipsWrappingABadge([{
      name: "routes/Made Up.tsx",
      text: [
        "export function X() {",
        "  return (",
        "    <Tooltip label={why} multiline w={240} withArrow>",
        "      <Badge size=\"xs\">seams flat</Badge>",
        "    </Tooltip>",
        "  );",
        "}",
      ].join("\n"),
    }])).toEqual(["routes/Made Up.tsx:3"]);
  });

  it("and it does not flag a Tooltip around something that can be tapped", () => {
    expect(tooltipsWrappingABadge([{
      name: "routes/Made Up.tsx",
      text: [
        "    <Tooltip label={why}>",
        "      <ActionIcon aria-label=\"Delete\"><IconTrash /></ActionIcon>",
        "    </Tooltip>",
      ].join("\n"),
    }])).toEqual([]);
  });
});
