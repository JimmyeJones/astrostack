import { Badge, Group, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconMoon } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api, type MoonInterference } from "../api/client";

/**
 * "Is the Moon going to wash this out tonight?" — a plain-language Moon-
 * interference readout for this target.
 *
 * A bright Moon near a faint target floods the sky background and buries the
 * signal — the single biggest avoidable reason a beginner's faint-nebula night
 * disappoints — and a non-expert has no intuition for it. This turns the offline
 * ephemeris (Moon phase / illumination, its altitude, and its separation from
 * this target at tonight's darkest moment) into one honest verdict + sentence, so
 * a beginner can point at a bright galaxy or cluster instead before wasting a
 * clear night.
 *
 * Read-only and self-hiding: renders nothing until the planner returns a reading
 * (needs a saved location and a solved position), so it never nags and never
 * duplicates the "set a location" prompt the Tonight page already shows.
 */

/** Mantine colour for a Moon-interference level — gentle, never alarming. */
export function moonLevelColor(level: MoonInterference["level"]): string {
  switch (level) {
    case "good":
      return "teal";
    case "ok":
      return "yellow";
    case "poor":
      return "orange";
  }
}

/** Short chip label for the level, so the verdict reads at a glance. */
export function moonLevelLabel(level: MoonInterference["level"]): string {
  switch (level) {
    case "good":
      return "Good tonight";
    case "ok":
      return "So-so";
    case "poor":
      return "Poor for faint targets";
  }
}

export function MoonInterferenceCard({ safe }: { safe: string }) {
  const q = useQuery({
    queryKey: ["moon-interference", safe],
    queryFn: () => api.moonInterference(safe),
    enabled: !!safe,
  });

  const moon = q.data?.moon;
  if (!moon) return null;

  const pct = Math.round(moon.illumination * 100);
  const color = moonLevelColor(moon.level);

  return (
    <Paper withBorder p="sm" radius="md" mt="xs">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <ThemeIcon size={22} radius="xl" variant="light" color={color}
          style={{ flexShrink: 0, marginTop: 2 }}>
          <IconMoon size={14} />
        </ThemeIcon>
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Group gap="xs" wrap="nowrap" justify="space-between">
            <Text size="sm" fw={500}>Moon tonight</Text>
            <Badge color={color} variant="light" size="sm">
              {moonLevelLabel(moon.level)}
            </Badge>
          </Group>
          <Text size="xs" c="dimmed">{moon.text}</Text>
          <Text size="xs" c="dimmed">
            {moon.phase_name} · {pct}% lit
          </Text>
        </Stack>
      </Group>
    </Paper>
  );
}
