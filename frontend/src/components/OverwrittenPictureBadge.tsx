import { Badge } from "@mantine/core";

/**
 * "picture overwritten" — the honest label on a History card whose thumbnail
 * belongs to a *different* stack.
 *
 * Before v0.81.8 a re-stack wrote the canonical `master.*` straight over the
 * previous run's output, and nothing ever migrated the rows written before that
 * guard. So an old card can carry this run's frame count, integration time and
 * canvas beside the *newer* run's image: every number on it is true of this run,
 * and the picture is not. The old pixels are gone, so there is nothing to fix —
 * only something to say, which is this.
 *
 * `ownerDate` is the date of the run the file really belongs to, looked up from
 * the same list the card is rendered in (the server sends the id, not another
 * request). It is omitted rather than guessed when that run is not in view.
 *
 * Deliberately the same shape as the other per-run labels (`UnexportedEditBadge`,
 * `PanelSeamsBadge`): it sits in the badge row that already exists on the card
 * and appears only on the affected runs, so nothing is added to a page that is
 * already busy and nothing is moved for the runs this does not apply to.
 */
export function OverwrittenPictureBadge(
  { ownerRunId, ownerDate }: { ownerRunId?: number | null; ownerDate?: string },
) {
  if (ownerRunId == null) return null;
  const whose = ownerDate
    ? `the stack from ${ownerDate}`
    : "a later stack of this target";
  return (
    <Badge variant="light" color="orange" style={{ flexShrink: 0 }}
      title={"This run's own picture is gone: a later stack wrote over the same "
        + `file name, so the image here is ${whose}. The numbers on this card are `
        + "still this run's. Older versions of AstroStack overwrote a previous "
        + "stack instead of keeping it aside; versions since 0.81.8 keep both."}>
      picture overwritten
    </Badge>
  );
}
