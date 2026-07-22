import { Group, Text, ThemeIcon } from "@mantine/core";
import { IconArrowsHorizontal } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { noiseReductionBadge } from "./oneFrameVsStack";

/**
 * The concrete "stacking cut your noise ~N×" payoff, shown at the *moment a
 * beginner lands on a finished stack* — the Target result headline and the Jobs
 * "Process target" completion summary — instead of only when they dig into
 * History's before/after reveal.
 *
 * Reuses the shipped, tested `.../one-sub-vs-stack/noise` measurement (a
 * linear-domain background-noise σ ratio, ≈√N on a healthy weighted-mean stack)
 * and the pure `noiseReductionBadge` formatter. Shares the reveal card's query
 * key, so the two never double-measure the same run.
 *
 * Renders **nothing** when the ratio is missing/unmeasurable (an edited/older
 * run, or a linear/display-space export) or too small to be a compelling,
 * trustworthy story (< 1.5×) — a thin/gibberish stack is honestly reinforced by
 * its own "very few frames" warning instead of a weak number. Best-effort and
 * additive: a failed or null measurement just omits the line, never an error.
 */
export function StackNoiseBadge({
  safe,
  runId,
  nFrames,
}: {
  safe: string;
  runId: number;
  nFrames?: number | null;
}) {
  const noise = useQuery({
    // Same key as OneFrameVsStackCard so a run measured in one place is reused
    // in the other (and vice-versa) rather than measured twice.
    queryKey: ["one-sub-vs-stack-noise", safe, runId],
    queryFn: () => api.oneSubVsStackNoise(safe, runId),
    enabled: !!safe && Number.isFinite(runId),
    retry: false,
  });
  const badge = noiseReductionBadge(noise.data?.ratio, nFrames);
  if (!badge) return null;
  return (
    <Group gap={6} wrap="nowrap" data-testid="stack-noise-badge">
      <ThemeIcon size={20} radius="xl" variant="light" color="teal"
        style={{ flexShrink: 0 }}>
        <IconArrowsHorizontal size={13} />
      </ThemeIcon>
      <Text size="sm" fw={600} c="teal.6">{badge}</Text>
    </Group>
  );
}
