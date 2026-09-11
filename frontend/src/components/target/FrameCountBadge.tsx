import { Badge } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";

import { HintAnchor } from "../HintAnchor";

import { thinStackWarning } from "./thinStack";

/**
 * The "N frames" badge shown on a finished-picture tile, with an honest
 * thin-stack cue baked in: a healthy stack (≥5 combined frames) renders exactly
 * as the plain badge always did, but a very thin one (≤4, i.e. the owner's
 * 1-frame "gibberish" case) turns warning-coloured and carries a plain-language
 * tooltip explaining why it looks noisy. Reuses the tested `thinStackWarning`
 * helper so the copy and thresholds stay identical to the Target and Jobs pages
 * — this just carries the same honesty onto the Gallery/Dashboard grids a
 * beginner browses first, so a single-sub stack can't masquerade as a good
 * picture there.
 *
 * **`fieldFulls` is what makes that true on a mosaic** (added 2026-09-11). The
 * cue is a claim about one *pixel*, and a mosaic's frame count is not that: nine
 * subs over a 3x3 raster is one sub everywhere, and the badge stayed plain
 * because 9 > 4 while the Target page — given the same run's `field_fulls` in
 * v0.419.1 — called the very same picture a single sub. Pass the run's own
 * figure and the two surfaces agree; omit it and the badge is exactly what it
 * has always been.
 */
export function FrameCountBadge({
  nFramesUsed,
  fieldFulls,
  color,
  variant = "light",
}: {
  nFramesUsed: number;
  /** How many single-frame field-fulls of sky the run's canvas covers
   *  (`field_fulls` on the gallery/stats row). Omit / null on a single field and
   *  on an older backend — the cue is then read from the count, as before. */
  fieldFulls?: number | null;
  /** The healthy-stack badge colour for this surface (unchanged when not thin;
   *  omit to keep Mantine's default, matching a plain `<Badge variant="light">`). */
  color?: string;
  variant?: string;
}) {
  const warn = thinStackWarning(nFramesUsed, fieldFulls);
  const label = `${nFramesUsed} frames`;
  if (!warn) {
    return (
      <Badge variant={variant} color={color}>
        {label}
      </Badge>
    );
  }
  return (
    <HintAnchor label={warn.message} multiline w={260} withArrow>
      <Badge
        variant="light"
        color={warn.level === "single" ? "orange" : "yellow"}
        leftSection={<IconAlertTriangle size={12} />}
      >
        {label}
      </Badge>
    </HintAnchor>
  );
}
