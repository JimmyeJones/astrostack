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
export const AUTO_FEEDBACK_CHIPS: { cue: string; label: string }[] = [
  { cue: "too_dark", label: "Too dark" },
  { cue: "too_bright", label: "Too bright" },
  { cue: "too_soft", label: "Too soft" },
  { cue: "over_sharpened", label: "Over-sharpened" },
  { cue: "too_noisy", label: "Too noisy" },
  { cue: "over_smoothed", label: "Over-smoothed" },
  { cue: "undersaturated", label: "Colours too weak" },
  { cue: "too_saturated", label: "Colours too strong" },
  { cue: "too_green", label: "Too green" },
];

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
      <Group gap={4}>
        {AUTO_FEEDBACK_CHIPS.map((c) => (
          <Button key={c.cue} size="compact-xs" variant="default" radius="xl"
            disabled={busy} onClick={() => feedback.mutate(c.cue)}>
            {c.label}
          </Button>
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
