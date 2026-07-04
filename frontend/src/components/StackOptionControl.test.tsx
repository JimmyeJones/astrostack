import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
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
