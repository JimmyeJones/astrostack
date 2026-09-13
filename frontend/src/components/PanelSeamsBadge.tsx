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
 *
 * **…and it has to say that in the label, not only in the help** *(2026-09-13,
 * found by `agent-dogfood.sh --mosaic`)*. The first fix reached the tooltip and
 * left the word on the chip reading `Panels even`, so on the bundled mosaic
 * sample — 23 % of the picture 3 subs deep where the rest has 6, which the
 * health panel calls "about 1.4× grainier" in the same breath — History's card
 * showed a green `PANELS EVEN` and nothing else. `HintAnchor` does make the
 * sentence tappable on a phone, so it is reachable; but the chip is *read*
 * far more often than it is asked, and on the Gallery and Compare cards, where
 * a beginner chooses between two pictures, this chip is the only thing on the
 * row that knows anything about the panels at all. So when the grain is uneven
 * the label names **both** measurements. The verdict, the colour and the help
 * are untouched, and a run with no grain measurement — every single field,
 * every evenly-covered mosaic, every run recorded before the column existed and
 * every older backend — is byte-for-byte the chip it has always been.
 */
export function seamsLabel(
  verdict?: string | null, grain?: string | null,
): { label: string; color: string; help: string } | null {
  switch (verdict) {
    case "flat":
      return {
        // "Sky even" rather than "Panels even" because the sky level is what
        // this verdict measured; "one part thinner" is the app's own plain word
        // for the other half (the health note's "Part of this mosaic is thinner
        // than the rest"), kept out of the glossary term "panel depth" so the
        // chip needs no lookup to be read.
        label: grain === "uneven" ? "Sky even, one part thinner" : "Panels even",
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
