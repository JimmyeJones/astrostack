import { useMemo } from "react";
import { Alert, Anchor, Text } from "@mantine/core";
import { IconChartLine } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { integrationTrend } from "./integrationTrend";
import type { NextBestMoveKind } from "./nextBestMove";
import { api } from "../../api/client";
import { describeSuggestion, suggestionHeading } from "../suggestTargets";

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
 *
 * **It also names a target to point at instead.** The verdict's last sentence
 * has always ended on "a brighter target will do more than extra time on this
 * one" and then left the beginner to work out which — while the planner that
 * answers exactly that has been sitting on the Dashboard ("Try something new
 * tonight") and on the Tonight page all along. So when the plateau is on screen
 * it asks `/api/plan/suggest` for the best showpiece they haven't shot yet and
 * names it, with the same observability line that card prints. The request is
 * `enabled` on the verdict, not on the page — an ordinary target never issues it
 * — and it shares the Dashboard card's query key and stale time, so a user who
 * has just come from the Dashboard pays nothing at all. Everything about it
 * self-hides: no location set, no dark window, nothing new well-placed, or a
 * failed/older backend all leave the verdict exactly as it was.
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
  // Decided before the query so the two cannot disagree about whether the
  // verdict is up: the suggestion is a footnote to the sentence, and asking for
  // one on a target that isn't showing the sentence would be a request nobody
  // ever sees the answer to.
  const showing = trend?.level === "plateaued"
    && !(coachKind != null && ADD_TIME_KINDS.has(coachKind));
  const suggest = useQuery({
    queryKey: ["suggest-targets"],
    queryFn: () => api.suggestTargets(),
    staleTime: 60_000,
    enabled: showing,
  });

  if (!trend || !showing) return null;

  // Best-first, so the head of the list is the planner's own pick. Anything
  // short of one real suggestion leaves the verdict as it was.
  const pick = suggest.data?.suggestions?.[0] ?? null;

  return (
    <Alert
      color="orange"
      variant="light"
      icon={<IconChartLine size={18} />}
      title="📉 About as clean as your sky allows"
    >
      <Text size="sm">{trend.sentence}</Text>
      {pick ? (
        <Text size="sm" mt={8}>
          Try <Text span fw={600}>{suggestionHeading(pick)}</Text> on your next clear
          night — {describeSuggestion(pick)}{" "}
          <Anchor component={Link} to="/tonight">See what else is up →</Anchor>
        </Text>
      ) : null}
    </Alert>
  );
}
