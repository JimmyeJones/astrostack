/**
 * "Your best night" — the sentence under the whole-hobby sharpest-night stat.
 *
 * The backend already decides *which* night was sharpest (and stays silent when
 * too little was measured to say so honestly — see
 * `seestack/activity_calendar.py::sharpest_night`). This is only the wording, so
 * it lives here as a pure function the card renders and the tests read.
 *
 * Star size is quoted in **pixels**, the same unit the Frames table, the Nights
 * card and the session recap all use, so a beginner meets one number rather than
 * three. Smaller is sharper.
 */
import type { NightActivity } from "../api/client";
import { formatNightDate } from "../format";

export interface BestNightLines {
  /** The night itself, e.g. "12 Jan 2026". */
  date: string;
  /** The headline figure, e.g. "2.4 px stars". */
  value: string;
  /** One plain-language line of context under it. */
  detail: string;
}

/**
 * Render the sharpest night as the three strings the card shows, or `null` when
 * there is nothing trustworthy to say — an older backend that doesn't send the
 * field, a library where too few nights were measured, or a night that somehow
 * arrived without its median.
 */
export function bestNightLines(
  night: NightActivity | null | undefined,
  formatIntegration: (s: number) => string,
): BestNightLines | null {
  if (!night || night.median_fwhm_px == null || !(night.median_fwhm_px > 0)) {
    return null;
  }
  const subs = night.n_measured ?? 0;
  // What you actually pointed at that night — named, because "your best night"
  // is a memory, and the object is what makes it one. Two names fit; beyond
  // that the count carries it.
  const targets = night.targets ?? [];
  let what = "";
  if (targets.length === 1) what = ` on ${targets[0]}`;
  else if (targets.length === 2) what = ` on ${targets[0]} and ${targets[1]}`;
  else if (targets.length > 2) what = ` across ${targets.length} targets`;

  const measured = subs > 0
    ? `${subs.toLocaleString()} sub${subs === 1 ? "" : "s"} measured`
    : "";
  const shot = night.exposure_s > 0 ? formatIntegration(night.exposure_s) : "";
  const parts = [shot ? `${shot} captured` : "", measured].filter(Boolean);

  return {
    date: formatNightDate(night.date),
    value: `${night.median_fwhm_px.toFixed(1)} px stars`,
    detail: `Your steadiest sky yet${what}${parts.length ? ` — ${parts.join(", ")}` : ""}.`,
  };
}
