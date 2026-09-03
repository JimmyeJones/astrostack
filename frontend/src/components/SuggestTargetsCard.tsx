import {
  Anchor, Badge, Group, Paper, Stack, Text, ThemeIcon, Tooltip,
} from "@mantine/core";
import { IconCalendarPlus, IconSparkles } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type SuggestedTarget } from "../api/client";
import { withMosaicEffort } from "../mosaicEffort";
import { difficultyRowBadge, framingRowBadge } from "../tonight";
import { describeSuggestion, suggestionHeading } from "./suggestTargets";

/**
 * "Try something new tonight" — a gentle discovery nudge on the Dashboard.
 *
 * Every other planning surface plans a target you're *already* working; this
 * answers the beginner's most common question — "what's a good, easy thing to
 * point at tonight?" — by suggesting one to three famous showpieces they haven't
 * captured that are well-placed right now (from `/api/plan/suggest`). It's the
 * distilled, beginner-friendly counterpart to the Tonight page's full ranked
 * table: a short "point the Seestar here" list rather than a wall of catalog rows.
 *
 * Read-only and self-hiding: renders nothing until the planner returns at least
 * one suggestion (needs a location, an upcoming dark window, and a showpiece the
 * library doesn't already cover). So it never nags a user with no site set, and
 * never duplicates the "set a location" prompt the Tonight page already shows.
 */
function SuggestionRow(
  { s, usualPaceS }: { s: SuggestedTarget; usualPaceS?: number | null },
) {
  // The mosaic badge also says, on hover, roughly how many clear nights all
  // those panels would take at this owner's own measured pace — silent for a
  // first-timer with no pace yet, and on an older backend.
  const framingBadge = withMosaicEffort(
    framingRowBadge(s.framing, s.mosaic), s.mosaic, s.type, usualPaceS);
  const difficultyBadge = difficultyRowBadge(s.difficulty);
  return (
    <Paper withBorder p="sm" radius="sm" bg="var(--mantine-color-body)">
      <Group justify="space-between" align="flex-start" wrap="nowrap" gap="sm">
        <Stack gap={2} style={{ minWidth: 0 }}>
          <Group gap={6} wrap="wrap">
            <Text size="sm" fw={600}>{suggestionHeading(s)}</Text>
            <Text size="xs" c="dimmed">{[s.type, s.con].filter(Boolean).join(" · ")}</Text>
            {difficultyBadge ? (
              <Tooltip label={difficultyBadge.tooltip} multiline w={240} withArrow>
                <Badge size="xs" variant="light" color={difficultyBadge.color}>
                  {difficultyBadge.label}
                </Badge>
              </Tooltip>
            ) : null}
            {framingBadge ? (
              <Tooltip label={framingBadge.tooltip} multiline w={240} withArrow>
                <Badge size="xs" variant="light" color={framingBadge.color}>
                  {framingBadge.label}
                </Badge>
              </Tooltip>
            ) : null}
          </Group>
          {s.blurb ? <Text size="xs" c="dimmed">{s.blurb}</Text> : null}
          <Text size="xs" fw={500}>{describeSuggestion(s)}</Text>
        </Stack>
        {/* One-tap "Add to calendar" so the beginner doesn't miss the night — a
            plain .ics download their own calendar imports (no account, no network). */}
        <Anchor href={api.suggestIcsUrl(s.id)} download size="xs" fw={500}
          style={{ flexShrink: 0, whiteSpace: "nowrap" }}>
          <Group gap={4} wrap="nowrap">
            <IconCalendarPlus size={13} />
            Add to calendar
          </Group>
        </Anchor>
      </Group>
    </Paper>
  );
}

export function SuggestTargetsCard() {
  const q = useQuery({
    queryKey: ["suggest-targets"],
    queryFn: () => api.suggestTargets(),
    staleTime: 60_000,
  });

  const suggestions = q.data?.suggestions ?? [];
  if (suggestions.length === 0) return null;

  return (
    <Paper withBorder p="md" radius="md">
      <Group justify="space-between" align="flex-start" mb="xs" wrap="wrap">
        <Group gap="sm" wrap="nowrap" align="flex-start">
          <ThemeIcon size={26} radius="xl" variant="light" color="grape"
            style={{ flexShrink: 0, marginTop: 2 }}>
            <IconSparkles size={16} />
          </ThemeIcon>
          <div>
            <Text fw={600}>Try something new tonight</Text>
            <Text size="xs" c="dimmed">
              Famous, easy targets you haven't shot yet — well placed right now.
              Point the Seestar and let it run.
            </Text>
          </div>
        </Group>
        <Anchor component={Link} to="/tonight" size="xs" c="grape">See all →</Anchor>
      </Group>
      <Stack gap="xs">
        {suggestions.map((s) => (
          <SuggestionRow key={s.id} s={s} usualPaceS={q.data?.usual_pace_s} />
        ))}
      </Stack>
    </Paper>
  );
}
