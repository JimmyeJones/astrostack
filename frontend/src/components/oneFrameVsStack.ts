/** Pure caption for the "one frame vs your stack" reveal.
 *
 * Turns the run's own provenance (a single sub's exposure + the stack's frame
 * count) into a plain-language line a beginner understands, e.g. "One 30-second
 * frame vs your 505-frame stack — stacking cut the noise and pulled out faint
 * detail." Every part is best-effort: a missing datum drops that clause rather
 * than printing a blank, so an older/edited run still reads cleanly. Kept pure so
 * a Vitest can pin every degraded shape without a DOM. */

/** Format a sub exposure in seconds as a compact human label ("30-second",
 * "2.5-second"). Returns null for a missing/non-finite/non-positive value. */
export function subExposureLabel(seconds: number | null | undefined): string | null {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) return null;
  // Whole seconds read as "30-second"; a fractional exposure keeps one decimal.
  const rounded = Math.round(seconds * 10) / 10;
  const text = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
  return `${text}-second`;
}

/** The caption sentence for the reveal. Degrades gracefully as fields drop:
 *  - both present → "One 30-second frame vs your 505-frame stack — …"
 *  - only frames  → "One frame vs your 505-frame stack — …"
 *  - neither      → "One frame vs your stack — …"
 *
 * `matchedBy` says how the two halves were made comparable. On a "Process
 * target" run both sides go through that run's *own* edit ("recipe"), which is
 * worth saying out loud: a beginner looking at an edited picture beside a grainy
 * frame should know the grain is the only difference, not the editing. A plain
 * stack ("stretch", the default) needs no such line — the tone match is the
 * uninteresting default there. */
export function oneFrameCaption(
  subExposureS: number | null | undefined,
  nFrames: number | null | undefined,
  matchedBy?: string | null,
): string {
  const exp = subExposureLabel(subExposureS);
  const frame = exp ? `One ${exp} frame` : "One frame";
  const hasCount = nFrames != null && Number.isFinite(nFrames) && nFrames > 0;
  const stack = hasCount ? `your ${nFrames}-frame stack` : "your stack";
  const same =
    matchedBy === "recipe"
      ? " Both sides went through the same edit, so the only difference is the extra frames."
      : "";
  return `${frame} vs ${stack} — stacking cut the noise and pulled out faint detail.${same}`;
}

/** The quantitative "stacking cut your noise ~N×" badge line, or null to omit it.
 *
 * Turns the measured background-noise reduction ratio into a concrete, shareable
 * sentence a beginner immediately understands (and a plain reminder that more
 * subs help, √N). Returns null for a missing/non-finite ratio, or one too small
 * to be a compelling, trustworthy story (< 1.5×) — the card then just shows the
 * visual reveal without a number. Formats a big reduction as a whole number
 * ("about 15×") and a small one to one decimal ("about 2.4×").
 *
 * **`isMosaic` drops the sub count**, because the ratio is measured over a
 * central crop and no pixel there ever saw more than its own panel's subs — so
 * "your 400 subs cut the noise about 10×" credits a whole target's frames with
 * one panel's result. That is the same wrong denominator the yardstick sentence
 * below fixed (`expected_basis: "mosaic_centre"`) and `rejection_blind` fixed
 * before it; this is its mildest instance, and the only one that *flatters*
 * rather than accuses, which is why it outlived two sweeps. The fix is the
 * already-tested countless phrasing rather than a panel-depth caveat: this is
 * the card's one celebratory line, the ×-figure itself is right, and naming the
 * panel depth here would both repeat and undercut the sentence directly beneath.
 * A `null` flag (a run stacked before schema 8) keeps the count — unlike the
 * yardstick, which withholds a *judgement* on an unknown canvas, this only
 * withholds a compliment's subject, and dropping it on every legacy single-field
 * run costs more than the rare legacy mosaic's overstatement does. */
export function noiseReductionBadge(
  ratio: number | null | undefined,
  nFrames: number | null | undefined,
  isMosaic?: boolean | null,
): string | null {
  if (ratio == null || !Number.isFinite(ratio) || ratio < 1.5) return null;
  const hasCount =
    !isMosaic && nFrames != null && Number.isFinite(nFrames) && nFrames > 0;
  const subs = hasCount ? `your ${nFrames} subs` : "your subs";
  return `Stacking ${subs} cut the background noise about ${factorLabel(ratio)}×.`;
}

/** Big reductions read as a whole number ("15×"); smaller ones keep one decimal
 *  ("2.4×") — but drop a trailing ".0" so a value that rounds up to a whole
 *  number ("10.0") shows cleanly as "10×".
 *
 *  Mirrored by hand in `seestack.stackhealth._factor_label`, which writes the
 *  "How's my stack?" note about the *same* run — a user reads both minutes
 *  apart, so a drift shows up as the app contradicting itself about one picture.
 *  The two are pinned against one shared table, `factorLabel.cases.json`, driven
 *  from this file's test and from `tests/test_factor_label_mirror.py`: change the
 *  rule and you have to change the table, on both sides. Exported for that test
 *  only. */
