import { Badge, Box, Group, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconCloud } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  describeTransparencyTrend,
  sparklinePoints,
  transparencyVerdictBadge,
} from "./transparencyTrend";

const SPARK_W = 240;
const SPARK_H = 44;

/**
 * "Clouds & haze" — a sparkline of each accepted sub's sky transparency over the
 * target's most recent capture night, with a plain-language verdict.
 *
 * Clouds and haze are the single most common reason a beginner's stack comes out
 * thin or noisy, and the app never *explains* when the sky went bad. This shows
 * exactly that from data already stored (each sub's `transparency_score`) — read-
 * only, and it never rejects anything. It also reassures the beginner that any
 * hazy subs were already auto-down-weighted. It self-hides when the latest session
 * has too few measured subs to trend (endpoint returns null).
 */
export function TransparencyTrendCard({ safe }: { safe: string }) {
  const trend = useQuery({
    queryKey: ["transparency-trend", safe],
    queryFn: () => api.transparencyTrend(safe),
    enabled: !!safe,
  });
  const t = trend.data;
  if (!t) return null;

  const scores = t.points.map((p) => p.transparency);
  const poly = sparklinePoints(scores, SPARK_W, SPARK_H);
  const badge = transparencyVerdictBadge(t.verdict);

  return (
    <Paper withBorder p="sm" radius="md" mt="xs">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <ThemeIcon size={22} radius="xl" variant="light" color="blue"
          style={{ flexShrink: 0, marginTop: 2 }}>
          <IconCloud size={14} />
        </ThemeIcon>
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Group gap={8} wrap="nowrap">
            <Text size="sm" fw={500}>Clouds &amp; haze</Text>
            <Badge size="sm" variant="light" color={badge.color}>{badge.label}</Badge>
          </Group>
          <Box>
            <svg
              width="100%"
              viewBox={`0 0 ${SPARK_W} ${SPARK_H}`}
              preserveAspectRatio="none"
              role="img"
              aria-label="Sky transparency through the night (higher line = clearer)"
              style={{ maxWidth: SPARK_W, display: "block" }}
            >
              <polyline
                points={poly}
                fill="none"
                stroke="var(--mantine-color-blue-5)"
                strokeWidth={1.5}
                strokeLinejoin="round"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
              />
            </svg>
            <Group justify="space-between" gap={0}>
              <Text size="10px" c="dimmed">night start</Text>
              <Text size="10px" c="dimmed">clearer ↑</Text>
              <Text size="10px" c="dimmed">night end</Text>
            </Group>
          </Box>
          <Text size="xs" c="dimmed">{describeTransparencyTrend(t)}</Text>
        </Stack>
      </Group>
    </Paper>
  );
}
