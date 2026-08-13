// "Is it enough yet?" — judge a target's accumulated integration against a sane
// per-object-type goal and phrase a plain-language readiness verdict. Purely
// offline: it turns data the Target page already has (accepted-sub exposure
// total + the catalog object type from the identify card) into an answer to a
// beginner's most common uncertainty on the stack→result path — "do I have
// enough subs for a clean image, or should I keep shooting this target?" The
// goal is a *suggestion, never a gate* (nothing here blocks stacking).

import {
  clearNightsFromPace, FINISH_FIRST_MAX_NIGHTS, nightWord,
} from "./components/clearNights";
import { formatIntegration } from "./format";
import { objectTypeBucket, type TypeBucket } from "./tonight";

// Suggested total-integration goals (hours) by friendly object type. Galaxies
// and faint diffuse nebulae reward long integration; bright open/globular
// clusters need far less. The coarse buckets can't tell a bright emission
// nebula from a faint one, so Nebula sits at a middle-ground 4 h. Unknown /
// unclassified targets get the same sensible mid-range default so a target with
// no catalog match still gets a rough steer rather than nothing. These are
// deliberately gentle round numbers — a rough "enough for a clean image",
// not a precise SNR target.
const GOAL_HOURS: Record<TypeBucket, number> = {
  Galaxy: 6,
  Nebula: 4,
  Cluster: 1.5,
  Other: 4,
};

export type ReadinessLevel = "starting" | "solid" | "close" | "plenty";

export interface IntegrationReadiness {
  bucket: TypeBucket;
  goalHours: number;
  // True when goalHours came from a user-set goal rather than the per-type
  // default — lets the card label it "your goal" instead of "goal".
  customGoal: boolean;
  hours: number;
  // hours / goalHours clamped to [0, 1] — ready to drive a progress bar.
  fraction: number;
  level: ReadinessLevel;
  // A plain-language one-liner, e.g. "1.8 h of ~4 h — a solid start; …".
  verdict: string;
}

// The goal as a compact figure: "6", "4", "1.5" (trailing ".0" trimmed), for a
// "~N h" phrasing.
function fmtGoal(h: number): string {
  return Number.isInteger(h) ? `${h}` : `${h.toFixed(1)}`;
}

// Judge accumulated integration against a goal. `type` is the catalog object
// type (from the identify card) or null/empty when the target isn't recognised;
// `exposureSeconds` is the accepted-sub total the target already reports. When
// `goalHoursOverride` is a positive number the user has set their own goal for
// this target and it wins over the per-type default (Galaxy 6 h, …). Returns
// null when there's no integration yet — nothing useful to say — so the caller
// can simply render nothing.
export function integrationReadiness(
  exposureSeconds: number,
  type: string | null | undefined,
  goalHoursOverride?: number | null,
): IntegrationReadiness | null {
  if (!Number.isFinite(exposureSeconds) || exposureSeconds <= 0) return null;
  const bucket = objectTypeBucket(type);
  const customGoal =
    typeof goalHoursOverride === "number" &&
    Number.isFinite(goalHoursOverride) &&
    goalHoursOverride > 0;
  const goalHours = customGoal ? goalHoursOverride! : GOAL_HOURS[bucket];
  const hours = exposureSeconds / 3600;
  const ratio = hours / goalHours;
  const fraction = Math.max(0, Math.min(1, ratio));

  let level: ReadinessLevel;
  let phrase: string;
  if (ratio < 0.25) {
    level = "starting";
    phrase = "a good start — more time pulls out fainter detail";
  } else if (ratio < 0.75) {
    level = "solid";
    phrase = "a solid start — keep going to pull out fainter detail";
  } else if (ratio < 1) {
    level = "close";
    phrase = "nearly there — a little more will really finish it off";
  } else {
    level = "plenty";
    phrase = "plenty for a clean image of this target";
  }

  const so_far = formatIntegration(exposureSeconds);
  const verdict =
    level === "plenty"
      ? `${so_far} — ${phrase}.`
      : `${so_far} of ~${fmtGoal(goalHours)} h — ${phrase}.`;

  return { bucket, goalHours, customGoal, hours, fraction, level, verdict };
}

