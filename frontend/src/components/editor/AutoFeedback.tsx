import { Anchor, Button, Group, Stack, Text, Tooltip } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type AutoPreferences } from "../../api/client";

/** Adaptive Auto — one-tap feedback on the one-click Auto result.
 *
 * The owner taps what they'd change ("too dark", "over-sharpened", …); each tap
 * records a small, bounded bias into a per-library taste profile, and Auto is
 * immediately re-run so the preview reflects the shift. A plain-language "why"
 * note explains how Auto is leaning, with a one-tap Reset back to the neutral,
 * data-driven default — so the taste never drifts silently and is fully
 * reversible. An unset profile behaves exactly as today's Auto.
 */
export interface AutoFeedbackChip {
  cue: string;
  label: string;
  /** Which aspect of the picture this chip is about. Presentation only — the
   * cue a tap sends is unchanged — but it turns a wall of equal-weight buttons
   * into a handful of small "what would you change?" decisions. */
  group: string;
}

export const AUTO_FEEDBACK_CHIPS: AutoFeedbackChip[] = [
  { cue: "too_dark", label: "Too dark", group: "Brightness" },
  { cue: "too_bright", label: "Too bright", group: "Brightness" },
  { cue: "too_soft", label: "Too soft", group: "Sharpness" },
  { cue: "over_sharpened", label: "Over-sharpened", group: "Sharpness" },
  { cue: "too_noisy", label: "Too noisy", group: "Grain" },
  { cue: "over_smoothed", label: "Over-smoothed", group: "Grain" },
  { cue: "undersaturated", label: "Colours too weak", group: "Colour" },
  { cue: "too_saturated", label: "Colours too strong", group: "Colour" },
  // The green pair. "Too green" asks for a stronger green-cast removal (SCNR);
  // "Too magenta" eases it back off. The reverse chip is what makes the pair a
  // pair: without it three "Too green" taps saturated the bias at full removal
  // and only Reset — which throws away *every* learned taste — could undo them.
  // "Magenta" is the word the sky-cast read-out on this same screen already
  // uses for the symptom ("Sky background has a magenta cast"), which is what
  // over-strong SCNR produces.
  { cue: "too_green", label: "Too green", group: "Colour" },
  { cue: "too_magenta", label: "Too magenta", group: "Colour" },
  // The bright-core pair. "Core blown out" asks Auto to hold the highlights back
  // (it starts off); "Core looks flat" walks that back toward off again.
  { cue: "core_clipped", label: "Core blown out", group: "Bright core" },
  { cue: "core_flat", label: "Core looks flat", group: "Bright core" },
];

/** Cluster the chips by what they're about, in first-appearance order. Pure.
 *
 * Every cue keeps its own button and every walk-back chip stays one tap away,
 * side by side with the chip that got the user there — hiding the reverse
 * behind a second interaction is what would make the feature feel one-way.
 * Grouping only changes how the row *reads*: five small questions instead of
 * twelve equal-weight buttons, which is the point of a feature meant to reduce
 * decisions rather than add them.
 */
export function autoFeedbackGroups(
  chips: AutoFeedbackChip[] = AUTO_FEEDBACK_CHIPS,
): { group: string; chips: AutoFeedbackChip[] }[] {
  const out: { group: string; chips: AutoFeedbackChip[] }[] = [];
  for (const chip of chips) {
    const existing = out.find((g) => g.group === chip.group);
    if (existing) existing.chips.push(chip);
    else out.push({ group: chip.group, chips: [chip] });
  }
  return out;
}

