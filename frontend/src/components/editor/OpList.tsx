import { ActionIcon, Group, Paper, Stack, Switch, Text } from "@mantine/core";
import { IconChevronDown, IconChevronUp, IconX } from "@tabler/icons-react";
import type { EditOp, OpInstance } from "../../api/client";

/** The ordered operation pipeline. Reorder with the arrows, toggle to bypass,
 * click to select for editing, ✕ to remove. (Dependency-free; no drag lib.) */
export function OpList({ ops, specs, selected, onSelect, onMove, onToggle, onRemove }: {
  ops: OpInstance[];
  specs: Record<string, EditOp>;
  selected: string | null;
  onSelect: (uid: string) => void;
  onMove: (uid: string, dir: -1 | 1) => void;
  onToggle: (uid: string) => void;
  onRemove: (uid: string) => void;
}) {
  if (!ops.length) {
    return <Text size="sm" c="dimmed">No operations yet — add one to start editing.</Text>;
  }
  return (
    <Stack gap={6}>
      {ops.map((op, i) => {
        const spec = specs[op.id];
        const active = op.uid === selected;
        return (
          <Paper key={op.uid} withBorder p={6} radius="sm"
            bg={active ? "var(--mantine-color-violet-light)" : undefined}
            style={{ cursor: "pointer", opacity: op.enabled ? 1 : 0.5 }}
            onClick={() => onSelect(op.uid)}>
            <Group justify="space-between" wrap="nowrap" gap="xs">
              <Group gap={6} wrap="nowrap" style={{ minWidth: 0 }}>
                <Text size="xs" c="dimmed" w={16} ta="right">{i + 1}</Text>
                <Text size="sm" fw={active ? 600 : 400} lineClamp={1}>
                  {spec?.label ?? op.id}
                </Text>
              </Group>
              <Group gap={2} wrap="nowrap" onClick={(e) => e.stopPropagation()}>
                <Switch size="xs" checked={op.enabled} onChange={() => onToggle(op.uid)}
                  aria-label="Enable/bypass" />
                <ActionIcon size="sm" variant="subtle" disabled={i === 0}
                  onClick={() => onMove(op.uid, -1)} aria-label="Move up">
                  <IconChevronUp size={14} />
                </ActionIcon>
                <ActionIcon size="sm" variant="subtle" disabled={i === ops.length - 1}
                  onClick={() => onMove(op.uid, 1)} aria-label="Move down">
                  <IconChevronDown size={14} />
                </ActionIcon>
                <ActionIcon size="sm" variant="subtle" color="red"
                  onClick={() => onRemove(op.uid)} aria-label="Remove">
                  <IconX size={14} />
                </ActionIcon>
              </Group>
            </Group>
          </Paper>
        );
      })}
    </Stack>
  );
}