export function factorLabel(value: number): string {
  const rounded = value >= 10 ? Math.round(value) : Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

/** The plain-language reading of a measured noise reduction against what the
 *  frames used *should* have bought. */
export interface NoiseVsExpected {
  /** The whole sentence(s), ready to render. */
  text: string;
  /** True when the stack came in materially below √N — a gentle nudge, never
   *  an assertion of fault. */
  concern: boolean;
}

/** The "you should have got about N×, you got M×" lead of the shortfall note.
 *
 * The *same* sentence is written by `seestack.stackhealth` for the "How's my
 * stack?" note about the same run, so it is pinned from both sides against
 * `noiseLowLead.cases.json`. It had already drifted: this side said "cut the
 * noise" where the health note said "cut the **background** noise" — the measured
 * quantity is the sky background's grain, so the qualifier is the true word and
 * this side moved to it. Nothing was *wrong* in either, which is why nobody
 * caught it; this class doesn't fail loudly, it drifts.
 *
 * Exported so the mirror guard can drive it directly, and factored out of
 * `noiseVsExpectedNote` so there is one place the wording lives.
 */
export function noiseLowLead(n: number, ratio: number, mosaic: boolean): string {
  const expLabel = factorLabel(Math.sqrt(n));
  return mosaic
    ? `About ${n} subs cover the middle of this mosaic, which should cut the ` +
      `background noise about ${expLabel}× (√${n}), and it came in nearer ` +
      `${factorLabel(ratio)}×.`
    : `${n} subs should cut the background noise about ${expLabel}× (√${n}), ` +
      `and this stack came in nearer ${factorLabel(ratio)}×.`;
}

/** "Is ~18× any good?" — the context a beginner needs to read the badge above.
 *
 * A weighted-mean stack of `N` frames cuts background noise by about √N, so the
 * honest yardstick is √(frames actually used). **The judgement is the server's**:
 * `verdict` comes straight from the noise endpoint's `expected_verdict`, which
 * is `seestack.stackhealth.noise_vs_expected` — the same call behind the "How's
 * my stack?" note, so the two surfaces can never disagree about the same stack
 * and the 0.7 factor (and the 10-frame floor under it) is never re-typed here.
 * This function only writes the sentence for it.
 *
 * Returns null when there is nothing trustworthy to say: no verdict (no
 * measurement, too few frames for √N to mean anything, or a mosaic whose crop
 * depth nothing has measured), or a ratio/count the sentence can't name.
 *
 * **Which N.** The yardstick is `expectedFrames` — the count the server actually
 * judged against — and `basis` says what it counts, so the sentence names the
 * right thing rather than inferring it. On a single field that is the run's own
 * frame count; on a **mosaic** it is the frame depth at the crop the ratio was
 * measured over, because no pixel there ever saw more than its own panel's subs.
 * A backend too old to send either falls back to `nFrames`, i.e. exactly today's
 * single-field sentence.
 *
 * The healthy sentence assumes the badge is beside it (it is: anything at or
 * above 0.7·√10 also clears the badge's own 1.5× floor), so it doesn't repeat
 * the measured number. The *concern* sentence stands alone, because a stack far
 * enough below expectation can measure under that floor — which is exactly the
 * case worth saying something about. It suggests, never asserts: legitimate
 * rejection and quality weighting both lower the effective frame count. */
export function noiseVsExpectedNote(
  verdict: string | null | undefined,
  ratio: number | null | undefined,
  nFrames: number | null | undefined,
  expectedFrames?: number | null,
  basis?: string | null,
): NoiseVsExpected | null {
  if (verdict !== "expected" && verdict !== "low") return null;
  if (ratio == null || !Number.isFinite(ratio) || ratio <= 0) return null;
  const yardstick =
    expectedFrames != null && Number.isFinite(expectedFrames)
      ? expectedFrames
      : nFrames;
  if (yardstick == null || !Number.isFinite(yardstick)) return null;
  const n = Math.trunc(yardstick);
  if (n <= 0) return null;
  const expLabel = factorLabel(Math.sqrt(n));
  const mosaic = basis === "mosaic_centre";
  if (verdict === "expected") {
    return {
      text: mosaic
        ? `That's about what the ${n} subs covering the middle of this mosaic ` +
          `should give (√${n} ≈ ${expLabel}×).`
        : `That's about what ${n} subs should give (√${n} ≈ ${expLabel}×).`,
      concern: false,
    };
  }
  const lead = noiseLowLead(n, ratio, mosaic);
  return {
    text:
      `${lead} That usually means the subs didn't line up tightly, or a lot ` +
      `of them were dropped — worth checking focus and alignment on your next ` +
      `night.`,
    concern: true,
  };
}
