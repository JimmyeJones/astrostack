import { describe, it, expect } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";

import { UnsolvedHelp } from "./UnsolvedHelp";

function renderHelp() {
  return render(
    <MantineProvider>
      <UnsolvedHelp />
    </MantineProvider>,
  );
}

describe("UnsolvedHelp", () => {
  it("shows a labelled help affordance without revealing the explainer up front", () => {
    renderHelp();
    // The "?" button is always visible (glanceable), but its plain-language
    // explainer stays collapsed until the user asks for it.
    expect(
      screen.getByRole("button", { name: /what does .*not located yet.* mean/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Plate-solving works out exactly where/)).toBeNull();
  });

  it("reveals the plain-language plate-solve explainer when opened", async () => {
    renderHelp();
    fireEvent.click(
      screen.getByRole("button", { name: /what does .*not located yet.* mean/i }),
    );
    // Explains what plate-solving is, reassures it's usually harmless, and gives
    // the one actionable next step (the star database) — the whole point of the
    // affordance is that a beginner doesn't read the badge as a scary error.
    expect(
      await screen.findByText(/Plate-solving works out exactly where in the sky/),
    ).toBeInTheDocument();
    expect(screen.getByText(/usually\s+harmless/)).toBeInTheDocument();
    expect(screen.getByText(/star database is installed/)).toBeInTheDocument();
  });
});
