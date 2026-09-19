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

/** The gain settings this guide should name: the target's own *distinct* gains
 *  when the backend sends them, the single value it has always sent otherwise.
 *
 *  The sibling of `darkSpecLengths`, and the argument is sharper here. A gain is
 *  a discrete **setting**, so a target shot at gain 80 one night and gain 200
 *  the next does not merely have a median no sub carries — 140 is a number the
 *  camera cannot be dialled to at all, printed under the words "at the same
 *  settings as your subs". */
export function darkSpecGains(spec: DarkSpec | null | undefined): number[] {
  if (!spec) return [];
  const set = (spec.gains ?? []).filter((g) => g != null && g >= 0);
  if (set.length > 0) return [...set].sort((a, b) => a - b);
  const { gain } = spec;
  return gain != null ? [gain] : [];
}

/** `[10, 30]` → `"10 s and 30 s"`; `[80]` → `"80"`. One joiner, so the two
 *  halves of the phrase are punctuated the same way. */
function joinParts(parts: string[]): string {
  if (parts.length <= 1) return parts.join("");
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/**
 * Format the target's own exposure/gain into the "match these numbers" phrase,
 * e.g. `"10 s at gain 80"` — or `"10 s and 30 s at gain 80 and 200"` for a
 * target shot at two lengths and two gains. Returns `null` when neither number
 * is known, so the guide falls back to generic wording instead of showing a
 * wrong/empty value. Pure/testable.
 */
export function formatDarkSpec(spec: DarkSpec | null | undefined): string | null {
  if (!spec) return null;
  const parts: string[] = [];
  const lengths = darkSpecLengths(spec).map(formatSeconds);
  if (lengths.length > 0) parts.push(joinParts(lengths));
  const gains = darkSpecGains(spec).map(
    (g) => (Number.isInteger(g) ? String(g) : g.toFixed(0)),
  );
  if (gains.length > 0) parts.push(`gain ${joinParts(gains)}`);
  if (parts.length === 0) return null;
  return parts.join(" at ");
}

/** The extra sentence a target shot at more than one *setting* needs: a dark
 *  only subtracts correctly from subs of its own exposure **and** its own gain,
 *  so two of either means two sets of darks.
 *
 *  Both axes in one sentence rather than two, because a reader who changed both
 *  between nights needs one instruction, not a pair that have to be combined —
 *  and because the guide sits under the owner's standing "extremely busy"
 *  complaint. Empty string on the ordinary target, which is every target until
 *  someone changes a setting between nights. */
export function darkSpecPerSettingNote(spec: DarkSpec | null | undefined): string {
  const lengths = darkSpecLengths(spec).length;
  const gains = darkSpecGains(spec).length;
  if (lengths < 2 && gains < 2) return "";
  if (lengths >= 2 && gains < 2) {
    return (
      ` You shot this target at ${lengths} different sub lengths, so it needs a set of `
      + `darks at each — one dark only matches subs of its own exposure.`
    );
  }
  if (gains >= 2 && lengths < 2) {
    return (
      ` You shot this target at ${gains} different gains, so it needs a set of `
      + `darks at each — a dark carries the gain-dependent readout pedestal, and `
      + `nothing rescales it.`
    );
  }
  return (
    ` You shot this target at ${lengths} different sub lengths and ${gains} different `
    + `gains, so it needs a set of darks for each combination you used — a dark only `
    + `matches subs of its own exposure and its own gain.`
  );
}

/**
 * "How to add darks" — the actionable how-to behind the app's existing "adding
 * darks would cut the speckle" advice. A beginner who's told darks help still
 * has no idea *how* to shoot them on a Seestar; this bridges that gap with three
 * plain steps and the target's own exposure/gain pre-filled ("shoot darks at the
 * same 10 s / gain 80 as your subs"). Static, jargon-free, self-contained; shown
 * as a collapsible disclosure beside the uncalibrated "How's my stack?" note.
 *
 * Its lead sentence used to call darks "the single biggest cleanup for a noisy
 * image" unconditionally, which is a fine thing to say about a noisy image and
 * the wrong thing to say directly under a note that has just told the reader
 * this picture's background measures clean. `backgroundClean` is that note's own
 * fact, threaded through rather than re-derived, so the two cannot hold
 * different opinions about one picture — the same reason the note reads the
 * measurement instead of guessing at it.
 */
export function DarksGuide(
  { spec, backgroundClean }: {
    spec?: DarkSpec | null;
    /** Whether the app has *measured* this picture's background and found it
     * clean (`StackHealth.background_clean`). Only `true` changes anything:
     * `false` and `undefined` — an older backend, or a picture nobody measured
     * — keep the general wording, which is the right thing to say when the
     * grain is unknown. */
    backgroundClean?: boolean | null;
  },
) {
  const [open, setOpen] = useState(false);
  const match = formatDarkSpec(spec);
  const step2 = match
    ? `Shoot about 20–30 dark frames at the same settings as your subs — ${match}.`
      + darkSpecPerSettingNote(spec)
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
            {backgroundClean
              // Deliberately says what darks *do* here rather than restating
              // that the background is clean. The note above already said that,
              // and on a mosaic it says it with a scope ("across most of it") —
              // sigma is one figure for the whole canvas, so a second
              // unqualified copy of the claim down here would be the very
              // over-claim v0.466.2 removed from the note. "Mostly hot pixels
              // rather than less grain" is true of every part of any canvas
              // once the sky is not dark-current-dominated: darks never reduce
              // shot noise, which is what the thin part of a mosaic has.
              ? "Darks record your camera's own warmth and noise so we can "
                + "subtract it — on this picture that mostly means hot pixels "
                + "rather than less grain."
              : "Darks record your camera's own warmth and noise so we can "
                + "subtract it — this is the single biggest cleanup for a "
                + "noisy image."}
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
