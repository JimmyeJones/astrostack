import { Badge, Group, Paper, Progress, Stack, Text, ThemeIcon, Tooltip } from "@mantine/core";
import { IconTelescope } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { formatIntegration } from "../format";
import {
  pickContinueTonight,
  type GoalSecondsBySafe,
  type TonightPick,
} from "../continueTonight";
import { readinessColor } from "../readiness";
import { recentreNudgeRowBadge, usableWindowNote } from "../tonight";
import {
  BEST_TONIGHT_QUERY_KEY, MAX_SHOWN, REFRESH_MS,
} from "./dashboard/PointHereTonightCard";

/**
 * "Point here tonight" — one calm recommendation of which target *you've already
 * started* to continue tonight.
 *
 * It complements the "Try something new tonight" discovery card (which suggests
 * brand-new showpieces) by answering the mid-project beginner's real question:
 * "of the things I'm already working on, where does tonight's clear sky pay off
 * most?" Rather than make them open every Target page and compare goal-progress
 * against tonight's altitude by hand, it picks the single owned target that is
 * both well-placed tonight and closest to a finished picture — reusing the
 * `/tonight` observability plan and each target's integration goal.
 *
 * Read-only and self-hiding: renders nothing until the planner returns an owned
 * target worth continuing (needs a location, an upcoming dark window, and a
 * started target that's up tonight and not already done). So it never nags a
 * user with no site set, and never duplicates the "set a location" prompt the
 * Tonight page already shows.
 *
 * It also never repeats a target the adjacent "Point here right now" card has
 * already named. The two cards read the same owned library and rank it by two
 * different rules, so on a small library they routinely picked the *same*
 * target and the Dashboard said it twice, one card apart, under two headings.
 * Skipping those names moves this card down to the next-best target — a second,
 * genuinely different suggestion — and hides it entirely when there isn't one.
 */
function windowLine(pick: TonightPick): string | null {
  const win = usableWindowNote(pick.target.usable_start_utc, pick.target.usable_end_utc);
  return win ? `Up tonight ${win}` : null;
}

function RunnerUp({ pick }: { pick: TonightPick }) {
  const win = windowLine(pick);
  const so_far = formatIntegration(pick.target.total_exposure_s ?? 0);
  return (
    <Group gap={6} wrap="nowrap" justify="space-between">
      <Text size="xs" c="dimmed" lineClamp={1}
        component={Link} to={`/targets/${pick.target.target_safe}`}
        style={{ minWidth: 0, cursor: "pointer" }}>
        {pick.target.name}
      </Text>
      <Text size="xs" c="dimmed" style={{ flexShrink: 0 }}>
        {so_far}{win ? ` · ${win.replace("Up tonight ", "")}` : ""}
      </Text>
    </Group>
  );
}

