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

/** The Stretch op the nudge is about when the user has not selected one.
 *
 * The measurement only ever reached the screen while the Stretch op was the
 * *selected* control — so a beginner who opened the editor on an Auto recipe,
 * saw a white blob where their galaxy core should be and did not think to click
 * "Stretch" was shown nothing, on a picture the app had already measured. The
 * Auto notes are where that user is looking, so they ask too.
 *
 * This mirrors the server's own fallback (`solve_highlight_protect` with no
 * uid: the recipe's **first** `tone.stretch`), so the nudge in the note and the
 * one on the op panel can never end up about two different ops. ``null`` when
 * the recipe has no Stretch, or when its Stretch is switched off — there is
 * nothing to offer on an op that is not rendering.
 */
export function blownCoreStretchOp<T extends { id: string; enabled?: boolean }>(
  ops: readonly T[] | undefined,
): T | null {
  const first = (ops ?? []).find((o) => o.id === "tone.stretch");
  if (!first || first.enabled === false) return null;
  return first;
}
