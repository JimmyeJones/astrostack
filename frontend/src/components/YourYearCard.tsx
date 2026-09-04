/**
 * The way in to "Your year under the stars", on the "Your sky, so far" page.
 *
 * A card inside the page's existing flow rather than another nav link or a new
 * always-on banner: the sidebar keeps its grouping, and the year lives one click
 * from the all-time numbers it slices.
 *
 * It opens on the most recent year that actually has nights, not on the calendar
 * year — clicking in on 3 January should land on the season you just finished,
 * not on a year three days old. Self-hides when the library has no nights at
 * all, so a fresh install isn't offered an empty story.
 */
import { Card, Group, Text } from "@mantine/core";
import { IconCalendarStar, IconChevronRight } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { defaultRecapYear } from "../yourYear";

export function YourYearCard() {
  const thisYear = new Date().getFullYear();
  const { data } = useQuery({
    queryKey: ["year-recap", thisYear],
    queryFn: () => api.getYearRecap(thisYear),
    staleTime: 60_000,
    retry: false,
  });

  // No answer yet, or an older backend without the endpoint — say nothing.
  if (!data) return null;
  const years = data.years_with_data ?? [];
  if (years.length === 0 && !data.has_anything) return null;

  const year = defaultRecapYear(years, thisYear);
  // The headline only describes the year we actually asked for, so it is shown
  // only when that is the year the link goes to.
  const blurb = year === data.year && data.headline
    ? data.headline
    : `Look back at ${year} — the nights, the hours and what you saw first.`;

  return (
    <Card withBorder radius="md" padding="md" data-testid="your-year"
      component={Link} to={`/sky-so-far/${year}`}>
      <Group gap="sm" wrap="nowrap">
        <IconCalendarStar size={22} color="var(--mantine-color-yellow-5)"
          style={{ flexShrink: 0 }} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <Text fw={600}>Your {year} under the stars</Text>
          <Text size="xs" c="dimmed">{blurb}</Text>
        </div>
        <IconChevronRight size={18} color="var(--mantine-color-dimmed)"
          style={{ flexShrink: 0 }} />
      </Group>
    </Card>
  );
}