export function ContinueTonightCard() {
  const tonight = useQuery({
    queryKey: ["tonight"],
    queryFn: () => api.getTonight(),
    staleTime: 60_000,
  });
  // Goals let the pick honour a user-set integration target; the plan alone only
  // knows the per-type default. Cheap and already cached by the progress card.
  const progress = useQuery({
    queryKey: ["library-progress"],
    queryFn: api.getLibraryProgress,
    staleTime: 60_000,
  });

  // What the adjacent "Point here right now" card is already recommending. Both
  // cards rank *the same* owned library, by two deliberately different rules
  // (that card: best-placed at this moment × how much another hour cuts its
  // noise; this one: closest to a finished picture), so they frequently landed
  // on the same target and printed it twice, one card apart, under two
  // headings — the Dashboard saying the same thing twice in two voices, which
  // is exactly the "extremely busy" clutter the owner asked us to stop adding.
  // Same query key, fn and staleTime as that card, so this is a cache hit and
  // costs no extra request. `retry: false` because an older backend 404s the
  // endpoint — then there's nothing to exclude and the card behaves exactly as
  // it did before.
  const best = useQuery({
    queryKey: BEST_TONIGHT_QUERY_KEY,
    queryFn: () => api.getBestTonight(MAX_SHOWN),
    staleTime: REFRESH_MS,
    retry: false,
  });

  const goals: GoalSecondsBySafe = {};
  for (const p of progress.data ?? []) goals[p.safe] = p.goal_s;

  // Hold off while that answer is still in flight rather than render a pick we
  // may have to swap a moment later: a recommendation that changes target under
  // the reader is worse than one that arrives a beat late.
  if (best.isPending) return null;
  const alreadyShown = (best.data?.picks ?? []).map((p) => p.safe);

  const plan = pickContinueTonight(tonight.data, goals, 2, alreadyShown);
  if (!plan) return null;

  const { pick, runnersUp } = plan;
  const win = windowLine(pick);
  const subs = pick.target.frames_accepted;
  const so_far = formatIntegration(pick.target.total_exposure_s ?? 0);
  const color = pick.readiness ? readinessColor(pick.readiness.level) : "gray";
  // "Nudge 1.0° south" — how this target's *newest* picture was framed. The
  // Tonight page already shows it on its rows; this card is the surface a
  // beginner actually acts on before a session ("point here tonight"), which is
  // the one moment the advice can still change the next picture. The same
  // backend-computed phrase, rendered by the same helper, so the two screens can
  // never disagree — and silent (null) for a well-framed picture, exactly as the
  // planner is. Deliberately on this card only: the Dashboard already carries
  // two sibling planning cards, and the same sentence on all three would be
  // clutter rather than guidance.
  const nudge = recentreNudgeRowBadge(pick.target.recentre_nudge);

  return (
    <Paper withBorder p="md" radius="md">
      <Group justify="space-between" align="flex-start" mb="xs" wrap="wrap">
        <Group gap="sm" wrap="nowrap" align="flex-start">
          <ThemeIcon size={26} radius="xl" variant="light" color="teal"
            style={{ flexShrink: 0, marginTop: 2 }}>
            <IconTelescope size={16} />
          </ThemeIcon>
          <div style={{ minWidth: 0 }}>
            <Text fw={600}>Point here tonight</Text>
            <Text size="xs" c="dimmed">
              Of the targets you've started, this one's well placed tonight and
              closest to a finished picture.
            </Text>
          </div>
        </Group>
        <Text component={Link} to="/tonight" size="xs" c="teal" style={{ flexShrink: 0 }}>
          Full plan →
        </Text>
      </Group>

      <Paper withBorder p="sm" radius="sm" bg="var(--mantine-color-body)">
        <Group gap="xs" justify="space-between" wrap="nowrap" mb={4}>
          <Text size="sm" fw={600} lineClamp={1}
            component={Link} to={`/targets/${pick.target.target_safe}`}
            style={{ minWidth: 0, cursor: "pointer" }} c="var(--mantine-color-text)">
            {pick.target.name}
          </Text>
          <Text size="xs" c="dimmed" style={{ flexShrink: 0 }}>
            {subs != null ? `${subs} subs · ` : ""}{so_far}
          </Text>
        </Group>
        {win ? <Text size="xs" c="dimmed" mb={4}>{win}</Text> : null}
        {nudge ? (
          <Tooltip label={nudge.tooltip} multiline w={260} withArrow>
            <Badge mb={6} size="xs" variant="light" color={nudge.color}>
              {nudge.label}
            </Badge>
          </Tooltip>
        ) : null}
        {pick.readiness ? (
          <>
            <Progress value={Math.round(pick.readiness.fraction * 100)} color={color}
              size="sm" radius="xl" mb={4}
              aria-label={`${pick.target.name}: ${Math.round(pick.readiness.fraction * 100)}% of goal`} />
            <Text size="xs" c="dimmed">{pick.readiness.verdict}</Text>
          </>
        ) : null}
      </Paper>

      {runnersUp.length > 0 ? (
        <Stack gap={2} mt="xs">
          <Text size="xs" c="dimmed" fw={500}>Or continue:</Text>
          {runnersUp.map((r) => <RunnerUp key={r.target.target_safe} pick={r} />)}
        </Stack>
      ) : null}
    </Paper>
  );
}
