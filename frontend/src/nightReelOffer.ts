import { formatEtaSeconds } from "./jobEta";

/**
 * "Build the night-by-night reel" — the offer shown on a target that holds the
 * reel's subs but has no reel.
 *
 * The "night after night" card animates a target across *successive* stacks, so
 * it self-hides on a target stacked once — which, on a walk-away install, is the
 * common shape: six nights of subs went in, one stack came out, and the switch
 * that would have snapshotted it night by night (`save_progress`, an advanced
 * Stack-form field, off by default) was never found. The subs are all there. The
 * only thing missing is somebody ticking the box.
 *
 * So this is the same card saying *how to get* what it exists to show, and the
 * backend decides when there is honestly something to offer
 * (`webapp/reeloffer.py` — one stack, no reel already, ≥3 nights by both the
 * owner's and the engine's bucketing, no lucky-imaging re-order).
 *
 * The wording has two jobs beyond the pitch, both about not surprising anyone
 * who presses it:
 *
 * - **the snapshots are free, the stacking is not.** The accumulator is already
 *   cumulative, so snapshotting it at the night boundaries costs no extra pass
 *   (see `_QuickLook`); what it costs is stacking those subs again, and the run
 *   itself recorded how long that took last time. A clip is a small pleasure —
 *   an hour of NAS the reader didn't expect to spend is not.
 * - **it adds a stack.** A fresh run is the newest run, and the newest run with
 *   a preview is what the Library wall shows, so the picture on the wall becomes
 *   the new (linear) stack. Saying so is the difference between a delight and
 *   the surprise `docs/IMPROVEMENTS.md` tracks as observer issue #903.
 */

export type NightReelOffer = {
  /** The run whose settings the Stack form pre-fills from. */
  run_id: number;
  /** Observing nights that one stack holds, the owner's way (the Nights card's). */
  nights: number;
  /** Subs it combined — what a re-stack would do again. */
  subs: number;
  /** Wall clock of that run, or null for a run recorded before the column. */
  last_duration_s?: number | null;
};

function withThousands(n: number): string {
  return Math.round(n).toLocaleString();
}

/** The pitch: what the clip would be, and why there isn't one yet. */
export function nightReelOfferBlurb(
  name: string | null | undefined,
  offer: NightReelOffer,
): string {
  const clean = (name ?? "").trim() || "your target";
  return `Watch ${clean} fill in night by night — your first night, then that ` +
    `night plus the next, and so on up to all ${offer.nights}. You stacked it ` +
    `in one go, so there's no clip of it yet; stacking it once more with ` +
    `“Save a ‘watch it appear’ clip” switched on makes one.`;
}

/**
 * The cost and the consequence, in that order — the two things somebody about
 * to press the button has not been told. Never `null`: both halves are true of
 * every offer, and the time clause simply drops on a run with no recorded
 * duration rather than being guessed at.
 */
export function nightReelOfferCost(offer: NightReelOffer): string {
  const subs = offer.subs > 0 ? `your ${withThousands(offer.subs)} subs` : "your subs";
  const secs = offer.last_duration_s;
  const time = typeof secs === "number" && Number.isFinite(secs) && secs > 0
    ? `about ${formatEtaSeconds(secs)}, going by how long that stack took`
    : "as long as that stack took";
  return `The snapshots are taken as the stack runs, so they add no time of ` +
    `their own — it's stacking ${subs} again that takes ${time}. And it adds a ` +
    `stack rather than replacing one: the stack you have now stays in History, ` +
    `and the new one becomes this target's picture.`;
}

/**
 * Where the button goes: the target's own Stack form, pre-filled from the run
 * being repeated (`?from=`), with the Advanced disclosure open (`?open=advanced`)
 * so the switch is on screen rather than folded away, and `?reel=1` to default
 * that switch on. All three are *defaults* the reader can still change — the
 * offer sets the form up, it does not start a job.
 */
export function nightReelStackHref(safe: string, offer: NightReelOffer): string {
  return `/targets/${encodeURIComponent(safe)}/stack` +
    `?from=${offer.run_id}&open=advanced&reel=1`;
}
