import { Anchor, Group, List, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconCalendarPlus, IconCalendarStar } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { describeGap, describeWindow, windowsIntro } from "./nextSession";

/**
 * "Plan your next night" — the forward-looking companion to the retrospective
 * trend cards. When a target still needs more integration to reach its readiness
 * goal, this joins that gap with the night planner's next dark window(s) into one
 * dated next step: "About 2 more clear hours (~120 more subs)… your next good
 * window: Thu 15 Jan, 22:40 → 02:10 UTC".
 *
 * Read-only and self-hiding: it renders nothing unless there's a real goal gap
 * (`gapSeconds > 0`) *and* the planner found at least one upcoming window (needs a
 * location and a solved position). So it never nags a finished target, and never
 * duplicates the "set a location" prompt the Tonight page already shows.
 */
export function NextSessionCard({
  safe,
  gapSeconds,
  subExposureSeconds,
}: {
  safe: string;
  gapSeconds: number;
  subExposureSeconds: number | null;
}) {
  const hasGap = gapSeconds > 0;
  const next = useQuery({
    queryKey: ["next-session", safe],
    queryFn: () => api.nextSession(safe),
    enabled: !!safe && hasGap,
  });

  if (!hasGap) return null;
  const windows = next.data?.windows ?? [];
  if (windows.length === 0) return null;

  return (
    <Paper withBorder p="sm" radius="md" mt="xs">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <ThemeIcon size={22} radius="xl" variant="light" color="indigo"
          style={{ flexShrink: 0, marginTop: 2 }}>
          <IconCalendarStar size={14} />
        </ThemeIcon>
        <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
          <Text size="sm" fw={500}>Plan your next night</Text>
          <Text size="xs" c="dimmed">{describeGap(gapSeconds, subExposureSeconds)}</Text>
          <Text size="xs" fw={500}>{windowsIntro(windows.length)}</Text>
          <List size="xs" spacing={2} c="dimmed" listStyleType="none" withPadding={false}>
            {windows.map((w) => (
              <List.Item key={w.dark_start_utc}>{describeWindow(w)}</List.Item>
            ))}
          </List>
          {/* Turn the plan into a reminder the beginner won't miss: a one-tap
              .ics download their own calendar imports (no account, no network). */}
          <Anchor href={api.nextSessionIcsUrl(safe)} download size="xs" fw={500}>
            <Group gap={4} wrap="nowrap">
              <IconCalendarPlus size={13} />
              Add to calendar
            </Group>
          </Anchor>
        </Stack>
      </Group>
    </Paper>
  );
}
