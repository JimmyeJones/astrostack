import {
  Anchor, Badge, Card, Group, Image, Select, SimpleGrid, Stack, Text, TextInput,
  Title, Loader, Center, Chip,
} from "@mantine/core";
import { IconChevronRight, IconSearch, IconStars } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Target, type ThinPictureItem } from "../api/client";
import { CleanupSuggestionsCard } from "../components/CleanupSuggestionsCard";
import { SkippedFoldersCard } from "../components/SkippedFoldersCard";
import { FirstImageCard } from "../components/dashboard/FirstImageCard";
import { MergeSuggestionsCard } from "../components/MergeSuggestionsCard";
import { QueryError } from "../components/QueryError";
import { UploadFits } from "../components/UploadFits";
import { formatIntegration } from "../format";
import {
  THIN_PICTURE_LABEL, thinStackWarning,
} from "../components/target/thinStack";
import { UNSTRETCHED_HINT, UNSTRETCHED_LABEL, unstretchedHint } from "../unstretched";

// Target-card exposure. Delegates to the app-wide `formatIntegration` so the
// Library card speaks the same integration-time vocabulary as every other
// surface (Dashboard / Target / History / readiness) — a beginner shouldn't see
// "1h 30m" on a card and "1.5 h" for the same target elsewhere, and the shared
// helper also shows sub-minute totals honestly ("20 s" rather than "0m").
export function expo(seconds: number): string {
  return formatIntegration(seconds);
}

type SortKey = "name" | "recent" | "exposure" | "frames";

// Persist the Library view (search text, sort, active tags) so a user with a big
// library keeps their filters when they open a target and come back, or reload.
// localStorage-only and defensively guarded so a disabled/broken store never
// breaks the page.
const LS_KEY = "astrostack.library.filters";
type SavedFilters = { search: string; sort: SortKey; tags: string[] };

function loadFilters(): SavedFilters {
  const fallback: SavedFilters = { search: "", sort: "recent", tags: [] };
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return fallback;
    const p = JSON.parse(raw) as Partial<SavedFilters>;
    return {
      search: typeof p.search === "string" ? p.search : "",
      sort: (["name", "recent", "exposure", "frames"] as const).includes(p.sort as SortKey)
        ? (p.sort as SortKey) : "recent",
      tags: Array.isArray(p.tags) ? p.tags.filter((t): t is string => typeof t === "string") : [],
    };
  } catch {
    return fallback;
  }
}

function saveFilters(f: SavedFilters): void {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(f));
  } catch {
    /* storage unavailable — filters just won't persist */
  }
}

const SORTS: { value: SortKey; label: string }[] = [
  { value: "recent", label: "Recently active" },
  { value: "name", label: "Name (A–Z)" },
  { value: "exposure", label: "Most integration" },
  { value: "frames", label: "Most frames" },
];

function sortTargets(targets: Target[], key: SortKey): Target[] {
  const sorted = [...targets];
  switch (key) {
    case "name":
      return sorted.sort((a, b) => a.name.localeCompare(b.name));
    case "exposure":
      return sorted.sort((a, b) => b.total_exposure_s - a.total_exposure_s);
    case "frames":
      return sorted.sort((a, b) => b.n_frames - a.n_frames);
    case "recent":
    default:
      return sorted.sort((a, b) =>
        (b.last_activity_utc ?? "").localeCompare(a.last_activity_utc ?? ""));
  }
}

// The chip's copy moved to `../unstretched` when the Gallery gained the same
// chip (v0.448.2) — one place, so the two walls cannot drift into saying
// different things about the same picture. Re-exported here because that is where
// it was first published and where this route's own tests import it from.
export { UNSTRETCHED_HINT };

