import { useMemo, useState } from "react";
import {
  Anchor, Badge, Card, Center, Group, Image, Loader, Progress, SegmentedControl,
  SimpleGrid, Stack, Text, Title, Tooltip,
} from "@mantine/core";
import { IconChecklist, IconCircleCheck } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type LifeListItem } from "../api/client";
import { QueryError } from "../components/QueryError";

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
          straight to its picture.
        </Text>
      </Card>

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
