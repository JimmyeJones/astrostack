import { Paper } from "@mantine/core";

import type { RejectionSummary } from "../../api/client";
import { RejectionBreakdown } from "./RejectionBreakdown";

/** "Why were some frames left out?" — with a home you can actually reach.
 *
 * The breakdown has only ever rendered inside a `HoverCard.Dropdown` on the
 * badge beside the frame counts. That is fine for *reading* it with a mouse and
 * useless on a phone: a Mantine `HoverCard` has no touch affordance at all, so
 * the whole explanation — and now the one-tap fixes inside it — is unreachable
 * on the device the owner checks a night on. This is the same breakdown, in the
 * page's own grouped analysis area, where a finger can get to it.
 *
 * Nothing was taken away: the hover card stays exactly as it was for the pointer
 * user who already knows to hover the badge.
 *
 * Self-hiding: without a summary, or with nothing dropped to explain, it renders
 * nothing (so its tab doesn't appear on a target that kept every sub).
 */
export function RejectionBreakdownCard(
  { summary, onRunPlateSolve, onTryHarder, deepRescueOffered }: {
    summary: RejectionSummary | null | undefined;
    onRunPlateSolve?: () => void;
    onTryHarder?: () => void;
    deepRescueOffered?: boolean;
  },
) {
  if (!summary || summary.buckets.length === 0) return null;
  return (
    <Paper withBorder p="md" radius="md">
      <RejectionBreakdown summary={summary} onRunPlateSolve={onRunPlateSolve}
        onTryHarder={onTryHarder} deepRescueOffered={deepRescueOffered} />
    </Paper>
  );
}
