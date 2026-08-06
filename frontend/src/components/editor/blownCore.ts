import type { HighlightSuggestion } from "../../api/client";

/** Plain-language nudge when the highlight suggestion found a blown-out core the
 * stretch's shoulder can genuinely bring back — or ``null`` when there's nothing
 * to say.
 *
 * v0.240.0 wired the measurement to a "From your image" button on the **Hold back
 * highlights** slider, but that slider is an `advanced` param, so the button
 * lives inside the op panel's collapsed *Advanced* accordion. A beginner
 * selecting Stretch never opens it — which leaves the app in the odd position of
 * having measured that the user's galaxy core is washing out, and knowing the
 * exact fix, while showing them nothing. This surfaces the same finding, with the
 * same one click, where it can be seen.
 *
 * There is deliberately **no threshold here.** The server already declines on a
 * core too small to be anything but a star, one barely clipped, one saturated at
 * capture (nothing to bring back), and one the knob can't meaningfully reopen —
 * so a strength arriving at all *is* the decision to speak. A second, independent
 * floor in the UI could only disagree with it.
 *
 * Pure and side-effect free: nothing changes until the user presses the button,
 * the preview shows the result immediately, and dragging the slider back undoes
 * it. */
export function blownCoreCaption(
  sug: HighlightSuggestion | undefined,
  current?: unknown,
): string | null {
  const strength = sug?.strength;
  if (strength == null || !Number.isFinite(strength) || strength <= 0) return null;
  // The suggestion is solved from protection *off*, so it's an absolute strength:
  // once the slider is there (or past it) the nudge has been taken, and repeating
  // it would just be nagging.
  const held = typeof current === "number" && Number.isFinite(current) ? current : 0;
  if (held >= strength) return null;
  return "The brightest core in your picture is washing out to flat white. "
    + "The detail is still in your data — holding the highlights back brings its "
    + "shape and colour back, and leaves the sky exactly where it is.";
}

/** Label for the button that applies the measured strength. Names the value so
 * the click has no surprise in it, like the sibling "From your image" buttons. */
export function blownCoreButtonLabel(sug: HighlightSuggestion | undefined): string {
  return `Hold back highlights (${sug?.strength ?? 0})`;
}
