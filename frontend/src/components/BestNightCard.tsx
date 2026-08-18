/**
 * "Your best night" — the one night of the whole hobby whose stars measured
 * smallest, named on the "Your sky, so far" page.
 *
 * The page already tallies *how much* you've collected; this is the first thing
 * on it that says one night was better than another, which is the question a
 * beginner actually asks after a few sessions ("was last Tuesday as good as it
 * felt?"). It rides on the activity calendar the Dashboard heatmap already
 * fetches and the server already caches, so it costs no extra library walk.
 *
 * Self-hiding by design: the backend returns no sharpest night until enough
 * nights carry enough measured subs to make the comparison mean something, and
 * an older backend doesn't send the field at all — either way the card renders
 * nothing rather than a hedge.
 */
import { Center, Group, Paper, Text } from "@mantine/core";
import { IconMoonStars } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { formatIntegration } from "../format";
import { bestNightLines } from "./bestNight";

export function BestNightCard() {
  const cal = useQuery({
    queryKey: ["activity-calendar"],
    queryFn: () => api.getActivityCalendar(12),
    staleTime: 60_000,
    retry: false,
  });

  const lines = bestNightLines(cal.data?.sharpest_night, formatIntegration);
  if (!lines) return null;

  return (
    <Paper withBorder p="md" radius="md" data-testid="best-night">
      <Group gap="sm" wrap="nowrap">
        <Center w={40} h={40} bg="dark.6" style={{ borderRadius: 8, flexShrink: 0 }}>
          <IconMoonStars size={22} color="var(--mantine-color-teal-4)" />
        </Center>
        <div style={{ minWidth: 0 }}>
          <Text size="xs" c="dimmed">Your best night · {lines.date}</Text>
          <Text fw={700} size="lg" lh={1.2}>{lines.value}</Text>
          <Text size="xs" c="dimmed">{lines.detail}</Text>
        </div>
      </Group>
    </Paper>
  );
}
