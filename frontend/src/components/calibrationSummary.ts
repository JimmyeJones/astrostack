import { calibrationLabel } from "./CalibrationBadge";

// Plain-language calibration provenance for a run's FITS header cards. The
// stacker stamps a CALSTAT card ("dark+flat", "bias+flat", "flat", …) only when
// masters were actually applied to the lights, so — among a stack that *does*
// carry provenance — CALSTAT's presence reliably means calibrated and its
// absence means uncalibrated (callers return early when a stack has no
// provenance cards at all, so this never confuses "uncalibrated" with an older
// master that recorded nothing). For the walk-away user this closes a real trust
// gap: the History Info panel previously showed only a cryptic "CALSTAT dark+flat"
// row when calibrated, and said *nothing at all* when a hands-off (auto-bound)
// stack came out uncalibrated — leaving no cue to go build or pick a master.
// Returns { text, calibrated } or null when there's no provenance to speak to.
// Pure and shared so both the History Info panel (v0.103.7) and the editor's
// auto-note surface (where the Process-target deep-link lands the walk-away user)
// tell the same calibration story.
// `advice` (optional) is the backend's specific, actionable "why uncalibrated"
// hint (`StackRunInfo.calibration_advice`) — e.g. "you have a master dark at a
// different exposure — build a master bias and it'll be reused automatically". It
// only ever replaces the *generic* uncalibrated copy (never the calibrated line),
// so a concrete fix is shown when the library holds a nearly-usable master.
// `skipped` (optional) is what the run itself *recorded*: the saved calibration
// picks its unattended stack had to drop, already written as plain-language
// sentences by the backend ("Your saved master dark wasn't used: it's no longer in
// your calibration library."). It comes back as its own field rather than folded
// into `text`, because it answers a different question — `text` says what this
// picture *got*, the skip line says what the user *asked for and didn't get* — and
// because it matters even on a calibrated run: a bound flat is no excuse for
// silently dropping the dark they picked. Unlike `advice` (re-derived from the
// library) it is recorded evidence, and it's the only thing that can explain a
// master deleted *after* it was chosen.
export function calibrationSummaryText(
  cards: { key: string; value: string | number | boolean }[],
  advice?: string | null,
  skipped?: string[] | null,
): { text: string; calibrated: boolean; skipped?: string } | null {
  if (cards.length === 0) return null;
  const skips = (skipped ?? []).map((s) => s.trim()).filter(Boolean);
  const skipText = skips.length ? skips.join(" ") : undefined;
  const card = cards.find((c) => c.key === "CALSTAT");
  const label = calibrationLabel(card ? String(card.value) : null);
  if (label) {
    return { text: `Calibrated with your ${label}.`, calibrated: true, skipped: skipText };
  }
  if (advice && advice.trim()) {
    return { text: advice.trim(), calibrated: false, skipped: skipText };
  }
  return {
    text:
      "No calibration masters were applied — build or pick a master dark/flat " +
      "in Calibration to cut thermal noise and vignetting.",
    calibrated: false,
    skipped: skipText,
  };
}
