import { Box, Group, Paper, Stack, Text, Tooltip } from "@mantine/core";
import { IconCalendarHeart } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { api } from "../api/client";
import {
  buildCalendarGrid,
  calendarHeadline,
  type DayCell,
  nightDates,
  nightLabel,
  stepNight,
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

/** The prompt in the read-out slot before anything is picked. Named so the test
 *  and the card cannot drift over the one sentence that says the map answers. */
export const CALENDAR_PROMPT = "Tap a square for that night";

function Cell(
  { day, label, selected, roving, onPick, register }: {
    day: DayCell;
    /** The night's sentence, or "" on an empty day. */
    label: string;
    selected: boolean;
    /** This is the cell that holds the grid's single tab stop. */
    roving: boolean;
    onPick: (date: string) => void;
    register: (date: string, el: HTMLDivElement | null) => void;
  },
) {
  const box = (
    <Box
      style={{
        width: CELL,
        height: CELL,
        borderRadius: 2,
        background: day.date ? LEVEL_BG[day.level] : "transparent",
        outline: selected ? "2px solid var(--mantine-color-violet-2)" : undefined,
        outlineOffset: 1,
        cursor: day.night ? "pointer" : undefined,
      }}
    />
  );
  if (!day.night || !day.date) return box;
  const date = day.date;
  return (
    <Tooltip label={label} withArrow openDelay={100}>
      <Box
        ref={(el: HTMLDivElement | null) => register(date, el)}
        role="button"
        aria-label={label}
        aria-pressed={selected}
        // Exactly one night cell is ever in the tab order (the selected one, or
        // the most recent night before anything is picked) and the arrow keys
        // walk the rest — a roving tabIndex. A tab stop *per* night would put a
        // hundred of them on the Dashboard before the rest of the page.
        tabIndex={roving ? 0 : -1}
        onClick={() => onPick(date)}
        style={{
          width: CELL,
          height: CELL,
          borderRadius: 2,
          background: LEVEL_BG[day.level],
          outline: selected ? "2px solid var(--mantine-color-violet-2)" : undefined,
          outlineOffset: 1,
          cursor: "pointer",
        }}
      />
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
  // Which night the read-out under the grid is describing, as an ISO date.
  const [picked, setPicked] = useState<string | null>(null);
  const cells = useRef(new Map<string, HTMLDivElement>());
  const register = useCallback((date: string, el: HTMLDivElement | null) => {
    if (el) cells.current.set(date, el);
    else cells.current.delete(date);
  }, []);

  const cal = q.data;
  // Nothing to celebrate yet → stay out of the way (an empty grid is just noise
  // on a brand-new library). The rest of the Dashboard already guides first use.
  if (!cal || cal.n_nights === 0) return null;

  const weeks = buildCalendarGrid(cal);
  const dates = nightDates(weeks);
  // The single tab stop: whatever is picked, else the most recent night — so one
  // Tab from the headline lands on the night the owner most likely means.
  const rovingDate = (picked && dates.includes(picked))
    ? picked
    : dates[dates.length - 1] ?? null;
  const pickedNight = picked
    ? weeks.flat().find((d) => d.date === picked)?.night ?? null
    : null;

  // Arrow keys walk the nights; the moved-to cell takes focus so the next press
  // continues from there (a roving tabIndex is only usable if focus follows it).
  const onKeyDown = (e: React.KeyboardEvent) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1
      : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1
        : null;
    if (step === null) return;
    const next = stepNight(dates, picked, step as 1 | -1);
    if (next === null) return;   // at an end: let the page have the key back
    e.preventDefault();
    setPicked(next);
    cells.current.get(next)?.focus();
  };

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
              role="group"
              aria-label="Imaging activity by night"
              onKeyDown={onKeyDown}
              style={{ display: "flex", gap: GAP, width: "max-content" }}
            >
              {weeks.map((week, wi) => (
                <div key={wi} style={{ display: "flex", flexDirection: "column", gap: GAP }}>
                  {week.map((day, di) => (
                    <Cell
                      key={day.date ?? `pad-${wi}-${di}`}
                      day={day}
                      label={day.night ? nightLabel(day.night, formatIntegration) : ""}
                      selected={!!day.date && day.date === picked}
                      roving={!!day.date && day.date === rovingDate}
                      onPick={setPicked}
                      register={register}
                    />
                  ))}
                </div>
              ))}
            </div>
          </Box>
          {/* The read-out shares the legend's own row, so answering "which night
              is that?" costs no extra height on a page the owner already calls
              busy — the words only appear where "Less … More" already sat. */}
          <Group gap={6} justify="space-between" wrap="wrap">
            <Text size="xs" c={pickedNight ? undefined : "dimmed"} style={{ minWidth: 0 }}>
              {pickedNight
                ? nightLabel(pickedNight, formatIntegration)
                : CALENDAR_PROMPT}
            </Text>
            <Group gap={6} wrap="nowrap">
              <Text size="xs" c="dimmed">Less</Text>
              {LEVEL_BG.map((bg, i) => (
                <Box key={i}
                  style={{ width: CELL, height: CELL, borderRadius: 2, background: bg }} />
              ))}
              <Text size="xs" c="dimmed">More</Text>
            </Group>
          </Group>
        </Stack>
      </Group>
    </Paper>
  );
}
