import { Anchor, Group, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconStethoscope, IconCircleCheck, IconBulb } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
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
 * Turn a note's `action` key into a one-click link to the page that already does
 * it, so the suggestion is actionable rather than just described. Pure/testable;
 * returns `null` for a note with no wired action (e.g. a reassurance/positive
 * note). `trim_border` opens the non-destructive editor on this run (where Trim
 * border lives); `calibration` opens the Calibration page (build master darks/
 * flats); `solve_help` opens Settings (the ASTAP star-database status). All are
 * read-only navigations — nothing is changed until the user acts.
 *
 * When the card is rendered *inside* the editor (`inEditor`), the `trim_border`
 * link would just point at the page the user is already on — and the "Trim
 * border" button is right there in the op list — so we drop that redundant
 * self-link and let the note text guide them to the button. The `calibration`
 * link still points off to the Calibration page, so it's kept.
 */
export function noteAction(
  action: string | null,
  safe: string,
  runId: number | null,
  inEditor = false,
): { label: string; href: string } | null {
  switch (action) {
    case "trim_border":
      // In the editor the Trim border button is already on-screen, so a link
      // back to this same page adds nothing — show the note text alone there.
      if (inEditor) return null;
      // Opening the editor needs a concrete run to edit.
      return runId != null
        ? { label: "Open the editor to trim the border →",
            href: `/targets/${safe}/edit/${runId}` }
        : null;
    case "calibration":
      return { label: "Set up master darks & flats →", href: "/calibration" };
    case "solve_help":
      // Most subs failed to plate-solve; Settings shows the ASTAP star-database
      // status and how to install it, which is what lets far more subs locate.
      return { label: "Check your star database in Settings →", href: "/settings" };
    default:
      return null;
  }
}

/**
 * "How's my stack?" — a small, plain-language health check on the target's
 * current stack. Answers the opaque "is this any good, and what next?" moment a
 * beginner hits after a stack finishes, using cues we already compute (the run's
 * stamped fields + the frames' QC metrics). Read-only suggestion, never a gate.
 * Renders nothing until the target has a genuine stack to grade.
 *
 * `inEditor` tunes the action links for the editor surface, where the user is
 * already on the page a `trim_border` note would otherwise link to (see
 * `noteAction`).
 */
export function StackHealthCard(
  { safe, runId, inEditor = false }: { safe: string; runId?: number; inEditor?: boolean },
) {
  const health = useQuery({
    queryKey: ["stack-health", safe, runId ?? null],
    queryFn: () => api.stackHealth(safe, runId),
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
          {notes.map((n, i) => {
            const act = noteAction(n.action, safe, data.run_id, inEditor);
            return (
              <Group key={i} gap={8} wrap="nowrap" align="flex-start">
                <ThemeIcon size={18} radius="xl" variant="light" color={noteColor(n.severity)}
                  style={{ flexShrink: 0, marginTop: 1 }}>
                  {n.severity === "good" ? <IconCircleCheck size={13} /> : <IconBulb size={13} />}
                </ThemeIcon>
                <Stack gap={2} style={{ minWidth: 0 }}>
                  <Text size="sm" c="dimmed">{n.message}</Text>
                  {act ? (
                    <Anchor component={Link} to={act.href} size="xs" fw={500}>
                      {act.label}
                    </Anchor>
                  ) : null}
                </Stack>
              </Group>
            );
          })}
        </Stack>
      </Group>
    </Paper>
  );
}
