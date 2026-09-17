import { Badge } from "@mantine/core";

import {
  UNSTRETCHED_GALLERY_HINT, UNSTRETCHED_LABEL, showsUnstretchedChip,
} from "../unstretched";

/**
 * "Not stretched yet" — the label on a Gallery thumbnail that is still a flat
 * linear stack rather than a finished picture.
 *
 * The per-*run* half of the Library wall's chip (v0.448.0). The wall's endpoint
 * answers per target, about the one run it displays, which is the right question
 * for a wall of targets and the wrong one here: the Gallery lists every run of
 * every target, so it needs each card's own answer — `GalleryItem.finished`, off
 * the same shared `webapp/finishedpicture.py` definition.
 *
 * Silent on anything but an explicit `false` (see `showsUnstretchedChip`), so an
 * older backend that does not send the field badges nothing rather than accusing
 * every picture in the library.
 *
 * One component rather than inline JSX, for the reason `UnexportedEditBadge`
 * gives: the wording is the whole point of a label, and two surfaces explaining
 * the same state in slightly different words is the drift the shared server-side
 * predicate exists to stop.
 */
export function UnstretchedBadge({ finished }: { finished?: boolean | null }) {
  if (!showsUnstretchedChip(finished)) return null;
  return (
    <Badge variant="light" color="yellow" style={{ flexShrink: 0 }}
      title={UNSTRETCHED_GALLERY_HINT}>
      {UNSTRETCHED_LABEL}
    </Badge>
  );
}
