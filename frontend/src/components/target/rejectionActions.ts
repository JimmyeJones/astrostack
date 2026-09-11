import { settingsLink } from "../../settingsSections";

/** Where a piece of "why were some frames left out?" advice actually leads.
 *
 * The breakdown's notes and its headline verdict tell a beginner what to do
 * ("raise the ASTAP timeout in Settings", "Run Plate Solve to include them") and
 * then leave them to find it. These map the server's stable keys onto the thing
 * the advice names, so the sentence and the way to act on it sit together.
 *
 * Two shapes, because the advice has two kinds of destination:
 *  - `route` — a screen elsewhere in the app, addressed through the typed
 *    `settingsLink` helper so a renamed Settings section is a compile error
 *    rather than a link landing on the wrong tab.
 *  - `runPlateSolve` — a control on the very page the breakdown renders on;
 *    there is nowhere to navigate *to*, so the caller supplies the handler and
 *    a card without one simply shows no button.
 *
 * Keyed rather than matched on the copy: the wording of this advice is improved
 * regularly, and a link that silently disappears when a sentence is reworded is
 * worse than no link.
 */
export type RejectionAction =
  | { kind: "route"; label: string; to: string }
  | { kind: "runPlateSolve"; label: string }
  | { kind: "deepRescue"; label: string };

const SOLVE_SETTINGS: RejectionAction = {
  kind: "route",
  label: "Open plate-solving settings",
  to: settingsLink("plate-solving"),
};

const RUN_PLATE_SOLVE: RejectionAction = {
  kind: "runPlateSolve",
  label: "Run Plate Solve",
};

const DEEP_RESCUE: RejectionAction = {
  kind: "deepRescue",
  label: "Try harder to locate these",
};

/** The action for one bucket of left-out frames, or null when its note names
 *  nothing the app can take you to (most buckets: "a satellite crossed these"
 *  has no destination, and inventing one would be noise).
 *
 *  `deepRescueOffered` is the server's answer to "would the deep-image rescue
 *  actually do something here?" (`reject-summary.deep_rescue_offered`). When it
 *  is true the un-located subs have already been offered to the plate solver and
 *  beaten it, so "Run Plate Solve" would spend the same minutes over again for
 *  the same result — the rescue **replaces** it rather than sitting beside it,
 *  because two buttons on one line is exactly the clutter the owner asked us to
 *  stop adding, and only one of them is the right next move. Plate Solve stays
 *  where it has always been, on the page itself. Defaults to false, i.e. today's
 *  behaviour, so an older backend and every ordinary target are unchanged. */
export function bucketAction(
  key: string, deepRescueOffered = false,
): RejectionAction | null {
  if (key === "solve_timeout") return SOLVE_SETTINGS;
  if (key === "unsolved") return deepRescueOffered ? DEEP_RESCUE : RUN_PLATE_SOLVE;
  return null;
}

/** The action for the headline verdict, from the server's verdict `key`.
 *
 * The high-drop verdicts are keyed `dominant:<bucket>`, so they resolve through
 * the same bucket map — one definition, and a verdict can never point somewhere
 * different from the bucket it is about. An older backend sends no key at all,
 * which reads as "no action", i.e. exactly today's behaviour. */
export function verdictAction(
  key: string | undefined | null, deepRescueOffered = false,
): RejectionAction | null {
  if (!key) return null;
  const bucket = key.startsWith("dominant:") ? key.slice("dominant:".length) : key;
  return bucketAction(bucket, deepRescueOffered);
}
