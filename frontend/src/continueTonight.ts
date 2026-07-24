// "Point here tonight" — of the targets you've *already started*, which single
// one is worth pointing the Seestar at tonight? Every other planning surface
// answers a different question: `/suggest` recommends brand-new showpieces you
// haven't shot, `/next-session` plans one target you pick, `/tonight` ranks
// visibility across the whole sky. None of them answers the beginner's actual
// mid-project question — "of the things I've already got going, where does
// tonight's clear sky pay off most?" — which today means opening every Target
// page and eyeballing goal-progress against tonight's altitude by hand.
//
// This picks that one target for them, from data the Dashboard already fetches:
// the `/tonight` plan (which owned targets are well-placed tonight, with their
// score + usable window) and each target's integration goal (from
// `/api/library-progress`). The rule is deliberately simple and honest — among
// your started targets that are shootable tonight *and* still benefit from more
// data, recommend the one closest to a finished picture, so "about 90 more
// minutes reaches your goal" becomes a concrete, satisfying nudge rather than a
// wall of catalog rows.

import type { NightPlan, PlannedTarget } from "./api/client";
import { integrationReadiness, type IntegrationReadiness } from "./readiness";

export interface TonightPick {
  target: PlannedTarget;
  // How close this target is to a clean image, judged against its goal (a
  // user-set one when supplied, else the per-type default). null when there's
  // no integration yet or the type is unknown *and* nothing to say — the target
  // can still be recommended, just without a progress line.
  readiness: IntegrationReadiness | null;
}

export interface ContinueTonightPlan {
  pick: TonightPick;
  // Up to `maxRunnersUp` dimmed alternatives, so a user who'd rather shoot
  // something else tonight sees the next-best owned targets at a glance.
  runnersUp: TonightPick[];
}

// User-set integration goals (seconds) keyed by target `safe` name, as returned
// by `/api/library-progress` (`goal_s`). Optional — when a target has no custom
// goal the per-type default (Galaxy 6 h, Nebula 4 h, …) is used instead.
export type GoalSecondsBySafe = Record<string, number | null | undefined>;

/**
 * Choose the single owned target to continue tonight (plus a couple of
 * runners-up), or null when there's nothing sensible to recommend.
 *
 * Returns null — so the caller renders nothing — when: the plan is missing/empty
 * or has no location, no target you've already started is well-placed tonight
 * (score > 0), or every such target already has *plenty* of integration (nothing
 * left to gain, so "continue" would be pointless — the "try something new" card
 * covers that case).
 *
 * Among the targets that survive that filter, the recommendation is the one
 * closest to a finished picture (highest readiness fraction), breaking ties by
 * tonight's observability score — a target you can nearly *finish* tonight beats
 * one you've barely begun. A target with no readiness figure (no integration or
 * an unknown type) sorts as "just started", so it never displaces a genuinely
 * close target but can still be picked when it's your only improvable option up
 * tonight.
 */
export function pickContinueTonight(
  plan: NightPlan | undefined | null,
  goalSecondsBySafe?: GoalSecondsBySafe,
  maxRunnersUp = 2,
): ContinueTonightPlan | null {
  const targets = plan?.targets;
  if (!targets || targets.length === 0) return null;

  // Owned (already-started) targets that are actually shootable tonight.
  const owned = targets.filter(
    (t) => t.already_targeted && !!t.target_safe && t.score > 0,
  );
  if (owned.length === 0) return null;

  const scored: TonightPick[] = owned.map((t) => {
    const goalSec = t.target_safe ? goalSecondsBySafe?.[t.target_safe] : null;
    const goalHours =
      typeof goalSec === "number" && Number.isFinite(goalSec) && goalSec > 0
        ? goalSec / 3600
        : null;
    const readiness = integrationReadiness(t.total_exposure_s ?? 0, t.type, goalHours);
    return { target: t, readiness };
  });

  // Drop the already-done ones: a target with "plenty" of integration has
  // nothing left to gain, so recommending it to *continue* would be wrong. If
  // that leaves nothing, the user has finished everything they've started up
  // tonight — say nothing rather than nudge them to over-integrate.
  const improvable = scored.filter(
    (s) => s.readiness == null || s.readiness.level !== "plenty",
  );
  if (improvable.length === 0) return null;

  improvable.sort((a, b) => {
    const fa = a.readiness?.fraction ?? 0;
    const fb = b.readiness?.fraction ?? 0;
    if (fb !== fa) return fb - fa; // closest to its goal first
    return b.target.score - a.target.score; // then best-placed tonight
  });

  const [pick, ...rest] = improvable;
  return { pick, runnersUp: rest.slice(0, Math.max(0, maxRunnersUp)) };
}
