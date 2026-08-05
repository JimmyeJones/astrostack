import { Badge, Tooltip } from "@mantine/core";

/**
 * "Did my mosaic's panels line up?" as a small History/Gallery chip.
 *
 * The stacker measures the sky step still left between a mosaic's coverage
 * levels and the backend reads it into a verdict (`seestack.stackhealth.
 * seam_verdict`) — deliberately a *word*, not a number: the raw ratio means
 * nothing to a beginner, and the thresholds must live in exactly one place so
 * this chip and the "How's my stack?" seam note can never disagree.
 *
 * Renders nothing at all unless the run carries a verdict, which is every
 * single-field stack, every run made before the measurement existed, and the
 * ambiguous middle band where large-scale structure puts a floor under the
 * figure. So it's safe to drop in unconditionally beside the other run chips.
 */
export function seamsLabel(verdict?: string | null): { label: string; color: string; help: string } | null {
  switch (verdict) {
    case "flat":
      return {
        label: "Panels even",
        color: "teal",
        help: "This mosaic's panels evened out — the sky matches across the joins, so you shouldn't see seams between them.",
      };
    case "check":
      return {
        label: "Panels: check",
        color: "yellow",
        help: "This mosaic's panels didn't fully even out — the sky still steps where they join, so faint seams may show once it's stretched. The editor's background tools can even it out further.",
      };
    default:
      return null;
  }
}

export function PanelSeamsBadge(
  { verdict, size = "xs" }: { verdict?: string | null; size?: string },
) {
  const v = seamsLabel(verdict);
  if (!v) return null;
  return (
    <Tooltip label={v.help} multiline w={260}>
      <Badge color={v.color} variant="light" size={size}>
        {v.label}
      </Badge>
    </Tooltip>
  );
}
