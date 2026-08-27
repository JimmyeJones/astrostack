import { Badge, Group, Paper, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconConfetti } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { formatClock } from "../tonight";

/**
 * "You're one away from finishing Lyra — and it's up tonight."
 *
 * The life list answers *how many* of the famous objects you've captured, which
 * is a number you look at. This answers **what to point at next**, which is the
 * half that actually gets someone outside on a clear night — and it costs no new
 * data: the capture matching is the life list's, and the "is it up?" is the same
 * dark-window observability every other planning card uses.
 *
 * Deliberately one nudge, not a to-do list: only a constellation the owner has
 * genuinely started and is one or two objects from completing, and only the
 * single best-placed missing object gets the "tonight" line. A card that fires
 * every night about five different constellations is one a beginner learns to
 * scroll past.
 *
 * Read-only and self-hiding — nothing renders until a constellation is close, so
 * a fresh install never sees it. Best-effort: an older backend (404) or a failed
 * fetch renders nothing, exactly as before this existed.
 */
export function NearlyThereCard() {
  const near = useQuery({
    queryKey: ["nearly-there"],
    queryFn: () => api.nearlyThere().catch(() => null),
    staleTime: 5 * 60_000,
    retry: false,
  });

  const n = near.data;
  if (!n) return null;
  const tonight = n.tonight_catalog_id
    ? n.missing.find((m) => m.catalog_id === n.tonight_catalog_id) ?? null
    : null;
  const left = n.missing.length;

  return (
    <Paper withBorder p="md" data-testid="nearly-there-card">
      <Group gap="sm" align="flex-start" wrap="nowrap">
        <ThemeIcon variant="light" color="grape" size="lg" radius="xl">
          <IconConfetti size={18} />
        </ThemeIcon>
        <Stack gap={6} style={{ minWidth: 0 }}>
          <Title order={5}>
            {left === 1
              ? `You're one object away from finishing ${n.constellation}`
              : `You're ${left} objects away from finishing ${n.constellation}`}
          </Title>
          <Text size="sm" c="dimmed">
            {`You've captured ${n.captured} of the ${n.total} famous objects in `}
            {`${n.constellation}. `}
            {tonight
              ? `${objectLabel(tonight)} is well placed tonight — it climbs to about `
                + `${Math.round(tonight.max_altitude_deg ?? 0)}° and stays usable until `
                + `${formatClock(tonight.usable_end_utc)}.`
              : n.location_source === "none"
                ? "Set your observing location in Settings and this card will tell you "
                  + "when the ones you're missing are up."
                : "None of the ones you're missing are up tonight — check back another "
                  + "night, or see when they come round on the Tonight page."}
          </Text>
          <Group gap={6} wrap="wrap">
            {n.missing.map((m) => (
              <Badge key={m.catalog_id} size="sm" variant="light"
                color={m.catalog_id === n.tonight_catalog_id ? "grape" : "gray"}>
                {objectLabel(m)}
              </Badge>
            ))}
          </Group>
          <Text size="xs" c="dimmed">
            <Link to="/life-list">See your whole life list</Link>
          </Text>
        </Stack>
      </Group>
    </Paper>
  );
}

/** "M57 (Ring Nebula)", or just the id for the many objects with no popular
 *  name — never a bare blank where a name should be. */
function objectLabel(m: { catalog_id: string; name: string }): string {
  return m.name ? `${m.catalog_id} (${m.name})` : m.catalog_id;
}
