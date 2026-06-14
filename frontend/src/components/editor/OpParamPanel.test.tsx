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
});
