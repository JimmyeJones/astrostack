/** Pure phrasing for "Tonight, live" — the session happening right now.
 *
 * The page is read on a phone, outside, in the cold, by someone who wants two
 * answers and no reading: *"is this actually working?"* and *"have I got enough
 * to go inside?"*. So every helper here returns one plain sentence, and each one
 * says what it measured — "4 of your last 20 subs were kept" beats a bare
 * adjective the reader has to trust.
 *
 * No React and no I/O, so the wording is unit-testable on its own. The numbers
 * all come from the backend's `live-session` aggregation; nothing is re-derived
 * here.
 */
import type { LiveSession, Target } from "../api/client";
import { formatIntegration } from "../format";

/** The headline: how much you've got tonight, in the order you'd say it out
 * loud. "143 subs tonight · 118 kept · 1 h 58 m" is the shape the spec asked
 * for; this prints the integration in the app's shared idiom instead. */
export function tonightHeadline(live: LiveSession): string {
  const subs = `${live.n_frames.toLocaleString()} sub${live.n_frames === 1 ? "" : "s"}`;
  const parts = [`${subs} so far`, `${live.n_kept.toLocaleString()} kept`];
  if (live.kept_exposure_s > 0) parts.push(formatIntegration(live.kept_exposure_s));
  return parts.join(" · ");
}

/** "Is it working?" — the rolling conditions read, in a sentence that carries
 * the numbers behind it.
 *
 * Never scolds and never guesses: too few recent subs is "not enough yet to
 * tell", which is honestly different from "going badly". */
export function conditionsLine(live: LiveSession): string {
  const c = live.conditions;
  const of = `${c.n_recent_kept} of your last ${c.n_recent} subs`;
  switch (c.verdict) {
    case "good":
      return `Going well — ${of} were kept.`;
    case "mixed":
      return `A bit patchy — ${of} were kept.`;
    case "poor":
      return `Something's off out there — only ${of} were kept.`;
    default:
      return c.n_recent > 0
        ? `Only ${c.n_recent} sub${c.n_recent === 1 ? "" : "s"} in so far — not `
          + "enough yet to tell how it's going."
        : "No subs in yet.";
  }
}

/** The plain cause behind a bad stretch, when the app knows one — "mostly
 * cloud", "mostly trailing". Null when nothing was set aside recently, or when
 * no single cause dominates (saying "mostly" of a 40 % share would be a guess). */
export function conditionsCause(live: LiveSession): string | null {
  const buckets = Object.entries(live.conditions.recent_buckets)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
  if (buckets.length === 0) return null;
  const [name, n] = buckets[0];
  const total = buckets.reduce((sum, [, k]) => sum + k, 0);
  if (n / total < 0.6) return null;
  const phrase: Record<string, string> = {
    cloudy: "cloud",
    trailed: "trailing — check the mount is tracking and nothing has nudged it",
    soft: "soft stars — worth re-checking focus",
    unreadable: "subs that wouldn't read — worth checking the drive",
    "set aside by you": "subs you set aside yourself",
  };
  return `Mostly ${phrase[name] ?? name}.`;
}

/** Star size, when the app has measured it. Deliberately separate from the
 * verdict: a sharp night being thrown away by cloud and a soft night being kept
 * are different problems, and one adjective for both would hide each. */
export function sharpnessLine(live: LiveSession): string | null {
  const f = live.conditions.median_fwhm_px;
  if (f == null || !Number.isFinite(f) || f <= 0) return null;
  return `Stars are averaging ${f.toFixed(1)} px across tonight's keepers.`;
}

/** "Have I got enough to go inside?" — the goal line, or null when no goal is
 * set (the app never invents one).
 *
 * Measured against the target's *total* kept integration, not tonight's alone:
 * the goal is for the picture, and the beginner's real question is whether the
 * picture is done, not whether tonight was long. */
export function goalLine(live: LiveSession): string | null {
  const goal = live.goal_exposure_s;
  if (goal == null || !Number.isFinite(goal) || goal <= 0) return null;
  const have = live.total_kept_exposure_s;
  if (have >= goal) {
    return `${formatIntegration(have)} of your ${formatIntegration(goal)} goal — `
      + "you can call it a night whenever you like.";
  }
  const left = goal - have;
  return `${formatIntegration(have)} of your ${formatIntegration(goal)} goal — `
    + `about ${formatIntegration(left)} to go.`;
}

/** How long since the last sub landed, for the "is it still going?" line. */
export function freshnessLine(live: LiveSession): string {
  const m = live.minutes_since_latest;
  if (m == null || !Number.isFinite(m)) return "Waiting for the first sub.";
  if (!live.active) {
    return "No subs for a while — this session looks finished.";
  }
  if (m < 2) return "Newest sub just landed.";
  return `Newest sub ${Math.round(m)} min ago.`;
}

/** Which target the live page should open on, with no navigating: the one whose
 * frames arrived most recently.
 *
 * Cheap on purpose — `last_activity_utc` is already on the target list every
 * screen loads, so this needs no extra request and opens no project database.
 * Returns null for an empty library, or when nothing carries an activity stamp,
 * so the page shows its empty state rather than picking arbitrarily. */
/** How close another target's last activity has to be to the watched one's before
 * it counts as "the same night".
 *
 * Six hours is the same gap the backend's session split uses
 * (`DEFAULT_SESSION_GAP_HOURS`), so "tonight" means the same thing on this page
 * as it does in the recap and the Nights card — a Seestar that re-points at
 * midnight is one night, and yesterday's target is not. */
export const SAME_NIGHT_HOURS = 6;

/**
 * The *other* targets that also got subs inside the same night as the one being
 * watched, most recent first — empty when there are none.
 *
 * The page opens on whichever target's frames arrived most recently, which is
 * right: on a capture night that's the one filling up. But a Seestar that
 * re-points mid-night (or a mosaic split across panels) leaves the earlier
 * target invisible unless the reader already knows to use the picker. This is
 * the data behind one line naming them, built from the target list the page has
 * already fetched — no extra request, and deliberately not a second dashboard.
 *
 * Anchored on the watched target's own last activity rather than on the clock,
 * so reading the page the next morning still shows what shared that night.
 */
export function alsoActiveTonight(
  targets: Target[] | null | undefined,
  safe: string | null,
): Target[] {
  const all = targets ?? [];
  const watched = all.find((t) => t.safe_name === safe);
  const anchor = watched?.last_activity_utc
    ? new Date(watched.last_activity_utc).getTime()
    : NaN;
  if (!Number.isFinite(anchor)) return [];
  const window = SAME_NIGHT_HOURS * 3600 * 1000;
  return all
    .filter((t) => t.safe_name !== safe && !!t.last_activity_utc)
    .map((t) => ({ t, ms: new Date(t.last_activity_utc as string).getTime() }))
    .filter(({ ms }) => Number.isFinite(ms) && Math.abs(ms - anchor) <= window)
    .sort((a, b) => b.ms - a.ms)
    .map(({ t }) => t);
}

export function mostRecentlyActive(targets: Target[] | null | undefined): Target | null {
  let best: Target | null = null;
  let bestT = -Infinity;
  for (const t of targets ?? []) {
    if (!t.last_activity_utc) continue;
    const ms = new Date(t.last_activity_utc).getTime();
    if (!Number.isFinite(ms)) continue;
    if (ms > bestT) {
      bestT = ms;
      best = t;
    }
  }
  return best;
}
