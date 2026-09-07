import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StackOptionControl } from "./StackOptionControl";
import type { StackOptionField } from "../api/client";

const wrap = (ui: React.ReactNode) => render(<MantineProvider>{ui}</MantineProvider>);

const enumField = (option_labels?: Record<string, string>): StackOptionField => ({
  key: "mode", label: "Curve", type: "enum", group: "simple", default: "asinh",
  min: null, max: null, step: null, options: ["asinh", "stf"], option_labels,
  help: null, depends_on: null,
});

const floatField = (over: Partial<StackOptionField> = {}): StackOptionField => ({
  key: "gamma", label: "Gamma", type: "float", group: "simple", default: 1.0,
  min: 0.1, max: 5.0, step: 0.05, options: null, option_labels: undefined,
  help: null, depends_on: null, ...over,
});

describe("StackOptionControl enum labels", () => {
  it("shows the friendly label for the selected value when option_labels is set", () => {
    wrap(
      <StackOptionControl
        field={enumField({ asinh: "Asinh (manual)", stf: "Auto (STF)" })}
        value="stf" onChange={() => {}}
      />,
    );
    expect(screen.getByDisplayValue("Auto (STF)")).toBeInTheDocument();
  });

  it("falls back to the raw value when no label is provided", () => {
    wrap(<StackOptionControl field={enumField()} value="stf" onChange={() => {}} />);
    expect(screen.getAllByDisplayValue("stf").length).toBeGreaterThan(0);
  });
});

describe("StackOptionControl preferSlider editable readout", () => {
  it("renders the readout as an editable number field showing the current value", () => {
    wrap(
      <StackOptionControl
        field={floatField()} value={1.35} onChange={() => {}} preferSlider
      />,
    );
    const input = screen.getByLabelText("Gamma value") as HTMLInputElement;
    expect(input).toBeInTheDocument();
    expect(input.value).toBe("1.35");
  });

  it("typing an exact value in the readout calls onChange with that number", () => {
    const onChange = vi.fn();
    wrap(
      <StackOptionControl
        field={floatField()} value={1.0} onChange={onChange} preferSlider
      />,
    );
    const input = screen.getByLabelText("Gamma value");
    fireEvent.change(input, { target: { value: "2.4" } });
    expect(onChange).toHaveBeenLastCalledWith(2.4);
  });

  it("rounds the typed value for an int field", () => {
    const onChange = vi.fn();
    wrap(
      <StackOptionControl
        field={floatField({ key: "levels", label: "Levels", type: "int",
          default: 3, min: 1, max: 8, step: 1 })}
        value={3} onChange={onChange} preferSlider
      />,
    );
    const input = screen.getByLabelText("Levels value");
    fireEvent.change(input, { target: { value: "5" } });
    expect(onChange).toHaveBeenLastCalledWith(5);
  });

  it("ignores an empty readout rather than emitting null", () => {
    const onChange = vi.fn();
    wrap(
      <StackOptionControl
        field={floatField()} value={1.0} onChange={onChange} preferSlider
      />,
    );
    const input = screen.getByLabelText("Gamma value");
    fireEvent.change(input, { target: { value: "" } });
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("HintLabel — the explanation has to be reachable without a mouse", () => {
  const boolField = (help: string | null): StackOptionField => ({
    key: "drizzle", label: "Drizzle", type: "bool", group: "advanced",
    default: false, min: null, max: null, step: null, options: null,
    option_labels: undefined, help, depends_on: null,
  });

  it("tapping the info icon shows the hint instead of flipping the setting", async () => {
    // `HintLabel` is passed as a Switch's `label`, which Mantine renders inside
    // a <label> — so a tap on the icon used to activate the switch. On a phone
    // that is the *only* way to try to read the hint, so the one gesture a
    // beginner has for "what does this do?" changed their stacking options.
    const onChange = vi.fn();
    wrap(
      <StackOptionControl
        field={boolField("Recover detail from many dithered subs.")}
        value={false} onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByLabelText("What does this do?"));
    expect(await screen.findByText("Recover detail from many dithered subs."))
      .toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("tapping it again puts the hint away", async () => {
    wrap(
      <StackOptionControl field={boolField("Recover detail.")} value={false}
        onChange={() => {}} />,
    );
    const icon = screen.getByLabelText("What does this do?");
    fireEvent.click(icon);
    expect(await screen.findByText("Recover detail.")).toBeInTheDocument();
    fireEvent.click(icon);
    await waitFor(() =>
      expect(screen.queryByText("Recover detail.")).toBeNull());
  });

  it("moving on dismisses a tapped hint, so it can't be left stuck open", async () => {
    // There is no "tap outside" handler: losing focus is what closes it, which
    // is what happens the moment a touch user touches anything else.
    wrap(
      <StackOptionControl field={boolField("Recover detail.")} value={false}
        onChange={() => {}} />,
    );
    const icon = screen.getByLabelText("What does this do?");
    fireEvent.click(icon);
    expect(await screen.findByText("Recover detail.")).toBeInTheDocument();
    fireEvent.blur(icon);
    await waitFor(() =>
      expect(screen.queryByText("Recover detail.")).toBeNull());
  });

  it("still opens on hover, and now on keyboard focus too", async () => {
    wrap(
      <StackOptionControl field={boolField("Recover detail.")} value={false}
        onChange={() => {}} />,
    );
    const icon = screen.getByLabelText("What does this do?");
    fireEvent.mouseEnter(icon);
    expect(await screen.findByText("Recover detail.")).toBeInTheDocument();
    fireEvent.mouseLeave(icon);
    await waitFor(() =>
      expect(screen.queryByText("Recover detail.")).toBeNull());
    fireEvent.focus(icon);
    expect(await screen.findByText("Recover detail.")).toBeInTheDocument();
  });

  it("opens on Enter and Space, since it is a span carrying the button role", async () => {
    // It has to be a span: Mantine renders this inside the control's own
    // <label>, and a <button> there would be labelled by that label too — so
    // the field's name would then match two elements. The role and the key
    // handling are what a real button gave for free.
    wrap(
      <StackOptionControl field={boolField("Recover detail.")} value={false}
        onChange={() => {}} />,
    );
    const icon = screen.getByRole("button", { name: "What does this do?" });
    fireEvent.keyDown(icon, { key: "Enter" });
    expect(await screen.findByText("Recover detail.")).toBeInTheDocument();
    fireEvent.keyDown(icon, { key: " " });
    await waitFor(() =>
      expect(screen.queryByText("Recover detail.")).toBeNull());
  });

  it("adds nothing at all to a field that carries no explanation", () => {
    wrap(<StackOptionControl field={boolField(null)} value={false}
      onChange={() => {}} />);
    expect(screen.queryByLabelText("What does this do?")).toBeNull();
  });

  it("the switch itself still works when you actually click it", () => {
    const onChange = vi.fn();
    wrap(
      <StackOptionControl field={boolField("Recover detail.")} value={false}
        onChange={onChange} />,
    );
    fireEvent.click(screen.getByRole("switch"));
    expect(onChange).toHaveBeenLastCalledWith(true);
  });
});
