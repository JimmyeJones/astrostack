import { Badge, Tooltip } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";

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
 */
export function FrameCountBadge({
  nFramesUsed,
  color,
  variant = "light",
}: {
  nFramesUsed: number;
  /** The healthy-stack badge colour for this surface (unchanged when not thin;
   *  omit to keep Mantine's default, matching a plain `<Badge variant="light">`). */
  color?: string;
  variant?: string;
}) {
  const warn = thinStackWarning(nFramesUsed);
  const label = `${nFramesUsed} frames`;
  if (!warn) {
    return (
      <Badge variant={variant} color={color}>
        {label}
      </Badge>
    );
  }
  return (
    <Tooltip label={warn.message} multiline w={260} withArrow>
      <Badge
        variant="light"
        color={warn.level === "single" ? "orange" : "yellow"}
        leftSection={<IconAlertTriangle size={12} />}
      >
        {label}
      </Badge>
    </Tooltip>
  );
}
