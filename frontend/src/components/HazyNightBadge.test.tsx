import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
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
});
