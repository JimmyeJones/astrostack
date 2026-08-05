import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import { PanelSeamsBadge, seamsLabel } from "./PanelSeamsBadge";

function renderBadge(verdict?: string | null) {
  return render(
    <MantineProvider>
      <PanelSeamsBadge verdict={verdict} />
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
});
