import { Badge, Group, Paper, Progress, Stack, Text } from "@mantine/core";
import { IconTargetArrow } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { formatIntegration } from "../format";
import {
  describeLibraryProgress,
  objectTypeLabel,
  rankLibraryProgress,
  type RankedProgress,
} from "../libraryProgress";
import { readinessColor } from "../readiness";

// Show at most this many targets so the card stays a glanceable overview on a
// large library; the rest are a "+N more" pointer to the full Library page.
const MAX_ROWS = 6;

function ProgressRow({ r }: { r: RankedProgress }) {
  const { row, readiness } = r;
  const color = readinessColor(readiness.level);
  const pct = Math.round(readiness.fraction * 100);
  // Show the object type ("galaxy"/"nebula"/…) next to the goal so a beginner
  // sees why the goal differs per target; omitted for an unrecognised type.
  const typeLabel = objectTypeLabel(readiness.bucket);
  return (
    <div>
      <Group gap="xs" justify="space-between" wrap="nowrap" mb={2}>
        <Text size="sm" fw={500} lineClamp={1} component={Link} to={`/targets/${row.safe}`}
          style={{ cursor: "pointer", minWidth: 0 }} c="var(--mantine-color-text)">
          {row.name}
        </Text>
        <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
          <Text size="xs" c="dimmed">
            {typeLabel ? `${typeLabel} · ` : ""}
            {formatIntegration(row.total_exposure_s)} of ~{readiness.goalHours}h
          </Text>
          {readiness.level === "plenty" && (
            <Badge variant="light" color={color} size="xs">plenty</Badge>
          )}
        </Group>
      </Group>
      <Progress value={pct} color={color} size="sm" radius="xl"
        aria-label={`${row.name}: ${pct}% of goal`} />
    </div>
  );
}

/**
 * "Target progress" — a small, config-free Dashboard overview of how close each
 * target is to a clean image, across the whole library. It complements the
 * per-target "Is it enough yet?" card (and the Tonight planner, which needs a
 * site location) by answering, at a glance and with zero setup, *which of my
 * targets are nearly done and which need more time?* Read-only: it reuses the
 * shared readiness verdict (per-object-type goal, honouring any user-set goal)
 * and only renders when some light has been collected. A goal is a suggestion,
 * never a gate — nothing here blocks stacking.
 */
export function LibraryProgressCard() {
  // Integration totals change only when a scan lands new frames, so a plain
  // staleTime is enough — no aggressive refetch (the endpoint opens projects).
  const q = useQuery({
    queryKey: ["library-progress"],
    queryFn: api.getLibraryProgress,
    staleTime: 60_000,
  });
  const ranked = rankLibraryProgress(q.data ?? []);
  if (ranked.length === 0) return null;

  const shown = ranked.slice(0, MAX_ROWS);
  const extra = ranked.length - shown.length;
  return (
    <Paper withBorder p="sm" radius="md">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <IconTargetArrow size={22} style={{ flexShrink: 0, marginTop: 2 }}
          color="var(--mantine-color-violet-5)" />
        <Stack gap={8} style={{ flex: 1, minWidth: 0 }}>
          <Group gap="xs" justify="space-between" wrap="nowrap">
            <Text size="sm" fw={500}>Target progress</Text>
            <Text component={Link} to="/library" size="xs" c="violet"
              style={{ flexShrink: 0 }}>
              All targets →
            </Text>
          </Group>
          <Text size="sm" c="dimmed">{describeLibraryProgress(ranked)}</Text>
          <Stack gap={8} mt={2}>
            {shown.map((r) => <ProgressRow key={r.row.safe} r={r} />)}
          </Stack>
          {extra > 0 && (
            <Text size="xs" c="dimmed">
              +{extra} more target{extra === 1 ? "" : "s"} in your Library.
            </Text>
          )}
        </Stack>
      </Group>
    </Paper>
  );
}
