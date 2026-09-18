import { Anchor, Collapse, List, Stack, Text } from "@mantine/core";
import { useState } from "react";
import type { DarkSpec } from "../../api/client";

/** `10` → `"10 s"`; whole seconds read cleanest, odd values keep one decimal. */
function formatSeconds(value: number): string {
  return `${Number.isInteger(value) ? String(value) : value.toFixed(1)} s`;
}

/** The sub lengths this guide should name: the target's own *distinct* lengths
 *  when the backend sends them, the median it has always sent otherwise.
 *
 *  A target is one **folder**, never one exposure — shoot it at 10 s one night
 *  and 30 s the next and the median is 20 s, which this guide would then offer
 *  under the words "at the same settings as your subs". */
export function darkSpecLengths(spec: DarkSpec | null | undefined): number[] {
  if (!spec) return [];
  const set = (spec.exposures_s ?? []).filter((e) => e != null && e > 0);
  if (set.length > 0) return [...set].sort((a, b) => a - b);
  const { exposure_s } = spec;
  return exposure_s != null && exposure_s > 0 ? [exposure_s] : [];
}

/**
 * Format the target's own exposure/gain into the "match these numbers" phrase,
 * e.g. `"10 s at gain 80"` — or `"10 s and 30 s at gain 80"` for a target shot
 * at two lengths. Returns `null` when neither number is known, so the guide
 * falls back to generic wording instead of showing a wrong/empty value.
 * Pure/testable.
 */
export function formatDarkSpec(spec: DarkSpec | null | undefined): string | null {
  if (!spec) return null;
  const parts: string[] = [];
  const lengths = darkSpecLengths(spec).map(formatSeconds);
  if (lengths.length === 1) {
    parts.push(lengths[0]);
  } else if (lengths.length > 1) {
    parts.push(`${lengths.slice(0, -1).join(", ")} and ${lengths[lengths.length - 1]}`);
  }
  const { gain } = spec;
  if (gain != null) {
    const g = Number.isInteger(gain) ? String(gain) : gain.toFixed(0);
    parts.push(`gain ${g}`);
  }
  if (parts.length === 0) return null;
  return parts.join(" at ");
}

/** The extra sentence a target shot at more than one sub length needs: one dark
 *  only subtracts correctly from subs of its own exposure, so two lengths means
 *  two sets. Empty string on the ordinary single-length target, which is every
 *  target until someone changes their sub length between nights. */
export function darkSpecPerLengthNote(spec: DarkSpec | null | undefined): string {
  const n = darkSpecLengths(spec).length;
  if (n < 2) return "";
  return (
    ` You shot this target at ${n} different sub lengths, so it needs a set of `
    + `darks at each — one dark only matches subs of its own exposure.`
  );
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
      + darkSpecPerLengthNote(spec)
    : "Shoot about 20–30 dark frames at the same exposure and gain as your subs.";

  return (
    <Stack gap={4}>
      <Anchor
        component="button"
        type="button"
        size="xs"
        fw={500}
        // A `component="button"` anchor is a real <button>, and a Stack stretches
        // its children — so this one filled the column and took the browser's
        // centred button text with it, leaving the only centred line in an
        // otherwise left-aligned note (measured 707 px wide, `text-align: center`).
        // Hugging its own text puts it back in the column with its siblings.
        style={{ alignSelf: "flex-start" }}
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
