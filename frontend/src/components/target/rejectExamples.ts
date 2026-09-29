/**
 * "Show me one" — the copy above a strip of frames the stack set aside.
 *
 * The breakdown already tells a beginner *how many* subs went and *why*
 * (`webapp/rejection_summary.py`). What it cannot do in words is teach the eye:
 * a first-time Seestar owner has never seen what "trailed" or "soft stars"
 * looks like in their own data, so the count is a verdict to be trusted rather
 * than a thing to recognise — and the worry underneath it ("did it throw away
 * my best frame?") is answered by looking, not by reading.
 *
 * So each strip gets one line saying **what to look for** in the pictures under
 * it. Kept here, pure, for the same reason the rest of this folder's helpers
 * are: it is wording, and wording is what gets tested.
 *
 * `null` for a bucket with no line — which is also the second guard on what can
 * render. The backend only ever sends examples for the buckets whose cause is
 * visible in the frame (`webapp/rejectexamples.py::EXAMPLE_BUCKETS`); a bucket
 * that arrived without copy here would be one somebody added on one side only,
 * and a strip of thumbnails with nothing saying what they show is a puzzle, not
 * a lesson.
 */

export type RejectExample = { frame_id: number; name: string };
export type RejectExamples = Record<string, RejectExample[]>;

const WHAT_TO_LOOK_FOR: Record<string, string> = {
  trailed:
    "look for the straight bright line running across the frame. That streak is " +
    "what would have ended up in your picture.",
  clouds:
    "there are far fewer stars than in a clear frame, often on a milky-looking " +
    "sky. Nothing was wrong with your setup — that was the weather.",
  soft:
    "the stars here are fat and fuzzy rather than tight points, so they'd have " +
    "blurred the detail in everything else.",
};

/** The line above one bucket's strip, or `null` when it should not render. */
export function exampleLead(bucketKey: string, count: number): string | null {
  const what = WHAT_TO_LOOK_FOR[bucketKey];
  if (!what || count < 1) return null;
  const lead = count === 1 ? "Here's one we set aside" : `Here are ${count} we set aside`;
  return `${lead} — ${what}`;
}

/** Does this summary have anything worth offering a "show me" for? */
export function hasRenderableExamples(examples: RejectExamples | undefined): boolean {
  if (!examples) return false;
  return Object.entries(examples).some(
    ([key, list]) => exampleLead(key, list?.length ?? 0) !== null);
}
