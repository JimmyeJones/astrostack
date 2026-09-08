import { useMemo, useState } from "react";
import {
  Anchor, Badge, Button, Card, Center, Group, Image, Loader, Progress, SegmentedControl,
  SimpleGrid, Stack, Text, Title, Tooltip,
} from "@mantine/core";
import {
  IconChecklist, IconCircleCheck, IconDownload, IconStarFilled,
} from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type LifeListItem, type WishlistItem } from "../api/client";
import { QueryError } from "../components/QueryError";
import { WishlistStar } from "../components/WishlistStar";

// "My life list" — the collection view.
//
// The app already ranks what is up *tonight* and tracks integration on *one*
// target; neither answers the question a beginner is actually counting, which is
// "how many of the 110 have I got?". Capturing the Messier list is the classic
// milestone, so this page shows all of them at once: the ones already captured
// lit up and linked to their picture, the rest as a motivating to-shoot list.
//
// Everything here is read-only and offline — the catalog ships with the app and
// the match is done server-side against plate-solved target centres.

type Filter = "all" | "captured" | "todo";

// How many not-yet-shot tiles the "All" view draws before the rest go behind a
// count. The whole catalog rendered eagerly made this the tallest page in the
// app by nearly 3× — 14,584 px on a 420 px phone, about 17 screens of scrolling
// to reach anything — and every one of those screens was objects the owner
// hasn't got yet, scrolled past to find the ones they have. Nothing is removed
// (the owner's standing rule): the remainder is one tap away, and asking for
// "Still to shoot" explicitly still lists every one of them.
const TODO_PREVIEW = 12;

/** "Galaxy in Andromeda" — the tile's one-line identity, in plain words. */
function describe(item: LifeListItem): string {
  const type = item.type ? item.type[0].toUpperCase() + item.type.slice(1) : "Deep-sky object";
  return item.con ? `${type} in ${item.con}` : type;
}

function ObjectTile({ item }: { item: LifeListItem }) {
  // The catalog id is the stable label ("M31"); the popular name is a bonus that
  // many entries simply don't have, so it never carries the tile on its own.
  const title = item.name ? `${item.catalog_id} · ${item.name}` : item.catalog_id;
  return (
    // The star is a *sibling* of the tile, not a child: a captured tile is a
    // <Link>, and a <button> inside an <a> is invalid HTML that swallows one of
    // the two clicks. Positioned top-left so it never lands on the "Got it"
    // badge at top-right.
    <div style={{ position: "relative" }}>
      <TileBody item={item} title={title} />
      <div style={{ position: "absolute", top: 6, left: 6, zIndex: 3 }}>
        <WishlistStar catalogId={item.catalog_id} label={title} size="xs" />
      </div>
    </div>
  );
}

function TileBody({ item, title }: { item: LifeListItem; title: string }) {
  const body = (
    <Card
      withBorder padding="xs" radius="md" h="100%"
      // Captured tiles are full strength and uncaptured ones recede, so the
      // collection reads at a glance without either half becoming invisible.
      style={{ opacity: item.captured ? 1 : 0.55 }}
    >
      <Card.Section style={{ position: "relative" }}>
        {item.thumbnail_url ? (
          <Image src={item.thumbnail_url} h={110} fit="cover" bg="#000" alt="" />
        ) : (
          <Center h={110} bg="dark.7">
            <Text size="xs" c="dimmed">{item.captured ? "Not stacked yet" : "Not captured"}</Text>
          </Center>
        )}
        {item.captured ? (
          <Badge
            variant="filled" color="teal" size="sm"
            leftSection={<IconCircleCheck size={11} />}
            styles={{ root: { position: "absolute", top: 6, right: 6, zIndex: 2 } }}
          >
            Got it
          </Badge>
        ) : null}
      </Card.Section>

      <Text fw={600} size="sm" mt={6} truncate title={title}>{title}</Text>
      <Text size="xs" c="dimmed" truncate>{describe(item)}</Text>
    </Card>
  );

  // A captured object leads to its own target page — the whole point of lighting
  // it up is that the picture is one click away. An uncaptured one has nowhere
  // to go yet, so it stays a plain tile with its blurb on hover.
  if (item.captured && item.safe_name) {
    return (
      <Link to={`/targets/${item.safe_name}`} style={{ textDecoration: "none", color: "inherit" }}>
        {body}
      </Link>
    );
  }
  return item.blurb
    ? <Tooltip label={item.blurb} multiline w={300} openDelay={300}>{body}</Tooltip>
    : body;
}

