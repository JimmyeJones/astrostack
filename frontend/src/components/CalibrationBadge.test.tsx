import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import { CalibrationBadge, calibrationLabel } from "./CalibrationBadge";

function renderBadge(calstat?: string | null) {
  return render(
    <MantineProvider>
      <CalibrationBadge calstat={calstat} />
    </MantineProvider>,
  );
}

describe("CalibrationBadge", () => {
  it("renders the calstat string for a calibrated run", () => {
    renderBadge("dark+flat");
    expect(screen.getByText("dark+flat")).toBeInTheDocument();
  });

  it("renders nothing for an uncalibrated run", () => {
    renderBadge(null);
    expect(screen.queryByText("dark+flat")).not.toBeInTheDocument();
    renderBadge(undefined);
    expect(screen.queryByText("dark+flat")).not.toBeInTheDocument();
    renderBadge("");
    expect(screen.queryByText("dark+flat")).not.toBeInTheDocument();
  });

  it("calibrationLabel produces a friendly one-liner", () => {
    expect(calibrationLabel("dark+flat")).toBe("master dark and master flat");
    expect(calibrationLabel("bias+flat")).toBe("master bias and master flat");
    expect(calibrationLabel("flat")).toBe("master flat");
    expect(calibrationLabel(null)).toBeNull();
    expect(calibrationLabel("")).toBeNull();
    // Unknown tokens pass through rather than being dropped.
    expect(calibrationLabel("dark")).toBe("master dark");
  });
});
