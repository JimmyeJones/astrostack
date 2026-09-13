import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import { PanelSeamsBadge, seamsLabel } from "./PanelSeamsBadge";

function renderBadge(verdict?: string | null, grain?: string | null) {
  return render(
    <MantineProvider>
      <PanelSeamsBadge verdict={verdict} grain={grain} />
    </MantineProvider>,
  );
}

describe("PanelSeamsBadge", () => {
  it("says the panels evened out", () => {
    renderBadge("flat");
    expect(screen.getByText("Panels even")).toBeInTheDocument();
  });

  it("flags a mosaic whose joins still step", () => {
    renderBadge("check");
    expect(screen.getByText("Panels: check")).toBeInTheDocument();
  });

  it("renders nothing without a verdict", () => {
    // Every single-field stack, every pre-measurement run, and the ambiguous
    // middle band the backend deliberately keeps silent.
    for (const v of [null, undefined, ""]) {
      const { unmount } = renderBadge(v);
      expect(screen.queryByText(/Panels/)).not.toBeInTheDocument();
      unmount();
    }
  });

  it("renders nothing for a verdict word it doesn't know", () => {
    // Forward-compatible: a newer backend adding a third verdict must not make
    // an older frontend render a stray chip.
    renderBadge("something_else");
    expect(screen.queryByText(/Panels/)).not.toBeInTheDocument();
  });

  it("seamsLabel gives the beginner a word, never the raw ratio", () => {
    expect(seamsLabel("flat")?.label).toBe("Panels even");
    expect(seamsLabel("check")?.color).toBe("yellow");
    expect(seamsLabel("check")?.help).toContain("background tools");
    expect(seamsLabel(null)).toBeNull();
    expect(seamsLabel(undefined)).toBeNull();
  });

  it("stops promising no visible difference on an unevenly deep mosaic", () => {
    // The bug: a mosaic can be perfectly *level* and still show an obvious
    // grainier rectangle, because that panel was shot with fewer subs. Saying
    // "you shouldn't see seams between them" to someone looking straight at one
    // is the untruth here.
    const help = seamsLabel("flat", "uneven")?.help ?? "";
    expect(help).not.toContain("you shouldn't see seams");
    expect(help).toContain("difference in depth");
    // Nothing removed: it still says the panels evened out, and stays green.
    expect(help).toContain("evened out");
    expect(seamsLabel("flat", "uneven")?.color).toBe("teal");
  });

  it("says which of the two it measured on the chip, not only on hover", () => {
    // The half the tooltip fix left behind: the *word on the chip* still read
    // "Panels even" on a mosaic whose health panel calls a quarter of the same
    // picture 1.4x grainier. A reader who never taps the hint — which is most
    // of them, and on the Gallery/Compare cards the chip is the only thing on
    // the row that knows about the panels — was told the panels are even.
    const v = seamsLabel("flat", "uneven");
    expect(v?.label).toBe("Sky even");
    expect(v?.label).not.toBe("Panels even");
    // Still good news, and still the same measurement: only the wording of what
    // was measured moved.
    expect(v?.color).toBe("teal");
    expect(v?.help).toBe(seamsLabel("flat", "uneven")?.help);
  });

  it("renders the honest label on the real chip", () => {
    renderBadge("flat", "uneven");
    expect(screen.getByText("Sky even")).toBeInTheDocument();
    expect(screen.queryByText("Panels even")).not.toBeInTheDocument();
  });

  it("is never longer than the label it replaces", () => {
    // Not a style rule — a layout one, measured in a browser. Both badge rows
    // this chip lives in are `<Group wrap="nowrap">` sharing a row with the run
    // name, so a longer label does not wrap: it squeezes its neighbours into
    // ellipses. "Sky even, one part thinner" turned History's row into
    // `MIN-… | SKY EVEN, ONE PART TH… | 21 FRA…`, costing two facts to add one.
    // jsdom does no layout, so the only thing that can be pinned here is the
    // budget itself.
    const honest = seamsLabel("flat", "uneven")!.label;
    const plain = seamsLabel("flat")!.label;
    expect(honest.length).toBeLessThanOrEqual(plain.length);
  });

  it("keeps exactly its old label when nothing measured the grain", () => {
    // An older run, a single field, an even mosaic, an older backend omitting
    // the field — all of them are today's chip, unchanged.
    for (const g of [null, undefined, "", "something_else"]) {
      expect(seamsLabel("flat", g)?.label).toBe("Panels even");
    }
    expect(seamsLabel("check", "uneven")?.label).toBe("Panels: check");
  });

  it("keeps exactly its old wording when nothing measured the grain", () => {
    // An older run, a single field, an even mosaic, an older backend omitting
    // the field — all of them are today's sentence, unchanged.
    for (const g of [null, undefined, "", "something_else"]) {
      expect(seamsLabel("flat", g)?.help).toBe(
        "This mosaic's panels evened out — the sky matches across the joins, "
        + "so you shouldn't see seams between them.",
      );
    }
  });

  it("leaves a stepped mosaic's warning alone whatever the grain says", () => {
    // "check" is about the sky level and is still the more useful thing to say.
    expect(seamsLabel("check", "uneven")?.help).toBe(seamsLabel("check")?.help);
  });
});
