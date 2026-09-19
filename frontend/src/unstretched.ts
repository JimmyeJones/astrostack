/** "This picture hasn't been stretched yet" — the copy, shared by both walls.
 *
 * A linear master and a finished picture are both a dark-ish rectangle on a
 * card, and the only difference is that one of them has had its histogram
 * stretched. v0.448.0 put that on the Library wall; the Gallery is the other
 * wall, and the one where people actually *look* at pictures rather than
 * navigate past them.
 *
 * The sentences live here rather than in either route so the two surfaces cannot
 * drift into saying different things about the same picture — the same
 * arrangement `samplesPerPixel.ts` and `weightingHint.ts` use. `Library.tsx`
 * re-exports `UNSTRETCHED_HINT` so its own tests keep importing it from there.
 */

/** The plain-language sentence behind the "Not stretched yet" chip.
 *
 * Deliberately says what to *do* — and since the chip itself is the control
 * (see :func:`unstretchedEditPath`), it can name the one click rather than the
 * vaguer "open it" it said while the whole card was a single link to the
 * target and the run's editor was a screen further in.
 */
export const UNSTRETCHED_HINT =
  "This is the stack straight out of the stacker, so almost all of it is "
  + "squashed into the darkest part of the range. Click this chip to open it "
  + "in the editor — it starts you off with Auto, and it's reversible.";

/** The chip's label. One string, so the two walls read identically. */
export const UNSTRETCHED_LABEL = "Not stretched yet";

/** The hint for a card that is unstretched **because the edit on it was never
 * exported** — a different state, wanting the opposite advice.
 *
 * `UNSTRETCHED_HINT` says "press Auto", which is exactly what somebody who
 * already has a saved edit must not be told: Auto replaces the recipe in the
 * editor, so following that advice discards their own work. It is also simply
 * wrong about the cause — they *did* stretch this picture; what is missing is
 * the export that would put it in the bytes.
 *
 * Worded from `UnexportedEditBadge`'s title, which History, the Gallery and the
 * Target hero already show for this state, so a fourth surface is not a fourth
 * explanation. This is a hint rather than a second chip: the card gets one
 * badge either way, and the owner's standing complaint about this app is
 * clutter.
 */
export const UNSTRETCHED_UNEXPORTED_HINT =
  "You saved an edit for this picture but never exported it, so the card still "
  + "shows the un-edited version. Click this chip to open it in the editor and "
  + "export your edit — don't press Auto, which would replace what you saved.";

/** The hint to show on a Library card, given whether its edit is unexported. */
export function unstretchedHint(unexportedEdit?: boolean): string {
  return unexportedEdit ? UNSTRETCHED_UNEXPORTED_HINT : UNSTRETCHED_HINT;
}

/** The Gallery's variant of the hint, which names the button that fixes it.
 *
 * Both walls now promise one click; they just point at different controls.
 * A Gallery card already carries an **Edit image** button straight to that
 * run's editor — which, since v0.390.0, opens on Auto rather than on a nudge to
 * press it — so the honest hint here points at the control already on the card,
 * and a second link beside it would be the kind of duplicate surface the
 * owner's standing clutter complaint is about. The Library card has no such
 * button and no room for one, so there the *chip itself* is the control
 * (`unstretchedEditPath`) and `UNSTRETCHED_HINT` says so.
 */
export const UNSTRETCHED_GALLERY_HINT =
  "This is the stack straight out of the stacker, so almost all of it is "
  + "squashed into the darkest part of the range. Press \"Edit image\" below — "
  + "the editor starts you off with Auto, and it's reversible.";

/** Should the chip render for this run?
 *
 * Only on an explicit `false`. `undefined`/`null` is "the backend didn't say",
 * which is what an older build serves and what a run the endpoint skipped looks
 * like — and a chip that appears because a field is *missing* would accuse every
 * picture on an upgrading install of being unfinished.
 */
export function showsUnstretchedChip(finished: boolean | null | undefined): boolean {
  return finished === false;
}

/** Where the Library wall's chip goes: that target's *displayed* run, in the
 * editor.
 *
 * The last open piece of the wall-chip feature's "one-click deep link" slice.
 * The Gallery answered it without a new control — its card already carries an
 * **Edit image** button — and the Library card could not, because it names a
 * *target* and the editor needs a *run*. The run has been on the wire since
 * v0.448.0 (`UnstretchedItem.run_id`, the run `displayed_picture_run` picked),
 * so the missing half was only ever the link.
 *
 * Built here rather than inline so the chip and its own hint sentence are
 * written next to each other — the hint promises one click, and this is the
 * click.
 */
export function unstretchedEditPath(safe: string, runId: number): string {
  return `/targets/${safe}/edit/${runId}`;
}

/** Can this item's chip be a link?
 *
 * `run_id` has been served since the endpoint shipped, but a response that
 * omits it (an older backend, a field that failed to serialise) must degrade to
 * the plain chip the wall had before rather than to a link at `…/edit/0` — the
 * same "absent is not a value" rule the endpoint's own fields follow.
 */
export function unstretchedIsLinkable(runId: number | null | undefined): boolean {
  return typeof runId === "number" && Number.isFinite(runId) && runId > 0;
}
