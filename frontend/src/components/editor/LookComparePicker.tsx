import { Button, Menu } from "@mantine/core";
import { IconChevronDown, IconArrowsHorizontal, IconCheck } from "@tabler/icons-react";
import type { Preset } from "../../api/client";

/** Which look the user wants to compare their current edit against under the
 * split divider: the one-click Auto recipe, a built-in preset, or one of their
 * saved presets. The Editor resolves this into a concrete op list (sizing a
 * built-in preset to the target's data the same way applying it would). */
export type LookChoice =
  | { kind: "auto" }
  | { kind: "preset"; preset: Preset; source: "builtin" | "user" };

/** A small dropdown that lets the user pick another *look* (Auto / a built-in or
 * saved preset) to preview as the "before" side of the split divider, so they can
 * drag to judge their current edit against any other look in one frame without
 * committing to it. Sits next to the Split/Compare buttons in the preview
 * toolbar. */
export function LookComparePicker({
  builtin, user, disabled, active, activeLabel, loading, onPick, onStop, onAdopt,
}: {
  builtin: Preset[];
  user: Preset[];
  disabled: boolean;
  active: boolean;
  activeLabel: string | null;
  loading: boolean;
  onPick: (choice: LookChoice) => void;
  onStop: () => void;
  /** Apply the look currently being compared as the working recipe (an undoable
   * step). Lets the user go from "compare" straight to "adopt" in one click. */
  onAdopt: () => void;
}) {
  return (
    <Menu shadow="md" position="bottom-end" width={220}>
      <Menu.Target>
        <Button size="xs" variant={active ? "filled" : "default"} color="teal"
          leftSection={<IconArrowsHorizontal size={14} />}
          rightSection={<IconChevronDown size={12} />}
          loading={loading} disabled={disabled}>
          {active && activeLabel ? `Look: ${activeLabel}` : "Compare a look"}
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>Drag the divider: this look vs your edit</Menu.Label>
        <Menu.Item onClick={() => onPick({ kind: "auto" })}>Auto</Menu.Item>
        {builtin.length ? <Menu.Label>Built-in</Menu.Label> : null}
        {builtin.map((p) => (
          <Menu.Item key={p.id}
            onClick={() => onPick({ kind: "preset", preset: p, source: "builtin" })}>
            {p.label}
          </Menu.Item>
        ))}
        {user.length ? <Menu.Label>My presets</Menu.Label> : null}
        {user.map((p) => (
          <Menu.Item key={p.id}
            onClick={() => onPick({ kind: "preset", preset: p, source: "user" })}>
            {p.label}
          </Menu.Item>
        ))}
        {active ? (
          <>
            <Menu.Divider />
            <Menu.Item leftSection={<IconCheck size={14} />} color="teal" onClick={onAdopt}>
              Switch to this look
            </Menu.Item>
            <Menu.Item color="red" onClick={onStop}>Stop comparing</Menu.Item>
          </>
        ) : null}
      </Menu.Dropdown>
    </Menu>
  );
}
