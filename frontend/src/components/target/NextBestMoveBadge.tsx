import { useMemo } from "react";
import { Alert, Text } from "@mantine/core";
import { IconBulb } from "@tabler/icons-react";
import { nextBestMove } from "./nextBestMove";
import { softerThanUsual } from "./softStars";

/**
 * "💡 To make this even better" — a single calm, plain-language line on the
 * finished-result card naming the *one* highest-leverage thing that would most
 * improve this target next time (get more subs to plate-solve / add more subs /
 * add more time), or a short encouraging note when the result is already good.
 *
 * It translates the app's honest-but-scattered numbers (frames used, unsolved
 * subs, integration time) into the gentle "do this next" coaching a beginner
 * most lacks — one tip, never a dashboard.
 *
 * Self-hiding: renders nothing when there's no finished stack to advise on, when
 * the inputs are missing, or when the result is already deep and healthy — so
 * it's safe to drop in unconditionally beside the finished picture. The caller
 * suppresses it while the louder thin-stack warning is showing, so the two never
 * duplicate the "add more subs" nudge.
 */
export function NextBestMoveBadge(
  {
    name,
    nFramesUsed,
    integrationS,
    nUnsolved,
    runs,
  }: {
    name: string;
    nFramesUsed: number | null | undefined;
    integrationS: number | null | undefined;
    nUnsolved: number | null | undefined;
    /** The target's stack runs newest-first (from `listStackRuns`) — used to
     * derive the relative soft-star signal. Optional; the tip degrades to the
     * non-soft ladder when it's missing. */
    runs?: { stack_fwhm_px?: number | null }[] | null;
  },
) {
  const tip = useMemo(
    () =>
      nextBestMove({
        nFramesUsed,
        integrationS,
        nUnsolved,
        softStars: softerThanUsual(runs),
      }),
    [nFramesUsed, integrationS, nUnsolved, runs],
  );
  if (!tip) return null;

  // A good result is a warm blue "nice work"; an actionable lever is a neutral
  // teal nudge — calm either way, never an error colour.
  const color = tip.kind === "good" ? "blue" : "teal";
  const title =
    tip.kind === "good"
      ? `💡 Nice work on ${name}`
      : `💡 To make your ${name} even better`;
  return (
    <Alert color={color} variant="light" icon={<IconBulb size={18} />} title={title}>
      <Text size="sm">{tip.phrase}</Text>
    </Alert>
  );
}
