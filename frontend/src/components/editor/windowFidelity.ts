// Pure helper: the one thing "check it at full size" cannot promise.
//
// The loupe renders a 512 px window of the picture through the same recipe, and
// what makes that honest rather than a second lie is that every op which
// measures the *whole* image is handed what the whole-image render measured
// (`EditContext.fit`). Four ops take a whole-array measurement by a route `fit`
// cannot reach: noise reduction and deconvolution normalise by the picture's own
// 0.5–99.5th percentile span, colour-blotch smoothing and hot-pixel removal read
// its sky level and noise floor. Handed a window they measure the window, so how
// strong they look there is not the strength the export applies — measured at up
// to 3.9 % of full scale for the wavelet default on a star-poor patch (the open
// LEAD in `docs/IMPROVEMENTS.md` carries the table; the backend declares the four
// op by op and `tests/test_edit_window_fidelity.py` pins every one of them).
//
// Three of those four are *why the reader is here*. The preview's own advisories
// say hot-pixel removal is skipped entirely, deconvolution understates and
// bilateral noise reduction previews weaker than it exports, and all three send
// them to this control — "at the threshold you've set". So the window was being
// cited as the authority for the ops it is least faithful on, and said nothing
// about it. Until the measurement is carried, this sentence is the fix: cheap,
// honest, and it changes nothing about what the editor renders or exports.
//
// "Every other step here is applying exactly what your export will" is not a
// flourish. Every other op in the loupe's scope renders a frozen window whose
// pixels match the picture it was cut from to within float noise — asserted op by
// op, derived from the registry, in `tests/test_edit_window_fidelity.py`. The
// names come from the server (`OpSpec.label`), so this sentence cannot come to
// call a control something the control is not called.

export interface WindowFidelityInfo {
  /** Labels of the enabled ops whose window render is not the picture's, in
   *  recipe order and deduped by the server. Absent on a backend older than
   *  v0.493.7, which then says nothing — exactly as the editor always has. */
  unvouched_ops?: string[];
}

/** The caveat line for the full-size view, or `null` when this recipe has no op
 *  the window cannot vouch for — which is the common case, Auto's own recipe
 *  included, so the quiet picture pays nothing for the honest one. */
export function unvouchedOpsCaption(
  info: WindowFidelityInfo | null | undefined,
): string | null {
  const names = (info?.unvouched_ops ?? []).filter(
    (n): n is string => typeof n === "string" && n.trim().length > 0);
  if (names.length === 0) return null;
  const list = names.length === 1
    ? names[0]
    : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
  const close = "Every other step here is applying exactly what your export will.";
  return names.length === 1
    ? `One thing this view can't promise: ${list} measures your whole picture's `
      + "brightness and grain before it acts, and on a piece this small it has to "
      + "measure the piece instead — so how strong it looks here can differ from "
      + `your export. ${close}`
    : `One thing this view can't promise: ${list} measure your whole picture's `
      + "brightness and grain before they act, and on a piece this small they have "
      + "to measure the piece instead — so how strong they look here can differ "
      + `from your export. ${close}`;
}
