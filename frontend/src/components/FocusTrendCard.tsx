import { Badge, Box, Group, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconChartLine } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  describeFocusTrend,
  focusVerdictBadge,
  sparklinePoints,
} from "./focusTrend";

const SPARK_W = 240;
const SPARK_H = 44;

/**
 * "Focus & sharpness" — a sparkline of each accepted sub's star size (FWHM) over
 * the target's most recent capture night, with a plain-language verdict.
 *
 * The Seestar shoots unattended for hours; a beginner has no easy way to see
 * whether their stars stayed sharp all night or drifted soft partway through
 * (dew on the lens, temperature/focus drift). This shows exactly that from data
 * already stored — read-only, and it never rejects anything. It self-hides when
 * the latest session has too few measured subs to trend (endpoint returns null).
 */
export function FocusTrendCard({ safe }: { safe: string }) {
  const trend = useQuery({
    queryKey: ["focus-trend", safe],
    queryFn: () => api.focusTrend(safe),
    enabled: !!safe,
  });
  const t = trend.data;
  if (!t) return null;

  const fwhms = t.points.map((p) => p.fwhm_px);
  const poly = sparklinePoints(fwhms, SPARK_W, SPARK_H);
  const badge = focusVerdictBadge(t.verdict);

  return (
    <Paper withBorder p="sm" radius="md" mt="xs">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <ThemeIcon size={22} radius="xl" variant="light" color="cyan"
          style={{ flexShrink: 0, marginTop: 2 }}>
          <IconChartLine size={14} />
        </ThemeIcon>
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Group gap={8} wrap="nowrap">
            <Text size="sm" fw={500}>Focus &amp; sharpness</Text>
            <Badge size="sm" variant="light" color={badge.color}>{badge.label}</Badge>
          </Group>
          <Box>
            <svg
              width="100%"
              viewBox={`0 0 ${SPARK_W} ${SPARK_H}`}
              preserveAspectRatio="none"
              role="img"
              aria-label="Star sharpness through the night (higher line = sharper)"
              style={{ maxWidth: SPARK_W, display: "block" }}
            >
              <polyline
                points={poly}
                fill="none"
                stroke="var(--mantine-color-cyan-5)"
                strokeWidth={1.5}
                strokeLinejoin="round"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
            <Group justify="space-between" gap={0}>
              <Text size="10px" c="dimmed">night start</Text>
              <Text size="10px" c="dimmed">sharper ↑</Text>
              <Text size="10px" c="dimmed">night end</Text>
            </Group>
          </Box>
          <Text size="xs" c="dimmed">{describeFocusTrend(t)}</Text>
        </Stack>
      </Group>
    </Paper>
  );
}
