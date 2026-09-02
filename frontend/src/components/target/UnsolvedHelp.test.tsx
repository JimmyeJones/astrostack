import { describe, it, expect } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";

import { UnsolvedHelp } from "./UnsolvedHelp";
import type { SolveSetup } from "./solveSetup";

function renderHelp(setup: SolveSetup | null = null) {
  return render(
    <MantineProvider>
      <UnsolvedHelp setup={setup} />
    </MantineProvider>,
  );
}

function open() {
  fireEvent.click(
    screen.getByRole("button", { name: /what does .*not located yet.* mean/i }),
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

  // The contradiction this prop exists to remove: when ASTAP or its star
  // database is missing, the Target page shows a *blocking* banner saying the
  // problem "blocks the whole target" — and this popover sat beside it calling
  // the same subs "usually harmless: the located subs still stack into your
  // picture". With no solver there are no located subs, so that reassurance was
  // both contradictory and false.
  it("does not call the subs harmless when the solver itself is missing", async () => {
    renderHelp({ kind: "astap", frames: 200 });
    open();

    expect(await screen.findByText(/ASTAP — the program that does the locating/))
      .toBeInTheDocument();
    expect(screen.queryByText(/usually\s+harmless/)).toBeNull();
    // It still reassures, on the fact that is actually true here: the subs are
    // all still on disk and one fix brings them in.
    expect(screen.getByText(/Nothing has been lost/)).toBeInTheDocument();
  });

  it("names the missing star database when that is the blocker", async () => {
    renderHelp({ kind: "database", frames: 12 });
    open();

    expect(await screen.findByText(/no star database to match your subs against/))
      .toBeInTheDocument();
    expect(screen.queryByText(/usually\s+harmless/)).toBeNull();
    // …and it points at the banner rather than repeating its instructions, so a
    // beginner has one place to act, not two competing ones.
    expect(screen.getByText(/orange note above/)).toBeInTheDocument();
  });
});
