import { Anchor, Button, Group, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";

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
  { cue: "too_green", label: "Too green", group: "Colour" },
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
 * eleven equal-weight buttons, which is the point of a feature meant to reduce
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
  { onRerun, safe, runId }: { onRerun: () => void; safe?: string; runId?: number },
) {
  const qc = useQueryClient();
  const scoped = safe != null && runId != null;
  // Query the run-scoped profile when we know the target, so the "why" note
  // reflects this archetype's taste on load; otherwise the library-wide profile.
  const prefsKey = scoped ? ["auto-prefs", safe, runId] : ["auto-prefs"];
  const prefs = useQuery({
    queryKey: prefsKey,
    queryFn: () =>
      scoped ? api.getRunAutoPreferences(safe!, runId!) : api.getAutoPreferences(),
  });
  const feedback = useMutation({
    // Pass the run context so the cue is scoped to this target's archetype
    // (galaxy/nebula/cluster) — taste learned on galaxies won't move clusters.
    mutationFn: (cue: string) =>
      api.sendAutoFeedback(cue, scoped ? { safe: safe!, runId: runId! } : undefined),
    onSuccess: (data) => {
      qc.setQueryData(prefsKey, data);
      notifications.show({
        message: "Thanks — Auto will lean that way for you", color: "violet",
      });
      onRerun();
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const reset = useMutation({
    mutationFn: () => api.resetAutoPreferences(),
    onSuccess: (data) => {
      qc.setQueryData(prefsKey, data);
      notifications.show({ message: "Auto reset to its data-driven default", color: "gray" });
      onRerun();
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const busy = feedback.isPending || reset.isPending;
  const note = prefs.data?.note ?? null;

  return (
    <Stack gap={4} mt={6}>
      <Text size="xs" fw={600}>How did Auto do? Tap what you'd change:</Text>
      <Group gap="sm" align="flex-start">
        {autoFeedbackGroups().map((g) => (
          <Stack key={g.group} gap={2}>
            <Text size="10px" c="dimmed" tt="uppercase" fw={600}>{g.group}</Text>
            <Group gap={4}>
              {g.chips.map((c) => (
                <Button key={c.cue} size="compact-xs" variant="default" radius="xl"
                  disabled={busy} onClick={() => feedback.mutate(c.cue)}>
                  {c.label}
                </Button>
              ))}
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
    </Stack>
  );
}
