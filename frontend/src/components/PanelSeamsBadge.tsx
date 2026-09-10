import { Badge } from "@mantine/core";

import { HintAnchor } from "./HintAnchor";

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
 *
 * `grain` is the second verdict on the same picture
 * (`seestack.stackhealth.grain_verdict`), and it changes only what "even"
 * *means* here. A panel differs from its neighbours in its sky **level**, which
 * levelling removes and this chip measures, or in its **grain**, because a
 * panel shot with fewer subs is noisier and no processing puts those photons
 * back. A mosaic can be perfectly flat and still show an obvious rectangle, and
 * telling its owner "you shouldn't see seams between them" while they are
 * looking straight at one is the untruth this argument exists to remove. The
 * chip stays green and still says the panels evened out — nothing is taken
 * away — it just says which of the two things it measured.
 */
export function seamsLabel(
  verdict?: string | null, grain?: string | null,
): { label: string; color: string; help: string } | null {
  switch (verdict) {
    case "flat":
      return {
        label: "Panels even",
        color: "teal",
        help: grain === "uneven"
          ? "This mosaic's panels evened out — the sky matches across the joins, so where the picture looks grainier that's a difference in depth (fewer subs on that panel), not a step in the sky."
          : "This mosaic's panels evened out — the sky matches across the joins, so you shouldn't see seams between them.",
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
  { verdict, grain, size = "xs" }: {
    verdict?: string | null; grain?: string | null; size?: string;
  },
) {
  const v = seamsLabel(verdict, grain);
  if (!v) return null;
  return (
    <HintAnchor label={v.help} multiline w={260}>
      <Badge color={v.color} variant="light" size={size}>
        {v.label}
      </Badge>
    </HintAnchor>
  );
}
