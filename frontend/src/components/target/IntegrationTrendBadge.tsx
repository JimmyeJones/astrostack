import { useMemo } from "react";
import { Alert, Text } from "@mantine/core";
import { IconChartLine } from "@tabler/icons-react";
import { integrationTrend } from "./integrationTrend";
import type { NextBestMoveKind } from "./nextBestMove";

/** Coaching kinds that nudge the user to add more *time* to this target. When
 * "next best move" is showing one of these, a "more time won't help" plateau
 * verdict would directly contradict it, so we stay silent and let the actionable
 * add-time nudge win. */
const ADD_TIME_KINDS: ReadonlySet<NextBestMoveKind> = new Set(["integration", "good"]);

/**
 * "📉 About as clean as your sky allows" — a compact, plain-language read on the
 * Target page telling a beginner when a target has *plateaued* (gone
 * sky-limited): its noise has stopped falling even as they add integration time,
 * so more subs won't help it much. That's exactly the moment to move on to a
 * fresh target, and the Target page — beside the "next best move" coaching — is
 * where they decide whether to revisit this one.
 *
 * Reuses the already-tested `integrationTrend(runs)` helper (no new logic). It
 * deliberately surfaces **only the "plateaued" verdict here**: the
 * "improving"/"slowing" verdicts broadly agree with the existing add-time
 * coaching, so showing them on the Target page would just duplicate it — they
 * stay on the History "Noise trend" card.
 *
 * Self-hiding, so it's safe to drop in unconditionally beside the finished
 * picture. It renders nothing when:
 *   - there isn't enough measured history to judge the trend (`integrationTrend`
 *     returns null), or the verdict isn't "plateaued"; or
 *   - the "next best move" coaching is currently nudging *add more time*
 *     (`coachKind` is "integration" or "good") — the two must never contradict.
 *
 * `runs` must be the target's stack runs (order doesn't matter — the trend reads
 * by integration time, not chronology).
 */
export function IntegrationTrendBadge(
  {
    runs,
    coachKind,
  }: {
    runs?: { total_exposure_s?: number | null; noise_sigma?: number | null }[] | null;
    /** The kind of tip `NextBestMoveBadge` is currently showing (or null when it
     * is hidden), so the plateau verdict can defer to an add-time nudge. */
    coachKind?: NextBestMoveKind | null;
  },
) {
  const trend = useMemo(() => integrationTrend(runs), [runs]);
  if (!trend || trend.level !== "plateaued") return null;
  if (coachKind != null && ADD_TIME_KINDS.has(coachKind)) return null;

  return (
    <Alert
      color="orange"
      variant="light"
      icon={<IconChartLine size={18} />}
      title="📉 About as clean as your sky allows"
    >
      <Text size="sm">{trend.sentence}</Text>
    </Alert>
  );
}
