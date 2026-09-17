import { describe, it, expect } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import { HazyNightBadge, isHazy } from "./HazyNightBadge";

function renderBadge(ratio?: number | null, verdict?: string | null) {
  return render(
    <MantineProvider>
      {verdict === undefined
        ? <HazyNightBadge ratio={ratio} />
        : <HazyNightBadge ratio={ratio} verdict={verdict} />}
    </MantineProvider>,
  );
}

describe("HazyNightBadge", () => {
  it("renders for a hazy run (ratio below the threshold)", () => {
    renderBadge(0.44);
    expect(screen.getByText("Hazy night")).toBeInTheDocument();
  });

  it("renders nothing for a clear run", () => {
    renderBadge(0.95);
    expect(screen.queryByText("Hazy night")).not.toBeInTheDocument();
  });

  it("renders nothing when the ratio is absent", () => {
    renderBadge(null);
    expect(screen.queryByText("Hazy night")).not.toBeInTheDocument();
    renderBadge(undefined);
    expect(screen.queryByText("Hazy night")).not.toBeInTheDocument();
  });

  it("explains itself on a tap — the badge is two words and the sentence is all of it",
    async () => {
      renderBadge(0.44);
      expect(screen.queryByText(/median transparency/)).not.toBeInTheDocument();
      fireEvent.click(screen.getByText("Hazy night"));
      expect(await screen.findByText(/median transparency/)).toBeInTheDocument();
    });

  it("lets the server withhold the claim on a figure nobody can date", () => {
    // The whole point of the field. A mosaic run stacked before v0.304.2 carries
    // a figure measured against one target-wide baseline — 0.50 on a steady sky
    // — and the server answers `null` rather than let the bar be applied to a
    // different quantity. The ratio still arrives, because things that *report*
    // the number keep it; only the claim is withheld.
    renderBadge(0.5, null);
    expect(screen.queryByText("Hazy night")).not.toBeInTheDocument();
  });

  it("shows the badge on the server's word even where the bar is borderline", () => {
    renderBadge(0.6, "hazy");
    expect(screen.getByText("Hazy night")).toBeInTheDocument();
  });

  it("falls back to reading the ratio against a backend with no verdict", () => {
    // `undefined` is an older backend; `null` is this one saying "nothing to
    // claim". The two must not be conflated, or the upgrade would silence every
    // badge on a mixed pair.
    renderBadge(0.44);
    expect(screen.getByText("Hazy night")).toBeInTheDocument();
  });

  it("keeps the sentence when a verdict arrives without a figure", async () => {
    renderBadge(null, "hazy");
    expect(screen.getByText("Hazy night")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Hazy night"));
    // No "NaN% below" — the percentage is a reading of a figure that isn't here.
    expect(await screen.findByText(/well below this target/)).toBeInTheDocument();
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });

  it("isHazy guards non-positive and missing values", () => {
    expect(isHazy(0.59)).toBe(true);
    expect(isHazy(0.6)).toBe(false);
    expect(isHazy(0)).toBe(false);
    expect(isHazy(-1)).toBe(false);
    expect(isHazy(null)).toBe(false);
    expect(isHazy(undefined)).toBe(false);
  });
});
