import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SkyBrightnessRead } from "../../api/client";
import { SkyBrightnessNote } from "./SkyBrightnessNote";

function renderNote(read?: SkyBrightnessRead | null) {
  return render(
    <MantineProvider>
      <SkyBrightnessNote read={read} />
    </MantineProvider>,
  );
}

const bright: SkyBrightnessRead = {
  level: "much_brighter",
  label: "Much brighter than usual",
  text: "The sky on this night measured about 150% brighter than your typical night on this target — save this target for a darker night.",
  night: "2026-07-23",
  nights: 4,
  ratio: 2.5,
};

describe("SkyBrightnessNote", () => {
  it("renders nothing when there is no trustworthy read", () => {
    // The endpoint returns null until it has enough nights to compare against,
    // so the card must be safe to drop in unconditionally.
    const { unmount } = renderNote(null);
    expect(screen.queryByText(/your sky on the night of/i)).toBeNull();
    unmount();
    renderNote(undefined);
    expect(screen.queryByText(/your sky on the night of/i)).toBeNull();
  });

  it("names the night, the verdict and what to do about it", () => {
    renderNote(bright);
    // The night reads like every other night label in the app ("23 Jul 2026"),
    // not like the server's raw `2026-07-23` — it printed the ISO string until
    // v0.428.1, the one date on the Target page that didn't read like a date.
    expect(screen.getByText(/night of 23 Jul 2026: much brighter than usual/i))
      .toBeInTheDocument();
    expect(screen.queryByText(/2026-07-23/)).toBeNull();
    expect(screen.getByText(/save this target for a darker night/i)).toBeInTheDocument();
  });

  it("falls back rather than blanking when the night can't be parsed", () => {
    // `formatNightDate` answers "—" for anything it can't read, so a stamp from
    // an older backend can never leave the sentence mid-air.
    renderNote({ ...bright, night: "" });
    expect(screen.getByText(/night of —: much brighter than usual/i)).toBeInTheDocument();
  });

  it("says how the read was made, and that it is not an absolute rating", () => {
    renderNote(bright);
    expect(screen.getByText(/compared with your other 4 nights/i)).toBeInTheDocument();
    expect(screen.getByText(/not an absolute sky rating/i)).toBeInTheDocument();
  });

  it("still reassures on an ordinary night", () => {
    renderNote({
      ...bright, level: "typical", label: "Typical for your sky", ratio: 1.0,
      text: "The sky on this night was about as bright as your other 4 nights on this target — nothing unusual to explain the result.",
    });
    expect(screen.getByText(/nothing unusual to explain the result/i)).toBeInTheDocument();
  });

  it("renders every level without falling over", () => {
    for (const level of ["darker", "typical", "brighter", "much_brighter"] as const) {
      const { unmount } = renderNote({ ...bright, level });
      expect(screen.getByText(new RegExp(bright.text.slice(0, 30), "i"))).toBeInTheDocument();
      unmount();
    }
  });
});
