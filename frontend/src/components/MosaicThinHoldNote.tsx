import { Alert, Text } from "@mantine/core";
import { IconClock } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api, type AutoStackThinHold } from "../api/client";

/**
 * "Your mosaic isn't deep enough to be worth stacking yet."
 *
 * The walk-away minimum-frames floor asks "would stacking now publish anything
 * but single-frame colour speckle?" — and on a **mosaic** the honest number is
 * not the target's sub count but how many subs land on one patch of sky. A 3×3
 * mosaic one pass in has nine subs and a picture one sub deep everywhere; the
 * count clears the floor and the picture is speckle. The scan now holds that
 * target back, which is right — but a hold nobody can see reads as an app
 * sitting idle, and the Target page's existing "waiting for more of your subs
 * to be located" note cannot speak for this case: these subs *are* located.
 *
 * So this is the same fact in the words that fit it, on the page where the
 * owner's picture lives. Self-hiding and read-only: the endpoint reports only
 * the newest finished scan, so it disappears by itself the moment a scan stacks
 * the target, and an older backend (404) or a failed fetch renders nothing.
 */
export function MosaicThinHoldNote({ safe }: { safe: string }) {
  const hold = useQuery({
    queryKey: ["autostack-thin-hold", safe],
    queryFn: () => api.autoStackThinHold(safe).catch(() => null),
    enabled: !!safe,
    staleTime: 30_000,
    retry: false,
  });
  const held: AutoStackThinHold | null = hold.data ?? null;
  // Only the mosaic case: the count case is already explained above this one by
  // the page's own "waiting for more of your subs to be located" note, and two
  // notices for one hold is exactly the banner-piling AGENTS.md §1 warns off.
  if (!held || !(held.panel_depth > 0)) return null;
  const panels = held.panels > 1 ? `${held.panels} panels` : "its panels";
  return (
    <Alert color="blue" variant="light" icon={<IconClock size={18} />}
      title="Your mosaic isn't deep enough to stack yet"
      data-testid="mosaic-thin-hold-note">
      <Text size="sm">
        {`All ${held.frames} of your subs are located — but they're spread over `
          + `${panels}, so a typical part of the picture has only `
          + `${held.panel_depth} sub${held.panel_depth === 1 ? "" : "s"} on it. `
          + `Stacking now would make a picture that's mostly single-frame noise, `
          + `so the hands-off auto-stack is waiting until each part has at least `
          + `${held.min_frames}. Keep shooting this mosaic and it will stack `
          + `itself — or use "Stack" to make one now anyway.`}
      </Text>
    </Alert>
  );
}