function Grid({ items }: { items: LifeListItem[] }) {
  return (
    <SimpleGrid cols={{ base: 2, xs: 3, sm: 4, md: 5, lg: 6 }} spacing="sm">
      {items.map((i) => <ObjectTile key={i.catalog_id} item={i} />)}
    </SimpleGrid>
  );
}

function Section({ title, note, items, filter }: {
  title: string; note: string; items: LifeListItem[]; filter: Filter;
}) {
  const [expanded, setExpanded] = useState(false);
  const shown = items.filter((i) =>
    filter === "all" || (filter === "captured" ? i.captured : !i.captured));
  // Catalog order is kept inside each half — this only groups them, so the ones
  // the owner actually has come first instead of being scattered through a
  // hundred greyed-out tiles.
  const got = shown.filter((i) => i.captured);
  const todo = shown.filter((i) => !i.captured);
  // "Still to shoot" is the list the user just asked for, so it is never
  // shortened there; only the mixed "All" view collapses its tail.
  const collapsible = filter === "all" && !expanded && todo.length > TODO_PREVIEW;
  const todoShown = collapsible ? todo.slice(0, TODO_PREVIEW) : todo;
  const bothHalves = got.length > 0 && todo.length > 0;
  return (
    <Stack gap="xs">
      <div>
        <Title order={4}>{title}</Title>
        <Text size="sm" c="dimmed">{note}</Text>
      </div>
      {shown.length === 0 ? (
        <Text size="sm" c="dimmed">
          {filter === "captured"
            ? "None of these yet — every one of them is still ahead of you."
            : "You've got every one of these. Nothing left on this list!"}
        </Text>
      ) : (
        <>
          {got.length > 0 ? (
            <>
              {bothHalves ? (
                <Text size="xs" c="dimmed" fw={600}>Got it · {got.length}</Text>
              ) : null}
              <Grid items={got} />
            </>
          ) : null}
          {todo.length > 0 ? (
            <>
              {bothHalves ? (
                <Text size="xs" c="dimmed" fw={600}>Still to shoot · {todo.length}</Text>
              ) : null}
              <Grid items={todoShown} />
              {collapsible ? (
                <Anchor component="button" type="button" size="sm"
                        onClick={() => setExpanded(true)}>
                  Show all {todo.length} still to shoot
                </Anchor>
              ) : null}
              {filter === "all" && expanded && todo.length > TODO_PREVIEW ? (
                <Anchor component="button" type="button" size="sm"
                        onClick={() => setExpanded(false)}>
                  Show fewer
                </Anchor>
              ) : null}
            </>
          ) : null}
        </>
      )}
    </Stack>
  );
}

/**
 * "My wishlist" — the objects the owner picked out for themselves.
 *
 * The list below it is a *fixed* catalogue: you can tick things off it but you
 * can't tell it what you actually want next. This is that half, and it sits at
 * the top because your own shortlist beats a hundred greyed-out tiles.
 *
 * Self-hiding: nothing renders until something is starred, so a fresh install
 * and an older backend both see exactly today's page (the standing rule that a
 * new feature must not become one more always-on banner).
 */
function WishlistSection() {
  const list = useQuery({
    queryKey: ["wishlist"],
    queryFn: () => api.getWishlist().catch(() => null),
    staleTime: 60_000,
    retry: false,
  });

  const items = list.data?.items ?? [];
  if (items.length === 0) return null;
  const captured = list.data?.counts.captured ?? 0;

  return (
    <Card withBorder radius="md" padding="md">
      <Group gap="xs" mb={4}>
        <IconStarFilled size={16} color="var(--mantine-color-yellow-5)" />
        <Title order={4}>My wishlist</Title>
      </Group>
      <Text size="sm" c="dimmed" mb="sm">
        {captured === 0
          ? `${items.length === 1 ? "One object" : `${items.length} objects`} you said you want to shoot. `
            + "The Tonight page will tell you when one of them is well placed."
          : `You've captured ${captured} of the ${items.length} you saved. `
            + "The Tonight page tells you when the rest are well placed."}
      </Text>
      <SimpleGrid cols={{ base: 2, xs: 3, sm: 4, md: 5, lg: 6 }} spacing="sm">
        {items.map((i) => <WishlistTile key={i.catalog_id} item={i} />)}
      </SimpleGrid>
    </Card>
  );
}

