import { Badge, Button, Group, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconTelescope } from "@tabler/icons-react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { BestTonight, TonightPick } from "../../api/client";

// How often to re-ask. "Right now" goes stale as the sky turns, but not fast —
// ten minutes is well inside the resolution of an altitude recommendation and
// keeps an idle Dashboard from grinding the ephemeris.
const REFRESH_MS = 10 * 60 * 1000;

// Show the winner plus at most this many runners-up. One clear recommendation is
// the point; a long ranked list is the decision paralysis this replaces.
const MAX_SHOWN = 3;

/** The card's headline, or null when there's nothing worth showing (pure, tested).
 *
 * Two honest wordings, because the answer means different things depending on
 * what the app actually knows: with a location and darkness now it really is
 * "right now"; without one it's only "worth more time", and saying otherwise
 * would imply the target is up when we have no idea. */
export function pointHereTitle(data: BestTonight | undefined): string | null {
  if (!data || !data.picks.length) return null;
  return data.dark_now
    ? "Point here right now"
    : "Worth more time";
}

/** The dimmed line under the headline (pure, tested). Names how much dark sky is
 * left when we know, so "right now" carries its own deadline. */
export function pointHereSubtitle(data: BestTonight | undefined): string | null {
  if (!data || !data.picks.length) return null;
  if (data.observer === null) {
    return "Ranked by how much another hour would help. Set your location in "
      + "Settings to also see what's up right now.";
  }
  // No darkness at all tonight (a high-latitude summer): the picks are ranked on
  // depth alone, so don't imply there's a night to use them in.
  if (!data.dark_now && data.dark_minutes_left <= 0) {
    return "Ranked by how much another hour would help.";
  }
  if (!data.dark_now) return "Tonight's best use of your scope.";
  const mins = Math.max(0, Math.round(data.dark_minutes_left));
  if (mins < 60) return `About ${mins} min of dark sky left tonight.`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  const left = m === 0 ? `${h} h` : `${h} h ${m} m`;
  return `About ${left} of dark sky left tonight.`;
}

function PickRow({ pick, lead }: { pick: TonightPick; lead: boolean }) {
  return (
    <Stack gap={2}>
      <Group gap={8} wrap="wrap">
        <Text size="sm" fw={lead ? 600 : 500}>{pick.name}</Text>
        {pick.altitude_now_deg !== null ? (
          <Badge size="xs" variant="light" color={lead ? "teal" : "gray"}>
            {Math.round(pick.altitude_now_deg)}° up
          </Badge>
        ) : null}
      </Group>
      <Text size="xs" c="dimmed">{pick.reason}</Text>
      {lead ? (
        <Group gap="sm" mt={4}>
          <Button size="xs" variant="light" component={Link}
            to={`/targets/${encodeURIComponent(pick.safe)}`}>
            Open {pick.name}
          </Button>
          <Button size="xs" variant="subtle" color="gray" component={Link} to="/tonight">
            See the whole night
          </Button>
        </Group>
      ) : null}
    </Stack>
  );
}

/**
 * "Point here right now" — of the targets you've already started, which one is
 * best-placed at this moment *and* would gain most from another hour.
 *
 * The blank-page problem this solves: the sky clears unexpectedly, and a
 * beginner has no way to turn "I own eight half-finished targets" into "point at
 * this one". The Tonight planner answers "is X up on date D" once you've picked
 * X; this picks for you, from your own library, and says why in one sentence.
 *
 * Read-only and self-hiding: it never starts a capture or changes a setting, and
 * it renders nothing at all when the backend has nothing to recommend (no
 * targets, nothing above the horizon, or the night all but over) or is too old to
 * know the endpoint.
 */
export function PointHereTonightCard() {
  const q = useQuery({
    queryKey: ["best-tonight"],
    queryFn: () => api.getBestTonight(MAX_SHOWN),
    staleTime: REFRESH_MS,
    refetchInterval: REFRESH_MS,
    // An older backend 404s this; that's a quiet no-op, not an error to retry.
    retry: false,
  });
  const title = pointHereTitle(q.data);
  const subtitle = pointHereSubtitle(q.data);
  if (!q.data || !title) return null;

  const picks = q.data.picks.slice(0, MAX_SHOWN);
  return (
    <Paper withBorder p="md" radius="md" data-testid="point-here-tonight-card">
      <Group gap={8} wrap="nowrap" mb={4}>
        <ThemeIcon size={26} radius="xl" variant="light" color="teal">
          <IconTelescope size={16} />
        </ThemeIcon>
        <Text fw={600}>{title}</Text>
      </Group>
      {subtitle ? <Text size="xs" c="dimmed" mb="sm">{subtitle}</Text> : null}
      <Stack gap="md">
        {picks.map((p, i) => <PickRow key={p.safe} pick={p} lead={i === 0} />)}
      </Stack>
    </Paper>
  );
}
