import { Group, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconStethoscope, IconCircleCheck, IconBulb } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api, type HealthNote } from "../api/client";

// The card never dumps a wall of warnings — it shows only the top one or two
// notes the backend already ranked best-first (actionable next-steps before
// reassurance and the positive summary).
const MAX_NOTES = 2;

/** The notes to actually render: the top few, best-first. Pure/testable. */
export function visibleNotes(notes: HealthNote[]): HealthNote[] {
  return notes.slice(0, MAX_NOTES);
}

/** Mantine colour for a note's severity — gentle, never alarming. */
export function noteColor(severity: string): string {
  return severity === "good" ? "teal" : "blue";
}

/**
 * "How's my stack?" — a small, plain-language health check on the target's
 * current stack. Answers the opaque "is this any good, and what next?" moment a
 * beginner hits after a stack finishes, using cues we already compute (the run's
 * stamped fields + the frames' QC metrics). Read-only suggestion, never a gate.
 * Renders nothing until the target has a genuine stack to grade.
 */
export function StackHealthCard({ safe }: { safe: string }) {
  const health = useQuery({
    queryKey: ["stack-health", safe],
    queryFn: () => api.stackHealth(safe),
    enabled: !!safe,
  });
  const data = health.data;
  if (!data || data.notes.length === 0) return null;
  const notes = visibleNotes(data.notes);
  return (
    <Paper withBorder p="sm" radius="md" mt="xs">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <IconStethoscope size={22} style={{ flexShrink: 0, marginTop: 2 }}
          color="var(--mantine-color-teal-5)" />
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Text size="sm" fw={500}>How's my stack?</Text>
          {notes.map((n, i) => (
            <Group key={i} gap={8} wrap="nowrap" align="flex-start">
              <ThemeIcon size={18} radius="xl" variant="light" color={noteColor(n.severity)}
                style={{ flexShrink: 0, marginTop: 1 }}>
                {n.severity === "good" ? <IconCircleCheck size={13} /> : <IconBulb size={13} />}
              </ThemeIcon>
              <Text size="sm" c="dimmed">{n.message}</Text>
            </Group>
          ))}
        </Stack>
      </Group>
    </Paper>
  );
}
