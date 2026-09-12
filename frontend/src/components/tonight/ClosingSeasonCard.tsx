import { Anchor, Badge, Group, Paper, Stack, Text, Title } from "@mantine/core";
import { IconHourglassLow } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import {
  CLOSING_URGENT_WEEKS, CLOSING_WHY, closingHeadline, closingTargetLine,
} from "../../closingSeason";

/**
 * "Shoot these before they're gone" — your own targets whose season is ending.
 *
 * The Target page's seasonal strip already answers this for **one** target, for
 * somebody who went looking. Nobody goes looking: a season closes quietly, and
 * an owner with many targets across many nights finds out months later that the
 * autumn object he had three hours on is gone until next year. This is the
 * library-wide half, and it is the one planning answer worth putting in front of
 * someone unasked, because it expires.
 *
 * Self-hiding twice over, deliberately: nothing renders when the backend is too
 * old to know the endpoint, and nothing renders when nothing is leaving — which
 * is most of the year, and is what keeps this from becoming one more always-on
 * banner on a page the owner already calls busy.
 */
export function ClosingSeasonCard({ minAlt }: { minAlt?: number }) {
  const q = useQuery({
    queryKey: ["plan-closing", minAlt ?? null],
    queryFn: () => api.getSeasonClosing(minAlt != null ? { minAlt } : undefined),
    staleTime: 900_000,     // a season moves by the week, not by the minute
    // An older backend 404s this; that's a quiet no-op, not an error to retry.
    retry: false,
  });
  const headline = closingHeadline(q.data);
  if (!headline) return null;
  const rows = q.data?.targets ?? [];

  return (
    <Paper withBorder p="md" data-testid="closing-season">
      <Group justify="space-between" align="flex-start" mb="xs" wrap="wrap">
        <Group gap={8} wrap="nowrap">
          <IconHourglassLow size={18} />
          <Title order={4}>Shoot these before they're gone</Title>
        </Group>
        <Text size="xs" c="dimmed">
          Next {q.data?.horizon_weeks} weeks · your own targets
        </Text>
      </Group>

      <Text size="sm" fw={600}>{headline}</Text>
      <Text size="xs" c="dimmed" mb="sm">{CLOSING_WHY}</Text>

      <Stack gap={6}>
        {rows.map((t) => (
          <Group key={t.safe} gap={8} wrap="wrap" align="baseline">
            <Anchor component={Link} to={`/targets/${t.safe}`} fw={600}>
              {t.name}
            </Anchor>
            {t.weeks_left <= CLOSING_URGENT_WEEKS ? (
              <Badge size="sm" color="orange" variant="light">Last chance</Badge>
            ) : null}
            <Text size="xs" c="dimmed">{closingTargetLine(t)}</Text>
          </Group>
        ))}
      </Stack>
    </Paper>
  );
}
