import { Badge, Tooltip } from "@mantine/core";
import type { FocusVerdict } from "./focusChips";

/**
 * A tiny, neutral per-run chip for the History list that says — at a glance —
 * whether a past stack's stars were a personal-best ("✨ sharpest yet") or came
 * out softer than that target's usual ("softer than usual", a likely focus
 * wobble that night). Purely relative to the target's own history (see
 * `focusChips`), never an absolute bar. Renders nothing when the run earned no
 * verdict, so it's safe to drop in unconditionally.
 */
export function FocusChip({ verdict }: { verdict?: FocusVerdict }) {
  if (verdict === "sharpest") {
    return (
      <Tooltip
        label="The tightest stars of any stack of this target up to this point — smaller FWHM is sharper."
        multiline w={240} withArrow
      >
        <Badge color="grape" variant="light" style={{ cursor: "help" }}>
          ✨ sharpest yet
        </Badge>
      </Tooltip>
    );
  }
  if (verdict === "soft") {
    return (
      <Tooltip
        label="Stars in this stack are noticeably wider than this target's usual — often a focus wobble that night. Worth a focus check before the next session."
        multiline w={240} withArrow
      >
        <Badge color="orange" variant="light" style={{ cursor: "help" }}>
          softer than usual
        </Badge>
      </Tooltip>
    );
  }
  return null;
}