export function AutoFeedback(
  { onRerun, safe, runId, autoCrop }: {
    onRerun: () => void; safe?: string; runId?: number;
    /** The editor's per-run "let Auto trim the ragged border?" override, or
     * `undefined` to follow the saved setting. It travels with both requests
     * below because the archetype this taste is filed under has to be the one
     * Auto keys on, and with the trim off Auto keys on the whole canvas. */
    autoCrop?: boolean;
  },
) {
  const qc = useQueryClient();
  const scoped = safe != null && runId != null;
  // Query the run-scoped profile when we know the target, so the "why" note
  // reflects this archetype's taste on load; otherwise the library-wide profile.
  // `autoCrop` is part of the key: flipping the border-trim switch can change the
  // archetype, so a cached note taken under the other setting is the wrong note.
  const prefsKey = scoped
    ? ["auto-prefs", safe, runId, autoCrop] : ["auto-prefs"];
  const prefs = useQuery({
    queryKey: prefsKey,
    queryFn: () =>
      scoped
        ? api.getRunAutoPreferences(safe!, runId!, autoCrop)
        : api.getAutoPreferences(),
  });
  const feedback = useMutation({
    // Pass the run context so the cue is scoped to this target's archetype
    // (galaxy/nebula/cluster) — taste learned on galaxies won't move clusters.
    mutationFn: (cue: string) =>
      api.sendAutoFeedback(
        cue, scoped ? { safe: safe!, runId: runId! } : undefined, autoCrop),
    onSuccess: (data, cue) => {
      // The mark this chip was *already* carrying, read off the snapshot the tap
      // was made against. It is the other half of the answer below, and it has
      // to be read before `setQueryData` lands.
      const markedBefore = prefs.data?.inert_cues?.[cue] ?? null;
      // Keep the marks we already have while the refresh below is in flight: the
      // POST answers about the *profile* and leaves `inert_cues` empty, so taking
      // its value literally would unmark every chip for a moment and then mark
      // them again, which reads as a glitch rather than as an update.
      qc.setQueryData(prefsKey, (old: AutoPreferences | undefined) => ({
        ...data,
        inert_cues: old?.inert_cues ?? {},
      }));
      // A tap that cannot move this picture gets told so, instead of the thanks.
      // TWO sources, because the server can answer one of the two mechanisms for
      // free and not the other:
      //   * `limit_note` (`editor._feedback_limit_note`) is the tap whose dead
      //     end is in the **store** — the taste was already at its cap, so the
      //     effective biases did not move and the recipe is provably identical.
      //     That covers the fourth identical tap on any chip, and "Core looks
      //     flat" from the *first* tap on a picture Auto is not holding back.
      //   * the chip's own **mark** is the tap whose dead end is in the
      //     **picture**: the bias moves, but Auto's measured value already sits
      //     at the end of that parameter's range, so the clamp swallows it. The
      //     POST cannot see that without measuring the proxy (the cost argument
      //     behind v0.492.54), and it does not have to — the row was given the
      //     answer on load and the chip is wearing it.
      // Without the second source a marked chip still answered "Thanks — Auto
      // will lean that way for you", which is the exact sentence v0.492.53
      // exists to stop, one mechanism over. Found by the dogfood's own Auto pass
      // (v0.492.55) on its first working run.
      // Nothing to re-run in either case — the recipe Auto would rebuild is
      // byte-for-byte the one on screen — so the rebuild is skipped.
      const limit = data.limit_note ?? markedBefore;
      notifications.show(
        limit
          ? { message: limit, color: "gray" }
          : { message: "Thanks — Auto will lean that way for you", color: "violet" },
      );
      if (!limit) onRerun();
      // Which chips are dead is a property of the *picture plus the profile*, and
      // the tap just moved the profile: a third "too dark" can be the one that
      // takes the stretch target to the end of its range, which kills the chip
      // that was alive a moment ago. The POST deliberately doesn't measure the
      // picture (that is this feature's whole cost argument), so refresh the
      // run-scoped read in the background — the line above has already shown the
      // owner the up-to-date note.
      if (scoped) void qc.invalidateQueries({ queryKey: prefsKey });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const reset = useMutation({
    mutationFn: () => api.resetAutoPreferences(),
    onSuccess: (data) => {
      qc.setQueryData(prefsKey, (old: AutoPreferences | undefined) => ({
        ...data,
        inert_cues: old?.inert_cues ?? {},
      }));
      notifications.show({ message: "Auto reset to its data-driven default", color: "gray" });
      onRerun();
      // Clearing the taste un-saturates every bias, so a chip that was dead
      // because the stored taste had nowhere to go is alive again. Same reason
      // as the feedback refresh above.
      if (scoped) void qc.invalidateQueries({ queryKey: prefsKey });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const busy = feedback.isPending || reset.isPending;
  const note = prefs.data?.note ?? null;
  // Recency decay eases an unreinforced taste back toward Auto's measured
  // default. Say so when it has actually moved something — including when it has
  // moved *everything*, which is the case that would otherwise look like the
  // "why Auto shifted" note silently disappearing.
  const fadeNote = prefs.data?.fade_note ?? null;
  // `{cue: why}` for the chips that cannot move *this* picture — the server
  // measured it (`editor._run_inert_cue_hints`), because the answer depends on
  // where Auto's measured value sits in that parameter's range, which only the
  // engine knows. Marked, never removed or disabled: the taste is library-wide,
  // so the tap still teaches Auto for the owner's other targets, and each
  // sentence says exactly that. `{}` whenever there is no picture to ask about.
  const inert = prefs.data?.inert_cues ?? {};
  const inertCount = Object.keys(inert).length;

  return (
    <Stack gap={4} mt={6}>
      <Text size="xs" fw={600}>How did Auto do? Tap what you'd change:</Text>
      <Group gap="sm" align="flex-start">
        {autoFeedbackGroups().map((g) => (
          <Stack key={g.group} gap={2}>
            <Text size="10px" c="dimmed" tt="uppercase" fw={600}>{g.group}</Text>
            <Group gap={4}>
              {g.chips.map((c) => {
                const hint = inert[c.cue];
                const chip = (
                  <Button key={c.cue} size="compact-xs" variant="default" radius="xl"
                    disabled={busy} onClick={() => feedback.mutate(c.cue)}
                    // Dimmed, not disabled or hidden. A disabled chip would take
                    // away the one thing the tap still does (teach the
                    // library-wide taste) and a hidden one would make the pair
                    // look one-way, which is the bug v0.492.52 fixed.
                    c={hint ? "dimmed" : undefined}
                    opacity={hint ? 0.55 : undefined}>
                    {c.label}
                  </Button>
                );
                return hint
                  ? (
                    <Tooltip key={c.cue} label={hint} multiline w={260}
                      withArrow position="top" events={{ hover: true, focus: true, touch: true }}>
                      {chip}
                    </Tooltip>
                  )
                  : chip;
              })}
            </Group>
          </Stack>
        ))}
      </Group>
      {note ? (
        <Text size="10px" c="dimmed" mt={2}>
          {note}{" "}
          <Anchor component="button" type="button" inherit
            onClick={() => reset.mutate()} disabled={busy}>
            Reset
          </Anchor>
        </Text>
      ) : null}
      {inertCount ? (
        // The legend for the dimming, because a hover tooltip is not an
        // explanation on a touch screen and a faded chip with no caption reads as
        // broken. Says both halves: it won't move *this* picture, and the tap is
        // still worth making.
        <Text size="10px" c="dimmed">
          Faded chips can’t change this picture — Auto is already at its limit
          there — but tapping still teaches Auto for your other pictures.
        </Text>
      ) : null}
      {fadeNote ? <Text size="10px" c="dimmed">{fadeNote}</Text> : null}
    </Stack>
  );
}
