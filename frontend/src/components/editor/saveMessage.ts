import type { OpInstance } from "../../api/client";

/**
 * What to say after the editor's **Save** succeeds.
 *
 * Save and Export sit next to each other and both sound final, and Save's
 * confirmation used to be the bare word "Recipe saved" — so a beginner
 * reasonably believed pressing it had made their picture. It hadn't: a saved
 * recipe lives in the project DB and nowhere else, while the Target page, the
 * Gallery, History and everything they share keep serving the run's *baked*
 * preview. v0.261.0 taught those surfaces to admit that after the fact; this is
 * the same truth said at the moment the misunderstanding is created.
 *
 * Deliberately one sentence in the existing notification rather than a new
 * always-on block — the IA overhaul's whole point is not to add another banner.
 *
 * Saving a recipe with nothing enabled *clears* the look rather than leaving an
 * unfinished one, so it keeps the plain confirmation: nothing is waiting to be
 * exported and nagging would be wrong.
 */
export function saveRecipeMessage(ops: Pick<OpInstance, "enabled">[]): string {
  const active = ops.filter((o) => o.enabled !== false).length;
  if (active === 0) return "Recipe saved";
  return "Saved — this look is kept with the picture. Press Export to make it " +
    "the picture shown everywhere else.";
}
