import { Group, Paper, Progress, Stack, Text, ThemeIcon } from "@mantine/core";
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
import { usableWindowNote } from "../tonight";

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

  const goals: GoalSecondsBySafe = {};
  for (const p of progress.data ?? []) goals[p.safe] = p.goal_s;

  const plan = pickContinueTonight(tonight.data, goals);
  if (!plan) return null;

  const { pick, runnersUp } = plan;
  const win = windowLine(pick);
  const subs = pick.target.frames_accepted;
  const so_far = formatIntegration(pick.target.total_exposure_s ?? 0);
  const color = pick.readiness ? readinessColor(pick.readiness.level) : "gray";

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
