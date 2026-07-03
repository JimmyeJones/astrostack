import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OpParamPanel } from "./OpParamPanel";
import type { EditOp } from "../../api/client";

const SPEC: EditOp = {
  id: "tone.x", label: "X", group: "tone", stage: "any",
  proxy_safe: true, is_stretch: false, help: null,
  params: [{
    key: "amount", label: "Amount", type: "float", group: "simple",
    default: 1.0, min: 0, max: 3, step: 0.1, options: null, help: null, depends_on: null,
  }],
};

const wrap = (ui: React.ReactNode) => render(<MantineProvider>{ui}</MantineProvider>);

describe("OpParamPanel", () => {
  it("renders bounded numeric params as a slider (not a bare number input)", () => {
    wrap(<OpParamPanel spec={SPEC} params={{ amount: 1.5 }} onChange={() => {}} />);
    expect(screen.getByRole("slider")).toBeInTheDocument();
  });

  it("resets params to their schema defaults", () => {
    const onChange = vi.fn();
    wrap(<OpParamPanel spec={SPEC} params={{ amount: 2.5 }} onChange={onChange} />);
    fireEvent.click(screen.getByText("Reset op"));
    expect(onChange).toHaveBeenCalledWith({ amount: 1.0 });
  });

  it("per-param reset is disabled when the value already equals the default", () => {
    wrap(<OpParamPanel spec={SPEC} params={{ amount: 1.0 }} onChange={() => {}} />);
    expect(screen.getByLabelText("Reset Amount")).toBeDisabled();
  });

  it("offers a data-driven suggestion button that sets the param", () => {
    const onChange = vi.fn();
    wrap(
      <OpParamPanel
        spec={SPEC} params={{ amount: 1.5 }} onChange={onChange}
        suggestions={{ amount: { value: 2.2, label: "From your data (2.2)" } }}
      />,
    );
    fireEvent.click(screen.getByText("From your data (2.2)"));
    expect(onChange).toHaveBeenCalledWith({ amount: 2.2 });
  });

  it("omits the suggestion button when no suggestion is given for a param", () => {
    wrap(<OpParamPanel spec={SPEC} params={{ amount: 1.5 }} onChange={() => {}} />);
    expect(screen.queryByLabelText("Set Amount from your data")).not.toBeInTheDocument();
  });

  it("greys out a param whose depends_on value doesn't match the current choice", () => {
    const spec: EditOp = {
      id: "tone.stretch", label: "Stretch", group: "tone", stage: "any",
      proxy_safe: true, is_stretch: true, help: null,
      params: [
        {
          key: "mode", label: "Curve", type: "enum", group: "simple", default: "asinh",
          min: null, max: null, step: null, options: ["asinh", "stf"], help: null, depends_on: null,
        },
        {
          key: "target_bg", label: "STF sky level", type: "float", group: "simple",
          default: 0.2, min: 0.02, max: 0.6, step: 0.01, options: null, help: null,
          depends_on: "mode=stf",
        },
      ],
    };
    // In asinh mode the STF-only slider is disabled…
    const asinh = wrap(
      <OpParamPanel spec={spec} params={{ mode: "asinh", target_bg: 0.2 }} onChange={() => {}} />,
    );
    expect(asinh.getByRole("slider")).toHaveAttribute("data-disabled", "true");
    asinh.unmount();
    // …and enabled once STF is selected.
    const stf = wrap(
      <OpParamPanel spec={spec} params={{ mode: "stf", target_bg: 0.2 }} onChange={() => {}} />,
    );
    expect(stf.getByRole("slider")).not.toHaveAttribute("data-disabled", "true");
  });
});
