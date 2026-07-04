import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OpList } from "./OpList";
import type { EditOp, OpInstance } from "../../api/client";

const SPEC: EditOp = {
  id: "tone.stretch", label: "Stretch", group: "tone", stage: "any",
  proxy_safe: true, is_stretch: true, help: "Brighten faint detail.",
  params: [],
};
const SPECS: Record<string, EditOp> = { "tone.stretch": SPEC };
const OPS: OpInstance[] = [
  { uid: "a", id: "tone.stretch", params: {}, enabled: true },
  { uid: "b", id: "tone.stretch", params: {}, enabled: true },
];

const wrap = (ui: React.ReactNode) => render(<MantineProvider>{ui}</MantineProvider>);

describe("OpList a11y", () => {
  it("exposes each op row as a focusable button for keyboard users", () => {
    wrap(<OpList ops={OPS} specs={SPECS} selected={null} onSelect={() => {}}
      onMove={() => {}} onToggle={() => {}} onRemove={() => {}} />);
    const rows = screen.getAllByRole("button", { name: /Select Stretch/ });
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute("tabindex", "0");
  });

  it("selects an op when the row is activated with Enter or Space", () => {
    const onSelect = vi.fn();
    wrap(<OpList ops={OPS} specs={SPECS} selected={null} onSelect={onSelect}
      onMove={() => {}} onToggle={() => {}} onRemove={() => {}} />);
    const rows = screen.getAllByRole("button", { name: /Select Stretch/ });
    fireEvent.keyDown(rows[1], { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("b");
    fireEvent.keyDown(rows[0], { key: " " });
    expect(onSelect).toHaveBeenCalledWith("a");
  });

  it("marks the selected row with aria-pressed", () => {
    wrap(<OpList ops={OPS} specs={SPECS} selected="a" onSelect={() => {}}
      onMove={() => {}} onToggle={() => {}} onRemove={() => {}} />);
    const rows = screen.getAllByRole("button", { name: /Select Stretch/ });
    expect(rows[0]).toHaveAttribute("aria-pressed", "true");
    expect(rows[1]).toHaveAttribute("aria-pressed", "false");
  });
});
