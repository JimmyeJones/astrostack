/** The preview toolbar's controls, and the plain-language explanation of each.
 *
 * These sentences lived inline in `Editor.tsx` as `Tooltip` labels. They are
 * lifted out for one reason: **a tooltip is invisible on a phone.** Mantine's
 * `Tooltip` opens on hover or focus, and a tap on one of these buttons *runs*
 * it — so on the device the owner actually reads this app on, the only
 * explanation of "Coverage", "Star mask", "Drag to crop" and "Split" was, in
 * practice, not written at all. That is the row directly under the picture, on
 * the priority-1 screen.
 *
 * Sharing one array is the point (the `FRAME_COLUMNS` pattern): the tooltip and
 * the `PreviewToolGuide` disclosure can't drift into two different explanations
 * of the same button, and a tool added later gets its entry in both surfaces or
 * in neither.
 *
 * Three of the row's controls carried no explanation anywhere. "Compare" is the
 * one that needs it — it is the twin of "Split" and its label does not say what
 * it compares *against* — so it gets a sentence here; "Refresh" and "Zoom" say
 * what they do and are listed with the short line a reader would write for them
 * rather than left out, so the guide reads as the whole row rather than a
 * selection from it.
 */

export type PreviewToolKey =
  | "coverage" | "mask" | "cropDrag" | "compare" | "split" | "look"
  | "refresh" | "zoom";

export interface PreviewTool {
  key: PreviewToolKey;
  /** The button's resting label — what the reader sees before pressing it. */
  label: string;
  hint: string;
}

/** Keyed so `Editor.tsx` can hand a single sentence to the button's own tooltip
 * without re-typing it. */
export const PREVIEW_TOOLS: Record<PreviewToolKey, PreviewTool> = {
  coverage: {
    key: "coverage", label: "Coverage",
    hint: "Show this mosaic's frame-coverage map as a colour heatmap: yellow "
      + "where the most frames overlap, dark blue at the ragged, uncovered "
      + "edges. This is what 'Trim border' and 'Coverage leveling' act on.",
  },
  mask: {
    key: "mask", label: "Star mask",
    hint: "Show the soft mask that gates star ops (white = treated as a star)",
  },
  cropDrag: {
    key: "cropDrag", label: "Drag to crop",
    hint: "Drag the white handles on the picture to choose what to keep. While "
      + "this is on, the preview shows the picture as it goes into the crop, so "
      + "you can see what you're cutting off.",
  },
  compare: {
    key: "compare", label: "Compare",
    hint: "Swap the whole preview for the Original — your framing, with none of "
      + "your tone, colour or detail edits — then press it again (it says "
      + "\"Edited\") to come back. The quickest way to ask \"is my edit actually "
      + "better?\"",
  },
  split: {
    key: "split", label: "Split",
    hint: "Drag a divider across the preview to reveal the Original on the left "
      + "and your edit on the right in one frame — the clearest way to judge "
      + "exactly what a change did.",
  },
  look: {
    key: "look", label: "Compare a look",
    hint: "Put another look — Auto, or any preset — on the left of that same "
      + "divider instead of the Original, so you can judge \"this look vs mine\" "
      + "before switching to it.",
  },
  refresh: {
    key: "refresh", label: "Refresh",
    hint: "Render the preview again. Nothing here changes your edit; this is "
      + "for when a render was interrupted.",
  },
  zoom: {
    key: "zoom", label: "Zoom",
    hint: "Open the preview full-screen, where you can zoom in and pan around "
      + "to check stars and detail up close.",
  },
};

/** The tools actually offered, in the order the row renders them.
 *
 * `Editor.tsx` renders the row from the same two booleans, so the guide can
 * never explain a button that isn't there (or miss one that is). */
export function visiblePreviewTools(
  opts: { isMosaic: boolean; cropDrag: boolean },
): PreviewTool[] {
  const t = PREVIEW_TOOLS;
  return [
    ...(opts.isMosaic ? [t.coverage] : []),
    t.mask,
    ...(opts.cropDrag ? [t.cropDrag] : []),
    t.compare, t.split, t.look, t.refresh, t.zoom,
  ];
}
