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

/** How long since the last sub landed, for the "is it still going?" line.
 *
 * The `quiet` branch matters: "this session looks finished" is a comfortable
 * thing to say about a night that ended, and exactly the wrong thing to say
 * about one that *stopped*. The backend draws that line (see
 * `seestack/livesession.py`), so this only has to phrase it. */
export function freshnessLine(live: LiveSession): string {
  const m = live.minutes_since_latest;
  if (m == null || !Number.isFinite(m)) return "Waiting for the first sub.";
  if (live.quiet) {
    return `No new subs for ${quietGap(m)} — capture may have stopped.`;
  }
  if (!live.active) {
    return "No subs for a while — this session looks finished.";
  }
  if (m < 2) return "Newest sub just landed.";
  return `Newest sub ${Math.round(m)} min ago.`;
}

/** A span of minutes in the app's shared duration idiom ("50 min", "1.2 h"). */
export function quietGap(minutes: number): string {
  return formatIntegration(Math.max(0, minutes) * 60);
}

/** How often this target had been getting a sub, in words — "about every 40 s",
 * "about every 3 min". Null when the cadence wasn't measurable, so the caller
 * drops the clause rather than inventing a number. */
export function cadencePhrase(live: LiveSession): string | null {
  const g = live.typical_gap_minutes;
  if (g == null || !Number.isFinite(g) || g <= 0) return null;
  return `about every ${formatIntegration(g * 60)}`;
}

/**
 * "Capture seems to have gone quiet" — the whole note, or null when there is
 * nothing to say.
 *
 * The failure this is for is the one the owner can't watch happen: they walk
 * away, the Seestar stalls (lost connection, full card, a dew-heater trip that
 * parks it), and the rest of a clear night is simply missing in the morning. The
 * wording has one job beyond the fact — it must not scold someone who just
 * finished for the night, because that reader is the common case and this note
 * costs them a second either way.
 */
export function captureQuietMessage(live: LiveSession): string | null {
  if (!live.quiet) return null;
  const m = live.minutes_since_latest;
  if (m == null || !Number.isFinite(m)) return null;
  const cadence = cadencePhrase(live);
  const got = live.n_frames > 0
    ? ` You've got ${live.n_frames.toLocaleString()} sub`
      + `${live.n_frames === 1 ? "" : "s"}`
      + `${live.kept_exposure_s > 0
        ? ` (${formatIntegration(live.kept_exposure_s)} kept)` : ""}`
      + " from this session so far."
    : "";
  return `This target was getting a sub ${cadence ?? "steadily"}, then nothing `
    + `arrived for ${quietGap(m)}. Capture may have stopped — a Seestar can lose `
    + "its connection, fill its card, or park itself. If you finished for the "
    + `night, nothing is wrong and you can ignore this.${got}`;
}

/** Which target the live page should open on, with no navigating: the one whose
 * frames arrived most recently.
 *
 * Cheap on purpose — `last_activity_utc` is already on the target list every
 * screen loads, so this needs no extra request and opens no project database.
 * Returns null for an empty library, or when nothing carries an activity stamp,
 * so the page shows its empty state rather than picking arbitrarily. */
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

/** How far apart two targets' newest frames can be and still count as "the same
 * night". Long enough to span a winter night end to end, short enough that last
 * week's session never shows up as company. */
export const SAME_NIGHT_HOURS = 14;

/** The *other* targets that also got subs around the same time as the one on
 * screen, newest first.
 *
 * A Seestar that re-points mid-night (or a mosaic split across panels) leaves
 * the earlier target invisible on this page, because it opens on whichever
 * target's frames arrived most recently and says nothing about the rest. This is
 * the one line that fixes that, and it stays a zero-extra-request change:
 * `last_activity_utc` is already on the target list the page loads.
 *
 * Deliberately *not* a multi-target dashboard — the page's value is that it
 * answers two questions about **one** night at a glance — so the result is
 * capped at `limit` and is only ever rendered as links.
 */
export function alsoActiveTonight(
  targets: Target[] | null | undefined,
  currentSafe: string | null,
  limit = 3,
): Target[] {
  const current = (targets ?? []).find((t) => t.safe_name === currentSafe);
  const refMs = current?.last_activity_utc
    ? new Date(current.last_activity_utc).getTime()
    : NaN;
  if (!Number.isFinite(refMs)) return [];
  const windowMs = SAME_NIGHT_HOURS * 3600_000;
  return (targets ?? [])
    .filter((t) => t.safe_name !== currentSafe && !!t.last_activity_utc)
    .map((t) => ({ t, ms: new Date(t.last_activity_utc!).getTime() }))
    .filter(({ ms }) => Number.isFinite(ms) && Math.abs(ms - refMs) <= windowMs)
    .sort((a, b) => b.ms - a.ms)
    .slice(0, limit)
    .map(({ t }) => t);
}
