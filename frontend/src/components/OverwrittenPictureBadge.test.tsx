import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import { OverwrittenPictureBadge } from "./OverwrittenPictureBadge";

function renderBadge(props: Parameters<typeof OverwrittenPictureBadge>[0]) {
  return render(
    <MantineProvider><OverwrittenPictureBadge {...props} /></MantineProvider>,
  );
}

describe("OverwrittenPictureBadge", () => {
  it("says nothing for a run that owns its own picture", () => {
    // The overwhelmingly common case, and every run on an install that has only
    // re-stacked since v0.81.8. `null` and `undefined` both have to be silent:
    // an older backend sends no field at all.
    renderBadge({ ownerRunId: null });
    expect(screen.queryByText("picture overwritten")).not.toBeInTheDocument();
    renderBadge({});
    expect(screen.queryByText("picture overwritten")).not.toBeInTheDocument();
  });

  it("labels a card whose thumbnail belongs to a later stack, and dates it", () => {
    renderBadge({ ownerRunId: 7, ownerDate: "30 Aug 2026, 14:32" });
    expect(screen.getByText("picture overwritten")).toBeTruthy();
    const title = screen.getByText("picture overwritten")
      .closest("[title]")?.getAttribute("title") ?? "";
    // It has to say three things: this run's picture is gone, whose picture is
    // on screen instead, and that the numbers on the card are still this run's —
    // otherwise the honest label just reads as "something is broken".
    expect(title).toContain("the stack from 30 Aug 2026, 14:32");
    expect(title).toContain("still this run's");
    expect(title).toMatch(/0\.81\.8/);
  });

  it("does not invent a date when the owning run is not in view", () => {
    // Its row can be off this page, or deleted. The badge still has to appear —
    // the thumbnail is still not this run's — so it falls back to naming the
    // relationship rather than printing an empty date.
    renderBadge({ ownerRunId: 7 });
    const title = screen.getByText("picture overwritten")
      .closest("[title]")?.getAttribute("title") ?? "";
    expect(title).toContain("a later stack of this target");
    expect(title).not.toContain("the stack from ");
  });
});