function TargetCard(
  { t, unstretched, unexportedEdit, thin }:
  { t: Target; unstretched?: boolean; unexportedEdit?: boolean;
    thin?: ThinPictureItem },
) {
  // The wall's one chip slot, and why depth wins it when a card is both.
  //
  // A card that is thin *and* unstretched gets the depth sentence, because the
  // stretch chip's advice is "press Auto" and Auto cannot make a one-sub stack
  // anything but a stretched one-sub stack — stretching noise only makes it
  // easier to see. The upstream problem is the one worth naming, and the card
  // links to the target where both are explained. One chip rather than two for
  // the reason the "Finished" chip was never added: the owner's standing
  // complaint about this app is clutter (AGENTS.md §1).
  //
  // `thinStackWarning` is the Gallery badge's own function, asked the same
  // question with the same two numbers, so the two walls cannot say different
  // things about one picture. `"open-it"` because a wall card carries no
  // "rejected" count for the sentence to point at.
  const thinWarn = thin
    ? thinStackWarning(thin.n_frames_used, thin.field_fulls, "open-it")
    : null;
  return (
    <Card shadow="sm" padding="lg" radius="md" withBorder component={Link} to={`/targets/${t.safe_name}`}>
      <Card.Section>
        {t.has_preview ? (
          <Image src={api.targetThumbnailUrl(t.safe_name)} h={160} alt={t.name} fallbackSrc="" />
        ) : (
          <Center h={160} bg="dark.6">
            <IconStars size={48} color="var(--mantine-color-dark-3)" />
          </Center>
        )}
      </Card.Section>
      {/* `justify="space-between"` wraps by default, so a name long enough to
          fill the card pushed the chevron onto a line of its own — a stray "›"
          hanging under the title. Same shape as the Gallery card's name row:
          the row may not wrap, the icon may not shrink, and the name truncates
          with its full text on hover so nothing is silently cut. */}
      <Group justify="space-between" mt="md" wrap="nowrap">
        <Text fw={600} truncate title={t.name}>{t.name}</Text>
        <IconChevronRight size={16} style={{ flexShrink: 0 }} />
      </Group>
      <Group gap="xs" mt="xs">
        <Badge variant="light" color="violet">
          {t.n_frames_accepted}/{t.n_frames} frames
        </Badge>
        <Badge variant="light" color="gray">
          {expo(t.total_exposure_s)}
        </Badge>
        {/* Only the cards that need something. A "Finished" chip on the other
            nine in ten would be a wall of badges saying nothing — and the
            owner's standing complaint about this app is clutter. */}
        {thinWarn ? (
          <Badge variant="light"
            color={thinWarn.level === "single" ? "orange" : "yellow"}
            title={thinWarn.message}>
            {THIN_PICTURE_LABEL}
          </Badge>
        ) : unstretched ? (
          <Badge variant="light" color="yellow"
            title={unstretchedHint(unexportedEdit)}>
            {UNSTRETCHED_LABEL}
          </Badge>
        ) : null}
      </Group>
      {t.tags.length ? (
        <Group gap={4} mt="xs">
          {t.tags.map((tag) => (
            <Badge key={tag} size="sm" variant="dot" color="grape">{tag}</Badge>
          ))}
        </Group>
      ) : null}
    </Card>
  );
}

