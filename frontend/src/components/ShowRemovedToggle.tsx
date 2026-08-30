import { ActionIcon, Tooltip } from "@mantine/core";
import { IconSparkles } from "@tabler/icons-react";

/**
 * "Show what was removed" as a full-screen *view* control.
 *
 * The tint itself has existed on the History run card since v0.299.0, but that
 * card draws a 180 px thumbnail — at which size a satellite trail is a couple of
 * cyan pixels. The full-screen viewer is where a beginner actually studies their
 * picture, so it is where "these marks are what stacking cleaned out" lands.
 *
 * Only render it where the run really has a map to show (`has_rejection_map`,
 * i.e. `StackOptions.record_rejection_map` was on for that stack — off by
 * default, so most runs get no control at all rather than one that does
 * nothing). Off by default: the picture is the point; the tint answers a
 * question the viewer has to ask.
 */
export function ShowRemovedToggle(
  { on, onChange }: { on: boolean; onChange: (on: boolean) => void },
) {
  return (
    <Tooltip
      label={on ? "Hide what stacking removed" : "Show what stacking removed"}
    >
      <ActionIcon
        size="lg" variant={on ? "light" : "subtle"} color={on ? "cyan" : "gray"}
        data-testid="show-removed-view"
        aria-label={on
          ? "Hide what stacking removed"
          : "Show what stacking removed"}
        aria-pressed={on}
        onClick={() => onChange(!on)}
      >
        <IconSparkles size={20} />
      </ActionIcon>
    </Tooltip>
  );
}
