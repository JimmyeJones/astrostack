/**
 * "Your year under the stars" — the small decisions the year page and its entry
 * card both have to make, as pure functions.
 *
 * The backend decides what is *true* about a year (`seestack/yearrecap.py`);
 * this file only decides which year to open and how to word the two standout
 * nights. Keeping it out of the components means both surfaces can't drift
 * about which year "your year" means.
 */
import type { NightActivity, YearRecap } from "./api/client";
import { formatNightDate } from "./format";

/**
 * Which year the page should open on: the most recent year that actually has
 * nights, falling back to `thisYear` when the library has none at all.
 *
 * "The current year" is the wrong default in January — a beginner clicking in on
 * the 3rd would meet an empty page about a year that has barely started, while
 * the season they want to look back on sits one click away. Landing on the
 * newest year *with data* means the page always has something to say, and the
 * year picker is right there for the rest.
 */
export function defaultRecapYear(
  yearsWithData: number[] | undefined,
  thisYear: number,
): number {
  const years = (yearsWithData ?? []).filter((y) => Number.isFinite(y));
  if (years.length === 0) return thisYear;
  return Math.max(...years);
}

/** The years to offer in the picker, newest first — always including the year
 * being viewed, so the current selection is never missing from its own list. */
export function recapYearOptions(recap: YearRecap | undefined): number[] {
  if (!recap) return [];
  const set = new Set<number>(recap.years_with_data ?? []);
  set.add(recap.year);
  return [...set].sort((a, b) => b - a);
}

export interface YearNightLines {
  /** The night itself, e.g. "12 Jan 2026". */
  date: string;
  /** The headline figure for that night. */
  value: string;
  /** One plain-language line of context under it. */
  detail: string;
}

/** What you pointed at that night, as a phrase — "" when nothing is known.
 * Mirrors the wording `bestNight.ts` uses, so the two night cards read alike. */
function whatYouShot(night: NightActivity): string {
  const targets = night.targets ?? [];
  if (targets.length === 1) return ` on ${targets[0]}`;
  if (targets.length === 2) return ` on ${targets[0]} and ${targets[1]}`;
  if (targets.length > 2) return ` across ${targets.length} targets`;
  return "";
}

/**
 * The year's longest night as the three strings its card shows, or `null` when
 * the backend stayed silent (a one-night year has no "longest").
 */
export function longestNightLines(
  night: NightActivity | null | undefined,
  formatIntegration: (s: number) => string,
): YearNightLines | null {
  if (!night || !(night.exposure_s > 0)) return null;
  const subs = night.n_frames ?? 0;
  const kept = subs > 0
    ? ` — ${subs.toLocaleString()} sub${subs === 1 ? "" : "s"} kept`
    : "";
  return {
    date: formatNightDate(night.date),
    value: formatIntegration(night.exposure_s),
    detail: `Your longest night of the year${whatYouShot(night)}${kept}.`,
  };
}

/**
 * The year's sharpest night, worded for the year page. Star size is quoted in
 * pixels — the unit the Frames table, the Nights card and the session recap all
 * use — so a beginner meets one number rather than three. Smaller is sharper.
 */
export function sharpestNightLines(
  night: NightActivity | null | undefined,
): YearNightLines | null {
  if (!night || night.median_fwhm_px == null || !(night.median_fwhm_px > 0)) {
    return null;
  }
  const subs = night.n_measured ?? 0;
  const measured = subs > 0
    ? ` — ${subs.toLocaleString()} sub${subs === 1 ? "" : "s"} measured`
    : "";
  return {
    date: formatNightDate(night.date),
    value: `${night.median_fwhm_px.toFixed(1)} px stars`,
    detail: `Your steadiest sky of the year${whatYouShot(night)}${measured}.`,
  };
}

export interface YearNightCard {
  /** Which standout(s) this card carries — also its React key. */
  key: "longest" | "sharpest" | "both";
  title: string;
  lines: YearNightLines;
}

/**
 * The standout-night cards to render, in order — none, one or two.
 *
 * The year ranks its nights twice, by length and by steadiness, and on a short
 * season those two questions have one answer: the night you got the most out of
 * is often the night the sky was best. Rendered as two cards it read as the page
 * repeating itself — the same date, the same target, twice, side by side. So
 * when both standouts are the *same night* they become one card that says so,
 * carrying both figures and both facts. Nothing is dropped; the reader gains the
 * thing two cards could never say — that one night was both.
 *
 * The poster makes the same call in its own copy
 * (`seestack.yearrecap.year_sharpest_night_line`), so the page and the picture
 * you post from it cannot disagree about whether that was one night or two.
 */
export function yearNightCards(
  longestNight: NightActivity | null | undefined,
  sharpestNight: NightActivity | null | undefined,
  formatIntegration: (s: number) => string,
): YearNightCard[] {
  const longest = longestNightLines(longestNight, formatIntegration);
  const sharpest = sharpestNightLines(sharpestNight);
  if (longest && sharpest && longestNight && sharpestNight
      && longestNight.date === sharpestNight.date) {
    return [{
      key: "both",
      title: "Longest — and sharpest — night",
      lines: {
        date: longest.date,
        value: `${longest.value} · ${sharpest.value}`,
        // The longest night's own sentence, then the second accolade as its
        // own clause — the sharpest line's "steadiest sky of the year" wording,
        // without repeating where you were pointing or how many subs it was.
        detail: `${longest.detail} It was your steadiest sky of the year too.`,
      },
    }];
  }
  const out: YearNightCard[] = [];
  if (longest) out.push({ key: "longest", title: "Longest night", lines: longest });
  if (sharpest) out.push({ key: "sharpest", title: "Sharpest night", lines: sharpest });
  return out;
}
