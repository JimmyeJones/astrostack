import { Alert, Text } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

/**
 * "Last night's stack was held back — some of your subs aren't on disk."
 *
 * The walk-away readability preflight (v0.270.1) refuses to publish a picture
 * made thin by subs it couldn't read, and explains itself in full — but only on
 * the **Jobs** page. A beginner whose picture quietly stops updating goes to the
 * **Target** page, where their picture lives, sees a stale image and no reason
 * for it, and has no cause to go hunting through job history. So the one place
 * the hold is explained is the one place they won't look.
 *
 * This is that same fact, in the same words, on the page they actually stare at.
 * Read-only and self-clearing: the endpoint reads only the *newest* finished
 * scan, so the moment a scan stacks the target the note disappears on its own —
 * there is no dismissal to get out of sync with reality, and nothing here can
 * change any data. Best-effort: an older backend (404) or a failed fetch renders
 * nothing, exactly as before this existed.
 */
export function AutoStackHoldNote({ safe }: { safe: string }) {
  const hold = useQuery({
    queryKey: ["autostack-hold", safe],
    queryFn: () => api.autoStackHold(safe).catch(() => null),
    enabled: !!safe,
    staleTime: 30_000,
    retry: false,
  });
  const h = hold.data;
  if (!h || h.unreadable <= 0) return null;
  return (
    <Alert color="yellow" variant="light" icon={<IconAlertTriangle size={18} />}
      title="Your latest stack was held back — some subs aren't on disk right now"
      data-testid="autostack-hold-note">
      <Text size="sm">
        {`${h.unreadable} of ${h.offered} subs couldn't be read on the last scan `}
        {`(${h.readable} still readable). Stacking without them would have made a `}
        {"thinner, noisier picture than the one you already have, so it was left "}
        {"alone. This usually means a drive or network share went off-line, or a "}
        {"folder was moved. Put it back and the next scan will stack the full set "}
        {"automatically — nothing has been lost."}
      </Text>
    </Alert>
  );
}
