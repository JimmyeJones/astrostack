/** Pure phrasing for "how much of the sky have you actually photographed?".
 *
 * The number itself is measured server-side off each run's own WCS
 * (`seestack/skyarea.py`) — never by counting pixels on the map, which is an
 * Aitoff projection (not equal-area) that also draws every picture several times
 * life size. All this file does is say it in words a beginner reads once and
 * understands. No React, no I/O, so it's unit-testable on its own.
 */

/** Square degrees in one full Moon (~31 arcmin across) — the only unit of sky
 *  area a beginner already has a feel for. */
export const FULL_MOON_DEG2 = 0.2018;

/** A tiny fraction as a readable percentage. Astro coverage is genuinely small,
 *  so the usual `toFixed(1)` would render almost every real library as "0.0%". */
export function formatSkyFraction(fraction: number): string {
  const pct = fraction * 100;
  if (!Number.isFinite(pct) || pct <= 0) return "0%";
  if (pct < 0.001) return "less than 0.001%";
  if (pct < 0.1) return `${pct.toFixed(3)}%`;
  if (pct < 1) return `${pct.toFixed(2)}%`;
  if (pct < 10) return `${pct.toFixed(1)}%`;
  return `${Math.round(pct)}%`;
}

/** Square degrees, at a precision that suits the magnitude. */
export function formatSkyArea(deg2: number): string {
  if (!Number.isFinite(deg2) || deg2 <= 0) return "0";
  if (deg2 < 1) return deg2.toFixed(2);
  if (deg2 < 100) return deg2.toFixed(1);
  return String(Math.round(deg2));
}

/**
 * The one-line read-out under "My map", or `""` when there's nothing to say yet
 * (no finished picture carries a position, so any number would be invented).
 *
 * Leads with the honest measurement, then anchors it in full Moons — the only
 * patch of sky a beginner can already picture — and closes with the fraction,
 * which is the number that makes people grin.
 *
 * **It deliberately says nothing about how many pictures there are**, though it
 * is handed the count. This sentence used to open "Your 3 pictures cover …" and
 * sat directly under a map whose own baked subtitle said "4 of your pictures" —
 * two counts of one thing, side by side, disagreeing. They are counted by
 * different rules on purpose and both rules are right for their own job: the map
 * draws every picture it can place *somewhere* honest, including one whose master
 * carries no usable WCS (a nominal field, `routers/sky.py::_my_map_pictures`),
 * while the area measurement drops that picture rather than invent the sky it
 * covers (`seestack/skyarea.py`). So the count belongs to the map, which is where
 * a reader can check it by looking; this line is about *area*, and says only that.
 * `nPictures` still gates it — zero placeable pictures means there is no honest
 * number to print — and still picks nothing else.
 *
 * `summedDeg2` is what plain addition would have said before overlapping
 * pictures were counted once (absent on an older backend). It buys one extra
 * clause, and only when the deduplication actually changed the number the reader
 * is looking at — otherwise explaining it would be clutter about nothing. That
 * test is deliberately the *rendered* number, not the raw one: a library with a
 * sliver of overlap says nothing, and the owner whose total visibly moved is
 * told why in the same breath.
 */
export function describeSkyCoverage(
  deg2: number, fraction: number, nPictures: number,
  summedDeg2?: number | null,
): string {
  if (!Number.isFinite(deg2) || deg2 <= 0 || nPictures <= 0) return "";
  const moons = deg2 / FULL_MOON_DEG2;
  // "of sky" belongs to the lead clause now, so saying it again here would read
  // as "square degrees of sky — about a full Moon's worth of sky".
  const moonPhrase = moons < 1.5
    ? "about a full Moon's worth"
    : `about ${Math.round(moons).toLocaleString()} full Moons' worth`;
  const overlapped =
    typeof summedDeg2 === "number" && Number.isFinite(summedDeg2) &&
    summedDeg2 > deg2 && formatSkyArea(summedDeg2) !== formatSkyArea(deg2);
  return (
    `You've photographed ${formatSkyArea(deg2)} square degrees of sky — ` +
    `${moonPhrase}, and ${formatSkyFraction(fraction)} of the whole sky.` +
    (overlapped
      ? " Where two of your pictures overlap, that patch counts once."
      : "")
  );
}
