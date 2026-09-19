import { useMemo } from "react";
import { Alert, Anchor, Text } from "@mantine/core";
import { Link } from "react-router-dom";
import { IconBulb } from "@tabler/icons-react";
import { nextBestMove, type NextBestMoveFraming } from "./nextBestMove";
import type { GoalDifficulty } from "../../readiness";
import { softerThanUsual } from "./softStars";
import type { GrainLevel } from "./grainProjection";

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
    fieldFulls,
    objectType,
    difficulty,
    grainVerdict,
    grainRegion,
    grainLevel,
    framing,
  }: {
    name: string;
    nFramesUsed: number | null | undefined;
    integrationS: number | null | undefined;
    nUnsolved: number | null | undefined;
    /** The target's stack runs newest-first (from `listStackRuns`) — used to
     * derive the relative soft-star signal. Optional; the tip degrades to the
     * non-soft ladder when it's missing. */
    runs?: { stack_fwhm_px?: number | null }[] | null;
    /** How many field-fulls of sky the stack's canvas covers
     * (`StackRun.field_fulls`), so the "how much have I got?" rungs are asked
     * of one part of a mosaic rather than of the whole raster. Optional — a
     * single field, and any caller without it, read exactly as before. */
    fieldFulls?: number | null;
    /** The catalogue object type (from the identify card), so the time rungs
     * are judged against the same per-type goal the readiness card next to
     * this one uses. Optional — omitted reads exactly as before. */
    objectType?: string | null;
    /** The target's vetted difficulty verdict (from the identify card), which
     * sharpens that same per-type goal. Optional — omitted reads exactly as
     * before. */
    difficulty?: GoalDifficulty;
    /** The run's own `grain_verdict` ("uneven" when a substantial part of its
     * canvas is thinner and grainier than the rest), so the well-done note
     * scopes its praise the way the "How's my stack?" panel below it scopes its
     * measurement. Optional — null/absent reads exactly as before. */
    grainVerdict?: string | null;
    /** The run's own `grain_region` ("panel" or "edge"), so the well-done note
     * never prescribes another night for a ragged edge no amount of shooting
     * evens out. Optional — null/absent reads as "panel", exactly as before. */
    grainRegion?: string | null;
    /** The measured grain level of the picture the readiness card beside this
     * one is describing (`cardGrainProjection(runs)?.level`), so the "add more
     * time" rung stops promising a cleaner background over a card that has just
     * measured the background clean. Optional — null/absent reads exactly as
     * before, and it never changes which rung fires. */
    grainLevel?: GrainLevel | null;
    /** The measured framing verdict for the same run (`useStackFraming`), so
     * the coaching line knows about the lever the framing note on this page is
     * naming and the two stop prescribing different next sessions. Optional —
     * absent, or any verdict but a badly-short `partial`, reads exactly as
     * before. */
    framing?: NextBestMoveFraming | null;
  },
) {
  const tip = useMemo(
    () =>
      nextBestMove({
        nFramesUsed,
        integrationS,
        nUnsolved,
        softStars: softerThanUsual(runs),
        fieldFulls,
        objectType,
        difficulty,
        grainVerdict,
        grainRegion,
        grainLevel,
        framing,
      }),
    [nFramesUsed, integrationS, nUnsolved, runs, fieldFulls, objectType,
     difficulty, grainVerdict, grainRegion, grainLevel, framing],
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
    <Alert color={color} variant="light" icon={<IconBulb size={18} />} title={title}
      data-testid="next-best-move">
      <Text size="sm">{tip.phrase}</Text>
      {tip.action ? (
        <Anchor component={Link} to={tip.action.href} size="xs" fw={500}>
          {tip.action.label}
        </Anchor>
      ) : null}
    </Alert>
  );
}
