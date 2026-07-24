import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DarksGuide, formatDarkSpec } from "./DarksGuide";

describe("formatDarkSpec", () => {
  it("joins exposure and gain into a match-these-numbers phrase", () => {
    expect(formatDarkSpec({ exposure_s: 10, gain: 80 })).toBe("10 s at gain 80");
  });
  it("keeps one decimal for a fractional exposure and rounds gain", () => {
    expect(formatDarkSpec({ exposure_s: 2.5, gain: 79.6 })).toBe("2.5 s at gain 80");
  });
  it("uses whatever single value is known", () => {
    expect(formatDarkSpec({ exposure_s: 30, gain: null })).toBe("30 s");
    expect(formatDarkSpec({ exposure_s: null, gain: 100 })).toBe("gain 100");
  });
  it("returns null when nothing usable is known (generic fallback)", () => {
    expect(formatDarkSpec({ exposure_s: null, gain: null })).toBeNull();
    expect(formatDarkSpec({ exposure_s: 0, gain: null })).toBeNull();
    expect(formatDarkSpec(null)).toBeNull();
    expect(formatDarkSpec(undefined)).toBeNull();
  });
});

function renderGuide(spec: Parameters<typeof DarksGuide>[0]["spec"]) {
  return render(
    <MantineProvider>
      <DarksGuide spec={spec} />
    </MantineProvider>,
  );
}

describe("DarksGuide", () => {
  it("expands the three steps with the target's own numbers pre-filled", () => {
    renderGuide({ exposure_s: 10, gain: 80 });
    fireEvent.click(screen.getByText("How to add darks →"));
    expect(
      screen.getByText(/same settings as your subs — 10 s at gain 80/),
    ).toBeInTheDocument();
    // Cap-the-scope step and the drop-folder step are present too.
    expect(screen.getByText(/Cap the scope/)).toBeInTheDocument();
    expect(screen.getByText(/AstroStack builds the master dark/)).toBeInTheDocument();
  });

  it("falls back to generic wording when exposure/gain are unknown", () => {
    renderGuide({ exposure_s: null, gain: null });
    fireEvent.click(screen.getByText("How to add darks →"));
    expect(
      screen.getByText(/same exposure and gain as your subs\./),
    ).toBeInTheDocument();
  });
});
