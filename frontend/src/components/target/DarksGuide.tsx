import { Anchor, Collapse, List, Stack, Text } from "@mantine/core";
import { useState } from "react";
import type { DarkSpec } from "../../api/client";

/**
 * Format the target's own exposure/gain into the "match these numbers" phrase,
 * e.g. `"10 s at gain 80"`. Returns `null` when neither number is known, so the
 * guide falls back to generic wording instead of showing a wrong/empty value.
 * Pure/testable.
 */
export function formatDarkSpec(spec: DarkSpec | null | undefined): string | null {
  if (!spec) return null;
  const parts: string[] = [];
  const { exposure_s, gain } = spec;
  if (exposure_s != null && exposure_s > 0) {
    // Whole seconds read cleanest ("10 s"); keep one decimal for odd values.
    const secs = Number.isInteger(exposure_s) ? String(exposure_s) : exposure_s.toFixed(1);
    parts.push(`${secs} s`);
  }
  if (gain != null) {
    const g = Number.isInteger(gain) ? String(gain) : gain.toFixed(0);
    parts.push(`gain ${g}`);
  }
  if (parts.length === 0) return null;
  return parts.join(" at ");
}

/**
 * "How to add darks" — the actionable how-to behind the app's existing "adding
 * darks would cut the speckle" advice. A beginner who's told darks help still
 * has no idea *how* to shoot them on a Seestar; this bridges that gap with three
 * plain steps and the target's own exposure/gain pre-filled ("shoot darks at the
 * same 10 s / gain 80 as your subs"). Static, jargon-free, self-contained; shown
 * as a collapsible disclosure beside the uncalibrated "How's my stack?" note.
 */
export function DarksGuide({ spec }: { spec?: DarkSpec | null }) {
  const [open, setOpen] = useState(false);
  const match = formatDarkSpec(spec);
  const step2 = match
    ? `Shoot about 20–30 dark frames at the same settings as your subs — ${match}.`
    : "Shoot about 20–30 dark frames at the same exposure and gain as your subs.";

  return (
    <Stack gap={4}>
      <Anchor
        component="button"
        type="button"
        size="xs"
        fw={500}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? "Hide how to add darks" : "How to add darks →"}
      </Anchor>
      <Collapse in={open}>
        <Stack gap={6} pl={4}>
          <Text size="xs" c="dimmed">
            Darks record your camera's own warmth and noise so we can subtract it —
            this is the single biggest cleanup for a noisy image.
          </Text>
          <List type="ordered" size="xs" spacing={4} c="dimmed">
            <List.Item>
              Cap the scope (or cover the lens) so no light gets in — a dark is a
              photo of the dark.
            </List.Item>
            <List.Item>{step2}</List.Item>
            <List.Item>
              Drop the dark folder in (or point the Calibration page at it) —
              AstroStack builds the master dark and applies it to your next stack.
            </List.Item>
          </List>
        </Stack>
      </Collapse>
    </Stack>
  );
}