export function Library() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["targets"], queryFn: api.listTargets,
  });
  const [initial] = useState(loadFilters);
  const [search, setSearch] = useState(initial.search);
  const [sort, setSort] = useState<SortKey>(initial.sort);
  const [activeTags, setActiveTags] = useState<string[]>(initial.tags);

  // Persist the view whenever any part of it changes.
  useEffect(() => {
    saveFilters({ search, sort, tags: activeTags });
  }, [search, sort, activeTags]);

  const targets = useMemo(() => data ?? [], [data]);

  // Which of these are showing a flat linear stack rather than a finished
  // picture. Its own endpoint on purpose: answering it needs each target's
  // project DB, and `/api/targets` is the light list this wall renders from —
  // the same reason the over-trim and new-subs notes have their own. Long
  // staleTime: it is a cross-target read about recipes already on disk.
  // Absent/failed ⇒ no chips, which is exactly the wall as it was.
  const unstretched = useQuery({
    queryKey: ["unstretched-pictures"],
    queryFn: api.getUnstretchedPictures,
    staleTime: 300_000,
  });
  // `safe -> unexported_edit` rather than a bare set: the chip renders on
  // membership, and the hint it carries depends on *which* kind of unstretched
  // this card is. One map, so the two cannot be read from different snapshots.
  const unstretchedSafe = useMemo(
    () => new Map((unstretched.data?.items ?? [])
      .map((i) => [i.safe, i.unexported_edit === true] as const)),
    [unstretched.data],
  );
  // …and which are showing a picture only a few subs deep on any one patch of
  // sky. The same response, because it is the same scan of the same library —
  // and the same "absent ⇒ no chips" rule, so an older backend leaves the wall
  // exactly as it was.
  const thinSafe = useMemo(
    () => new Map((unstretched.data?.thin ?? [])
      .map((i) => [i.safe, i] as const)),
    [unstretched.data],
  );

  const allTags = useMemo(() => {
    const set = new Set<string>();
    targets.forEach((t) => t.tags.forEach((tag) => set.add(tag)));
    return Array.from(set).sort();
  }, [targets]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = targets.filter((t) => {
      const matchesSearch = !q || t.name.toLowerCase().includes(q)
        || t.tags.some((tag) => tag.toLowerCase().includes(q))
        || (t.notes?.toLowerCase().includes(q) ?? false);
      const matchesTags = activeTags.length === 0
        || activeTags.every((tag) => t.tags.includes(tag));
      return matchesSearch && matchesTags;
    });
    return sortTargets(filtered, sort);
  }, [targets, search, sort, activeTags]);

  if (isError && !data) {
    return <QueryError error={error} onRetry={() => refetch()} />;
  }
  if (isLoading) {
    return <Center h={300}><Loader /></Center>;
  }

  return (
    <Stack>
      <Group justify="space-between" align="flex-end" wrap="wrap">
        <Title order={2}>Library</Title>
        {targets.length > 0 ? (
          <Group gap="xs">
            <TextInput
              leftSection={<IconSearch size={16} />}
              placeholder="Search name, tag or note…"
              value={search}
              onChange={(e) => setSearch(e.currentTarget.value)}
              w={{ base: "100%", xs: 220 }}
            />
            <Select data={SORTS} value={sort} onChange={(v) => setSort((v as SortKey) ?? "recent")}
              allowDeselect={false} w={170} aria-label="Sort targets" />
          </Group>
        ) : null}
      </Group>

      {allTags.length ? (
        <Chip.Group multiple value={activeTags} onChange={setActiveTags}>
          <Group gap="xs">
            {allTags.map((tag) => (
              <Chip key={tag} value={tag} size="xs" color="grape">{tag}</Chip>
            ))}
          </Group>
        </Chip.Group>
      ) : null}

      {targets.length > 0 ? (
        <Card withBorder padding="sm">
          <UploadFits compact />
        </Card>
      ) : null}

      {/* Not gated on having targets, unlike the two below it: this one says
          "frames of yours may be missing", which is at its most important on a
          library that came out thinner than the owner expected. It renders
          nothing unless a scan actually walked past something unexplained. */}
      <SkippedFoldersCard />
      {targets.length > 0 ? <CleanupSuggestionsCard /> : null}
      {targets.length > 0 ? <MergeSuggestionsCard /> : null}

      {targets.length === 0 ? (
        <Stack>
          {/* The getting-started map lives on the Dashboard, but Library is just
              as likely a first landing (it's where the subs go), and an empty
              list is exactly where the "what do I do now?" question lands. The
              card self-hides on an established install and once dismissed, so
              repeating it here can't nag anyone. */}
          <FirstImageCard />
          <Card withBorder padding="xl">
            <Stack align="center" gap="sm">
              <IconStars size={48} color="var(--mantine-color-dark-3)" />
              <Text c="dimmed">No targets yet.</Text>
              <Text c="dimmed" size="sm" ta="center">
                Upload your Seestar FITS files below, or drop target folders into the watched
                dataset over your NAS share.
              </Text>
              {/* Someone whose first night was a lunar video has *something* —
                  it just isn't a target, because a video has no subs to ingest.
                  Without this line the Library is the one screen that still
                  reads as "you have nothing at all". Always shown: it costs a
                  sentence and it is true either way. */}
              <Text c="dimmed" size="sm" ta="center">
                Shot a video of the Moon or the Sun instead? That lives on the{" "}
                <Anchor component={Link} to="/moon-sun">Moon &amp; Sun</Anchor> page.
              </Text>
            </Stack>
          </Card>
          <UploadFits />
        </Stack>
      ) : visible.length === 0 ? (
        <Text c="dimmed" mt="md">No targets match your filters.</Text>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3, lg: 4 }}>
          {visible.map((t) => (
            <TargetCard key={t.safe_name} t={t}
              unstretched={unstretchedSafe.has(t.safe_name)}
              unexportedEdit={unstretchedSafe.get(t.safe_name)}
              thin={thinSafe.get(t.safe_name)} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