// The honest √N truth behind "should I keep shooting?": stacking background
// noise falls as 1/√(integration time), so every extra hour buys progressively
// less. From the accumulated integration alone we can say — in plain words and
// an honest number — how much more noise one more clear hour would remove, so a
// beginner knows whether it's worth staying out. This is *goal-independent* (the
// physics doesn't care about the per-type goal), so it complements the goal
// verdict rather than repeating it: the goal answers "how far toward a nice
// image?"; this answers "does another hour still pay off?". Returns null when
// there's no integration yet, or when the target is so deeply integrated that a
// single extra hour changes nothing worth mentioning (nothing useful to add).
export function noiseReductionHint(exposureSeconds: number): string | null {
  if (!Number.isFinite(exposureSeconds) || exposureSeconds <= 0) return null;
  // Adding Δ=1 h of integration scales the stack's background noise by
  // √(T/(T+Δ)); the fractional *reduction* is 1 − that. Rounded to a whole
  // percent for a plain, honest figure ("about N% more").
  const oneHour = 3600;
  const cutPct = Math.round(
    (1 - Math.sqrt(exposureSeconds / (exposureSeconds + oneHour))) * 100,
  );
  // Past ~40 h a single extra hour rounds below 1% — say nothing rather than
  // print "about 0%".
  if (cutPct <= 0) return null;

  let tail: string;
  if (cutPct >= 20) {
    tail = "you're on the steep part of the curve — worth staying out for.";
  } else if (cutPct >= 9) {
    tail = "diminishing returns are setting in.";
  } else {
    tail = "you're well past the steep part — a clean place to stop.";
  }
  return `Another clear hour would cut background noise about ${cutPct}% more — ${tail}`;
}

// A compact hint for a target already in the library, for the Tonight planner's
// "add more to what you're shooting" rows: nudge the user toward starting
// something new once a target has close-to / more-than its suggested goal, and
// stay quiet (null) while it's still worth topping up (the row's integration
// figure already implies "keep going"). Caller supplies the accepted-sub
// exposure total + catalog type for one already-targeted row, plus that
// target's user-set goal in **hours** when it has one — a goal the owner set
// deliberately has to win here exactly as it does on the Target page and the
// Dashboard overview, or the planner tells them to move on from a target they
// have told the app they want more of.
export function readinessRowHint(
  exposureSeconds: number,
  type: string | null | undefined,
  goalHoursOverride?: number | null,
): { label: string; color: string } | null {
  const r = integrationReadiness(exposureSeconds, type, goalHoursOverride);
  if (!r) return null;
  if (r.level === "plenty") return { label: "Plenty — try something new", color: "green" };
  if (r.level === "close") return { label: "Nearly there", color: "teal" };
  return null;
}

// The same planner-row hint, upgraded to a *pace* when the target has one: how
// many more clear nights would finish it, in the wording the Dashboard's "Target
// progress" card and the Target page already use.
//
// Why this replaces the badge rather than sitting beside it: "Nearly there" and
// "~1 more night" answer the same question, and the second answers it better —
// it's the number the user is actually deciding on while choosing what to point
// at tonight. Printing both would be clutter on an already-dense table row.
//
// Falls back to `readinessRowHint` verbatim whenever there's no number to give:
// no measured pace (fewer than two productive nights), a goal already met (the
// "Plenty — try something new" nudge is the useful thing then), or a target
// further from done than the shared cap — past which a nights count reads as a
// scold rather than encouragement. So a library with no pace history anywhere
// sees exactly what it saw before.
//
// Every badge carries a `tooltip` — the full sentence behind the chip, exactly
// as the row's difficulty and framing badges do. A three-word chip in a dense
// table has to be terse, but "~1 more night" is meaningless without "of what,
// toward what?", so the hover says where the number came from (the owner's own
// measured pace) and what it is counting toward (their goal).
export function readinessRowBadge(
  exposureSeconds: number,
  type: string | null | undefined,
  goalHoursOverride?: number | null,
  paceSeconds?: number | null,
): { label: string; color: string; tooltip: string } | null {
  const r = integrationReadiness(exposureSeconds, type, goalHoursOverride);
  if (r && r.level !== "plenty") {
    const est = clearNightsFromPace((r.goalHours - r.hours) * 3600, paceSeconds);
    if (est && est.nights !== null && est.nights <= FINISH_FIRST_MAX_NIGHTS) {
      return {
        label: `~${est.nights} more ${nightWord(est.nights)}`,
        color: "teal",
        tooltip: `${r.verdict} ${est.text}`,
      };
    }
  }
  const hint = readinessRowHint(exposureSeconds, type, goalHoursOverride);
  // `readinessRowHint` only returns a hint when the readiness itself exists, so
  // `r` is non-null here; the guard keeps the types honest rather than asserting.
  return hint && r ? { ...hint, tooltip: r.verdict } : null;
}

// Mantine colour for the readiness level, so the progress bar and any accent
// track the verdict (grey while just starting → teal once there's plenty).
export function readinessColor(level: ReadinessLevel): string {
  switch (level) {
    case "starting":
      return "gray";
    case "solid":
      return "blue";
    case "close":
      return "teal";
    case "plenty":
      return "green";
  }
}
