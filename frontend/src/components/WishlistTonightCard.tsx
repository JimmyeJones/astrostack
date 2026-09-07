import { Badge, Group, Paper, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconStarFilled } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { WishlistTonightObject } from "../api/client";
import { formatClock, formatMinutes } from "../tonight";

/**
 * "Your wishlist target M57 is up tonight."
 *
 * The wishlist is where the owner records what *they* want to shoot; this is the
 * payoff — on the right night, the app volunteers that the thing they asked for
 * is well placed, instead of making them go and check. It adds no new data and
 * no new scoring: the objects are the saved ones, and "is it up?" is the same
 * dark-window / altitude / Moon blend as every other card on the page, so a
 * wishlist line and a Tonight row can never disagree about the same object.
 *
 * Self-hiding on every "nothing to say" case — an empty wishlist, no observing
 * location, nothing saved that clears the floor, or an older backend — so a
 * fresh install sees exactly today's page.
 */
export function WishlistTonightCard({ when, minAlt }: {
  when?: string;
  minAlt?: number;
}) {
  const tonight = useQuery({
    queryKey: ["wishlist-tonight", when ?? null, minAlt ?? null],
    queryFn: () => api.wishlistTonight({ when, minAlt }).catch(() => null),
    staleTime: 5 * 60_000,
    retry: false,
  });

  const up = tonight.data?.up ?? [];
  if (up.length === 0) return null;

  return (
    <Paper withBorder p="md" data-testid="wishlist-tonight-card">
      <Group gap="sm" align="flex-start" wrap="nowrap">
        <ThemeIcon variant="light" color="yellow" size="lg" radius="xl">
          <IconStarFilled size={16} />
        </ThemeIcon>
        <Stack gap={6} style={{ minWidth: 0 }}>
          <Title order={5}>
            {up.length === 1
              ? `${objectLabel(up[0])} is on your wishlist — and it's up tonight`
              : `${up.length} objects from your wishlist are up tonight`}
          </Title>
          {up.map((o) => <WishlistLine key={o.catalog_id} o={o} />)}
          <Text size="xs" c="dimmed">
            <Link to="/life-list">See your whole wishlist</Link>
          </Text>
        </Stack>
      </Group>
    </Paper>
  );
}

/** One saved object's placement, in the same plain words the rest of the page
 *  uses: how high it gets, how long it's usable, and until when. */
function WishlistLine({ o }: { o: WishlistTonightObject }) {
  return (
    <Group gap="xs" wrap="wrap">
      <Text size="sm" fw={600}>{objectLabel(o)}</Text>
      {o.captured ? (
        <Badge size="xs" variant="light" color="teal">Already got one</Badge>
      ) : null}
      <Text size="sm" c="dimmed">
        {`climbs to about ${Math.round(o.max_altitude_deg)}°, `}
        {`${formatMinutes(o.minutes_above_min_alt)} of it usable`}
        {o.usable_end_utc ? `, until ${formatClock(o.usable_end_utc)}` : ""}
      </Text>
    </Group>
  );
}

/** "M57 (Ring Nebula)", or just the id for the many objects with no popular
 *  name — never a bare blank where a name should be. */
function objectLabel(o: { catalog_id: string; name: string }): string {
  return o.name ? `${o.catalog_id} (${o.name})` : o.catalog_id;
}
