import { Badge, MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HintAnchor } from "./HintAnchor";

const HINT = "What this chip is actually saying, in a whole sentence.";

function renderChip(extra: Record<string, unknown> = {}) {
  return render(
    <MantineProvider>
      <HintAnchor label={HINT} multiline w={260}>
        <Badge color="teal" variant="light" {...extra}>Cleanest</Badge>
      </HintAnchor>
    </MantineProvider>,
  );
}

describe("HintAnchor", () => {
  it("shows the hint on a tap — the only gesture a phone has", async () => {
    renderChip();
    expect(screen.queryByText(HINT)).toBeNull();
    fireEvent.click(screen.getByText("Cleanest"));
    expect(await screen.findByText(HINT)).toBeInTheDocument();
  });

  it("dismisses on a second tap, and on losing focus", async () => {
    renderChip();
    const chip = screen.getByText("Cleanest");
    fireEvent.click(chip);
    expect(await screen.findByText(HINT)).toBeInTheDocument();
    fireEvent.click(chip);
    await waitFor(() => expect(screen.queryByText(HINT)).toBeNull());
    // There is no outside-click handler: on touch, tapping anything else takes
    // focus away, and that is how a tapped hint is put away.
    fireEvent.click(chip);
    expect(await screen.findByText(HINT)).toBeInTheDocument();
    fireEvent.blur(chip);
    await waitFor(() => expect(screen.queryByText(HINT)).toBeNull());
  });

  it("still opens on hover, which is what it did before", async () => {
    renderChip();
    const chip = screen.getByText("Cleanest");
    fireEvent.mouseEnter(chip);
    expect(await screen.findByText(HINT)).toBeInTheDocument();
    fireEvent.mouseLeave(chip);
    await waitFor(() => expect(screen.queryByText(HINT)).toBeNull());
  });

  it("opens from the keyboard, since the anchor carries the button role", async () => {
    renderChip();
    const chip = screen.getByRole("button", { name: "Cleanest" });
    fireEvent.focus(chip);
    expect(await screen.findByText(HINT)).toBeInTheDocument();
    fireEvent.blur(chip);
    await waitFor(() => expect(screen.queryByText(HINT)).toBeNull());
    fireEvent.keyDown(chip, { key: "Enter" });
    expect(await screen.findByText(HINT)).toBeInTheDocument();
    fireEvent.keyDown(chip, { key: " " });
    await waitFor(() => expect(screen.queryByText(HINT)).toBeNull());
  });

  it("keeps the anchor's own handlers and its own role", async () => {
    const onClick = vi.fn();
    renderChip({ onClick, role: "status" });
    const chip = screen.getByRole("status");
    fireEvent.click(chip);
    // The site's own click still runs, *and* the hint opens: this wrapper is for
    // anchors with nothing of their own to collide with, so it never swallows.
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(HINT)).toBeInTheDocument();
  });

  it("renders the anchor itself, not a wrapper box — no row can move", () => {
    const { container } = renderChip();
    // The chip sits directly in the render root: nothing was inserted around
    // it, so no layout, height or flex behaviour changes.
    expect(screen.getByRole("button", { name: "Cleanest" }).parentElement)
      .toBe(container);
  });
});
