import { Box, Group, Paper, Stack, Text, Tooltip } from "@mantine/core";
import { IconCalendarHeart } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  buildCalendarGrid,
  calendarHeadline,
  type DayCell,
  nightLabel,
} from "../activityCalendar";
import { formatIntegration } from "../format";

// Shade per level, 0 (no imaging) → 4 (a long night). Violet to match the
// Dashboard's accent; level 0 is a faint neutral so the grid still reads as a
// calendar on an empty stretch.
const LEVEL_BG = [
  "var(--mantine-color-dark-4)",
  "var(--mantine-color-violet-9)",
  "var(--mantine-color-violet-7)",
  "var(--mantine-color-violet-5)",
  "var(--mantine-color-violet-3)",
];

const CELL = 11;
const GAP = 3;

function Cell({ day }: { day: DayCell }) {
  const box = (
    <Box
      style={{
        width: CELL,
        height: CELL,
        borderRadius: 2,
        background: day.date ? LEVEL_BG[day.level] : "transparent",
      }}
    />
  );
  if (!day.night) return box;
  return (
    <Tooltip label={nightLabel(day.night, formatIntegration)} withArrow openDelay={100}>
      {box}
    </Tooltip>
  );
}

/**
 * "Your imaging calendar" — a GitHub-contributions-style heatmap of which nights
 * the owner actually imaged and how much, so the rhythm of the hobby is legible
 * at a glance (clear-sky runs, gaps, the streak building). Built entirely from
 * capture timestamps already on disk; renders nothing until there's a night to
 * show, so it never clutters a fresh install.
 */
export function ImagingCalendarCard() {
  const q = useQuery({
    queryKey: ["activity-calendar"],
    queryFn: () => api.getActivityCalendar(12),
    staleTime: 120_000,
  });
  const cal = q.data;
  // Nothing to celebrate yet → stay out of the way (an empty grid is just noise
  // on a brand-new library). The rest of the Dashboard already guides first use.
  if (!cal || cal.n_nights === 0) return null;

  const weeks = buildCalendarGrid(cal);
  return (
    <Paper withBorder p="sm" radius="md">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <IconCalendarHeart size={22} style={{ flexShrink: 0, marginTop: 2 }}
          color="var(--mantine-color-violet-5)" />
        <Stack gap={8} style={{ flex: 1, minWidth: 0 }}>
          <Group gap="xs" justify="space-between" wrap="nowrap">
            <Text size="sm" fw={500}>Your imaging calendar</Text>
            <Text size="xs" c="dimmed">{formatIntegration(cal.total_exposure_s)} total</Text>
          </Group>
          <Text size="sm" c="dimmed">{calendarHeadline(cal)}</Text>
          <Box style={{ overflowX: "auto", paddingBottom: 2 }}>
            <div
              role="grid"
              aria-label="Imaging activity by night"
              style={{ display: "flex", gap: GAP, width: "max-content" }}
            >
              {weeks.map((week, wi) => (
                <div key={wi} style={{ display: "flex", flexDirection: "column", gap: GAP }}>
                  {week.map((day, di) => (
                    <Cell key={day.date ?? `pad-${wi}-${di}`} day={day} />
                  ))}
                </div>
              ))}
            </div>
          </Box>
          <Group gap={6} justify="flex-end">
            <Text size="xs" c="dimmed">Less</Text>
            {LEVEL_BG.map((bg, i) => (
              <Box key={i} style={{ width: CELL, height: CELL, borderRadius: 2, background: bg }} />
            ))}
            <Text size="xs" c="dimmed">More</Text>
          </Group>
        </Stack>
      </Group>
    </Paper>
  );
}
