import { MantineProvider, Switch } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HintIcon } from "./HintIcon";

const HINT = "What this control is actually for, in a whole sentence.";

function renderIcon() {
  return render(
    <MantineProvider>
      <HintIcon hint={HINT} />
    </MantineProvider>,
  );
}

describe("HintIcon", () => {
  it("shows the hint on a tap — the only gesture a phone has", async () => {
    renderIcon();
    expect(screen.queryByText(HINT)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "What does this do?" }));
    expect(await screen.findByText(HINT)).toBeInTheDocument();
  });

  it("dismisses on a second tap, and on losing focus", async () => {
    renderIcon();
    const icon = screen.getByRole("button", { name: "What does this do?" });
    fireEvent.click(icon);
    expect(await screen.findByText(HINT)).toBeInTheDocument();
    fireEvent.click(icon);
    await waitFor(() => expect(screen.queryByText(HINT)).toBeNull());
    // There is no outside-click handler: on touch, tapping anything else takes
    // focus away, and that is how a tapped hint is put away without a second,
    // precise tap on a 14 px target.
    fireEvent.click(icon);
    expect(await screen.findByText(HINT)).toBeInTheDocument();
    fireEvent.blur(icon);
    await waitFor(() => expect(screen.queryByText(HINT)).toBeNull());
  });

  it("still opens on hover and on keyboard focus", async () => {
    renderIcon();
    const icon = screen.getByRole("button", { name: "What does this do?" });
    fireEvent.mouseEnter(icon);
    expect(await screen.findByText(HINT)).toBeInTheDocument();
    fireEvent.mouseLeave(icon);
    await waitFor(() => expect(screen.queryByText(HINT)).toBeNull());
    fireEvent.focus(icon);
    expect(await screen.findByText(HINT)).toBeInTheDocument();
  });

  it("opens from the keyboard, since it is a span carrying the button role",
    async () => {
      renderIcon();
      const icon = screen.getByRole("button", { name: "What does this do?" });
      fireEvent.keyDown(icon, { key: "Enter" });
      expect(await screen.findByText(HINT)).toBeInTheDocument();
      fireEvent.keyDown(icon, { key: " " });
      await waitFor(() => expect(screen.queryByText(HINT)).toBeNull());
    });

  it("never operates the control it sits beside", async () => {
    // The whole reason it sits beside the control rather than being wrapped
    // around it: asking "what does this do?" must not do it.
    const onChange = vi.fn();
    render(
      <MantineProvider>
        <Switch label="Auto-crop edges" checked={false} onChange={onChange} />
        <HintIcon hint={HINT} />
      </MantineProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "What does this do?" }));
    expect(await screen.findByText(HINT)).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Auto-crop edges")).not.toBeChecked();
  });

  it("leaves the control's own accessible name alone", () => {
    render(
      <MantineProvider>
        <Switch label="Auto-crop edges" checked={false} onChange={() => {}} />
        <HintIcon hint={HINT} />
      </MantineProvider>,
    );
    // Exactly "Auto-crop edges" — the icon is a sibling, not part of the
    // control's <label>, so nothing that looks the switch up by its own name
    // (a screen reader, or a test) has to know the hint exists.
    expect(screen.getByLabelText("Auto-crop edges")).toBeInTheDocument();
  });
});
