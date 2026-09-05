import { Anchor, Paper, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import { useMosaicAim } from "../../hooks/useMosaicAim";

// The Tonight page is "the whole night", so it shows more than the Dashboard
// card's three — but still a ranking a beginner can read, not the whole library.
const MAX_SHOWN = 8;

/**
 * The depth-only ranking, for the two nights the planner can't place anything.
 *
 * `/api/plan` returns an empty `targets` list when there's no observing location,
 * so the Tonight page had nothing to show but a "set your location" prompt — even
 * though `/api/plan/best-tonight` (the same planner, the same library) *does*
 * answer that case by ranking on "would another hour help?" alone. The Dashboard's
 * "Worth more time" card already renders exactly that, and its lead pick links
 * here with **See the whole night** — so the one page dedicated to planning was
 * strictly emptier than the card that sent you to it. Same story on a
 * high-latitude summer night, where there is no dark window to place anything in.
 *
 * When the top-ranked target is a **mosaic with a thin panel**, its row also
 * says *which corner* — this is the page a beginner opens to decide where to
 * point, and for the §1 owner (a heavy mosaic user) "which target" is only half
 * that decision. Shared with the Dashboard's card through `useMosaicAim`, on the
 * same cache entry as the Target page's own map, so no surface can name a
 * different panel and none of them costs a second request.
 *
 * Self-hiding: renders nothing when the backend has no picks (an empty library,
 * or a target with no position) or is too old to know the endpoint, so the page
 * falls back to exactly today's behaviour.
 */
export function WorthMoreTimeList({ limit = MAX_SHOWN }: { limit?: number }) {
  const q = useQuery({
    queryKey: ["best-tonight", limit],
    queryFn: () => api.getBestTonight(limit),
    staleTime: 60_000,
    // An older backend 404s this; that's a quiet no-op, not an error to retry.
    retry: false,
  });
  const picks = q.data?.picks ?? [];
  // The lead pick only: this list runs to eight rows, and a project read per row
  // to annotate targets nobody is being told to shoot first is a cost with no
  // reader. Silent on a single field, an even mosaic, and an older backend.
  const aim = useMosaicAim(picks[0]?.safe);
  if (picks.length === 0) return null;
  return (
    <Paper withBorder p="md" data-testid="worth-more-time">
      <Title order={4} mb="xs">Worth more time</Title>
      <Text size="sm" c="dimmed" mb="sm">
        Nothing above can say what's up right now — but this still can: the
        targets you've already started, ranked by how much another hour on each
        would improve it.
      </Text>
      <Stack gap="sm">
        {picks.map((p, i) => (
          <div key={p.safe}>
            <Anchor component={Link} fw={600}
              to={`/targets/${encodeURIComponent(p.safe)}`}>
              {p.name}
            </Anchor>
            <Text size="xs" c="dimmed">{p.reason}</Text>
            {i === 0 && aim ? (
              <Text size="xs" c="dimmed" data-testid="worth-more-time-aim">{aim}</Text>
            ) : null}
          </div>
        ))}
      </Stack>
    </Paper>
  );
}
