import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { isStarfieldEnabled, setStarfieldEnabled } from "../nightsky/prefs";
import { NightSkySettings } from "./NightSkySettings";

function renderCard() {
  return render(
    <MantineProvider defaultColorScheme="dark">
      <NightSkySettings />
    </MantineProvider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("the drifting-stars switch", () => {
  it("shows on by default, and says the preference is this device's", () => {
    renderCard();
    const sw = screen.getByRole("switch", { name: /drifting stars/i });
    expect(sw).toBeChecked();
    // The heading names the scope, so nobody expects the switch to reach the
    // browser they left open in the lounge.
    expect(screen.getByText("Drifting stars (this device)")).toBeInTheDocument();
  });

  it("persists an opt-out, and reads back as off on the next visit", () => {
    const view = renderCard();
    fireEvent.click(screen.getByRole("switch", { name: /drifting stars/i }));
    expect(isStarfieldEnabled()).toBe(false);
    view.unmount();

    renderCard();
    expect(screen.getByRole("switch", { name: /drifting stars/i })).not.toBeChecked();
  });

  it("turns them back on again", () => {
    setStarfieldEnabled(false);
    renderCard();
    const sw = screen.getByRole("switch", { name: /drifting stars/i });
    expect(sw).not.toBeChecked();
    fireEvent.click(sw);
    expect(isStarfieldEnabled()).toBe(true);
    expect(sw).toBeChecked();
  });

  it("explains what stays neutral, so nobody wonders where the stars went", () => {
    renderCard();
    expect(screen.getByText(/editor/i)).toBeInTheDocument();
  });
});
