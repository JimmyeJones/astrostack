import { ActionIcon, Anchor, Badge, Group, Paper, Stack, Switch, Text, Tooltip } from "@mantine/core";
import { IconAlertTriangle, IconChevronDown, IconChevronUp, IconX } from "@tabler/icons-react";
import type { EditOp, OpInstance } from "../../api/client";
import { stageConflicts, type WrongStage } from "./stageConflicts";

const CONFLICT_MSG: Record<WrongStage, string> = {
  linear: "This runs best before the stretch (it expects linear, un-stretched data). "
    + "Below the stretch it works on display-space pixels and can misbehave.",
  nonlinear: "This runs best after the stretch (it works in display space). "
    + "Above the stretch it operates on linear data and can misbehave.",
};

/** The ordered operation pipeline. Reorder with the arrows, toggle to bypass,
 * click to select for editing, ✕ to remove. (Dependency-free; no drag lib.) */
export function OpList({ ops, specs, selected, onSelect, onMove, onToggle, onRemove, onFix }: {
  ops: OpInstance[];
  specs: Record<string, EditOp>;
  selected: string | null;
  onSelect: (uid: string) => void;
  onMove: (uid: string, dir: -1 | 1) => void;
  onToggle: (uid: string) => void;
  onRemove: (uid: string) => void;
  onFix?: (uid: string) => void;
}) {
  const conflicts = stageConflicts(ops, specs);
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
                <div style={{ minWidth: 0 }}>
                  <Group gap={6} wrap="nowrap">
                    <Text size="sm" fw={active ? 600 : 400} lineClamp={1}>
                      {spec?.label ?? op.id}
                    </Text>
                    {spec?.heavy ? (
                      <Tooltip
                        label="This op is slow to render, so the live preview updates after a short pause when you change its settings — it's not stuck."
                        multiline w={240} withArrow>
                        <Badge size="xs" variant="light" color="grape"
                          style={{ flexShrink: 0, cursor: "help" }}>
                          slower preview
                        </Badge>
                      </Tooltip>
                    ) : null}
                  </Group>
                  {spec?.help ? (
                    <Text size="10px" c="dimmed" lineClamp={1}>{spec.help}</Text>
                  ) : null}
                  {conflicts[op.uid] ? (
                    <Group gap={4} wrap="nowrap" mt={2}>
                      <Tooltip label={CONFLICT_MSG[conflicts[op.uid]]} multiline w={240} withArrow>
                        <Group gap={2} wrap="nowrap" style={{ cursor: "help" }}>
                          <IconAlertTriangle size={12} color="var(--mantine-color-orange-6)" />
                          <Text size="10px" c="orange.6">
                            {conflicts[op.uid] === "linear"
                              ? "should be before the stretch"
                              : "should be after the stretch"}
                          </Text>
                        </Group>
                      </Tooltip>
                      {onFix ? (
                        <Anchor component="button" type="button" size="10px" c="orange.6"
                          onClick={(e) => { e.stopPropagation(); onFix(op.uid); }}>
                          Fix
                        </Anchor>
                      ) : null}
                    </Group>
                  ) : null}
                </div>
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
