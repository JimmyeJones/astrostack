import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FocusChip } from "./FocusChip";

function renderChip(verdict?: "sharpest" | "soft") {
  return render(
    <MantineProvider>
      <FocusChip verdict={verdict} />
    </MantineProvider>,
  );
}

describe("FocusChip", () => {
  it("renders no chip when there is no verdict", () => {
    renderChip(undefined);
    expect(screen.queryByText(/sharpest yet/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/softer than usual/i)).not.toBeInTheDocument();
  });

  it("renders the sharpest-yet chip", () => {
    renderChip("sharpest");
    expect(screen.getByText(/sharpest yet/i)).toBeInTheDocument();
  });

  it("renders the softer-than-usual chip", () => {
    renderChip("soft");
    expect(screen.getByText(/softer than usual/i)).toBeInTheDocument();
  });
});
