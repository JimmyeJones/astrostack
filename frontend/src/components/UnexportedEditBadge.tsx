import { Badge } from "@mantine/core";

/**
 * "edit not exported" — the honest label on any thumbnail that isn't the
 * picture the user made.
 *
 * Every surface that shows "your picture" serves the run's *baked* preview PNG.
 * A recipe the user saved in the editor but never exported lives only in the
 * project DB, so the picture on screen is still the plain auto-stretch of the
 * linear stack. History and the Gallery both need to say so, next to the
 * thumbnail it applies to (the one-click **Finish my edit** offer lives on the
 * Target page's hero, where there is room for it).
 *
 * One component rather than two copies of the same JSX: the wording is the whole
 * point of the label, and two surfaces explaining the same state in slightly
 * different words is exactly the drift the shared `_unexported_edit` predicate
 * was written to stop on the server side.
 */
export function UnexportedEditBadge({ show }: { show?: boolean }) {
  if (!show) return null;
  return (
    <Badge variant="light" color="violet" style={{ flexShrink: 0 }}
      title={"You saved an edit for this stack but never exported it, so this "
        + "thumbnail is the un-edited version. Open the editor to export it."}>
      edit not exported
    </Badge>
  );
}
