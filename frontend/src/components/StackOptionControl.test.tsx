import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StackOptionControl } from "./StackOptionControl";
import type { StackOptionField } from "../api/client";

const wrap = (ui: React.ReactNode) => render(<MantineProvider>{ui}</MantineProvider>);

const enumField = (option_labels?: Record<string, string>): StackOptionField => ({
  key: "mode", label: "Curve", type: "enum", group: "simple", default: "asinh",
  min: null, max: null, step: null, options: ["asinh", "stf"], option_labels,
  help: null, depends_on: null,
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
