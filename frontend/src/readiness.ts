// "Is it enough yet?" — judge a target's accumulated integration against a sane
// per-object-type goal and phrase a plain-language readiness verdict. Purely
// offline: it turns data the Target page already has (accepted-sub exposure
// total + the catalog object type from the identify card) into an answer to a
// beginner's most common uncertainty on the stack→result path — "do I have
// enough subs for a clean image, or should I keep shooting this target?" The
// goal is a *suggestion, never a gate* (nothing here blocks stacking).

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

// A compact hint for a target already in the library, for the Tonight planner's
// "add more to what you're shooting" rows: nudge the user toward starting
// something new once a target has close-to / more-than its suggested goal, and
// stay quiet (null) while it's still worth topping up (the row's integration
// figure already implies "keep going"). Caller supplies the accepted-sub
// exposure total + catalog type for one already-targeted row.
export function readinessRowHint(
  exposureSeconds: number,
  type: string | null | undefined,
): { label: string; color: string } | null {
  const r = integrationReadiness(exposureSeconds, type);
  if (!r) return null;
  if (r.level === "plenty") return { label: "Plenty — try something new", color: "green" };
  if (r.level === "close") return { label: "Nearly there", color: "teal" };
  return null;
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
