import { describe, it, expect } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import { HazyNightBadge, isHazy } from "./HazyNightBadge";

function renderBadge(ratio?: number | null) {
  return render(
    <MantineProvider>
      <HazyNightBadge ratio={ratio} />
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

  it("isHazy guards non-positive and missing values", () => {
    expect(isHazy(0.59)).toBe(true);
    expect(isHazy(0.6)).toBe(false);
    expect(isHazy(0)).toBe(false);
    expect(isHazy(-1)).toBe(false);
    expect(isHazy(null)).toBe(false);
    expect(isHazy(undefined)).toBe(false);
  });

  // The badge is what the owner sees on a phone, and a phone has no hover. Until
  // v0.413.0 the only sentence explaining what "Hazy night" means was on a plain
  // `<Tooltip>`, i.e. reachable by a gesture the device does not have — and a
  // Badge has no action, so there was nothing else to try either.
  it("says what it means when tapped, not only when hovered", async () => {
    renderBadge(0.44);
    expect(screen.queryByText(/Shot through haze/)).toBeNull();
    fireEvent.click(screen.getByText("Hazy night"));
    expect(await screen.findByText(/Shot through haze/)).toBeInTheDocument();
  });
});