/** A wishlist row reuses the life-list tile — same shape, same "Got it" badge,
 *  same star (which un-saves it here). The two lists are the same objects seen
 *  two ways, so they should not look like two different things. */
function WishlistTile({ item }: { item: WishlistItem }) {
  return (
    <ObjectTile item={{
      catalog_id: item.catalog_id,
      name: item.name,
      type: item.type,
      con: item.con,
      blurb: item.blurb,
      size_arcmin: item.size_arcmin,
      captured: item.captured,
      safe_name: item.safe_name,
      target_name: item.target_name,
      sep_deg: null,
      thumbnail_url: item.thumbnail_url,
    }} />
  );
}

export function LifeListView() {
  const list = useQuery({ queryKey: ["lifeList"], queryFn: () => api.getLifeList() });
  const [filter, setFilter] = useState<Filter>("all");

  const headline = useMemo(() => {
    const c = list.data?.counts;
    if (!c) return "";
    const left = c.messier_total - c.messier_captured;
    if (c.messier_captured === 0) {
      return `All ${c.messier_total} Messier objects are still ahead of you — pick one and point the scope at it tonight.`;
    }
    if (left === 0) {
      return `You've captured all ${c.messier_total} Messier objects. That's the whole list — congratulations.`;
    }
    return `You've captured ${c.messier_captured} of ${c.messier_total} Messier objects — ${left} to go.`;
  }, [list.data]);

  if (list.isError && !list.data) {
    return <QueryError error={list.error} onRetry={() => list.refetch()} />;
  }
  if (list.isLoading || !list.data) {
    return <Center h={300}><Loader /></Center>;
  }

  const { messier, other, counts } = list.data;

  return (
    <Stack>
      <Group gap="xs">
        <IconChecklist size={24} />
        <Title order={2}>My life list</Title>
      </Group>

      <Card withBorder radius="md" padding="md">
        <Text fw={600}>{headline}</Text>
        <Progress
          value={(counts.messier_captured / Math.max(counts.messier_total, 1)) * 100}
          color="teal" size="lg" radius="xl" mt="sm"
          aria-label="Messier objects captured"
        />
        <Text size="sm" c="dimmed" mt="sm">
          An object counts as captured once you have frames of it and the app has
          worked out where they point — so a target still waiting to be located
          stays greyed out until it's solved. Tap anything you've got to jump
          straight to its picture, or tap its ☆ to put it on your wishlist.
        </Text>
        {/* The shareable half of the same fact, one tap along and inside this
            card rather than as another block on the page (the standing rule
            that a new feature joins a grouping instead of becoming one more
            banner). Self-hides until something is captured — a grid of grey
            squares is a picture of Messier's catalogue, not of your sky, which
            is also why the endpoint 404s there. */}
        {counts.messier_captured > 0 ? (
          <Group gap="xs" mt="sm">
            <Button
              size="xs" variant="light" color="teal"
              leftSection={<IconDownload size={14} />}
              component="a" href={api.lifeListGridUrl()} download
            >
              Share my grid
            </Button>
            <Text size="xs" c="dimmed">
              All {counts.messier_total} squares as one picture — yours filled in,
              the rest still to shoot.
            </Text>
          </Group>
        ) : null}
      </Card>

      <WishlistSection />

      <SegmentedControl
        value={filter}
        onChange={(v) => setFilter(v as Filter)}
        data={[
          { label: "All", value: "all" },
          { label: "Captured", value: "captured" },
          { label: "Still to shoot", value: "todo" },
        ]}
        w="fit-content"
      />

      <Section
        title={`Messier · ${counts.messier_captured} of ${counts.messier_total}`}
        note="The classic list every beginner works through — 110 objects Charles Messier catalogued in the 1770s, all of them within reach of a Seestar."
        items={messier}
        filter={filter}
      />
      <Section
        title={`Also worth getting · ${counts.other_captured} of ${counts.other_total}`}
        note="Popular NGC and IC objects that aren't on Messier's list but are just as rewarding to shoot."
        items={other}
        filter={filter}
      />
    </Stack>
  );
}
