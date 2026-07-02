import {
  Badge, Button, Card, Group, Image, Select, SimpleGrid, Stack, Text, TextInput,
  Title, Loader, Center, Chip,
} from "@mantine/core";
import { IconChevronRight, IconSearch, IconStars } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Target } from "../api/client";
import { QueryError } from "../components/QueryError";

function expo(seconds: number): string {
  if (!seconds) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}

type SortKey = "name" | "recent" | "exposure" | "frames";

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

function TargetCard({ t }: { t: Target }) {
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
      <Group justify="space-between" mt="md">
        <Text fw={600}>{t.name}</Text>
        <IconChevronRight size={16} />
      </Group>
      <Group gap="xs" mt="xs">
        <Badge variant="light" color="violet">
          {t.n_frames_accepted}/{t.n_frames} frames
        </Badge>
        <Badge variant="light" color="gray">
          {expo(t.total_exposure_s)}
        </Badge>
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
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("recent");
  const [activeTags, setActiveTags] = useState<string[]>([]);

  const targets = useMemo(() => data ?? [], [data]);

  const allTags = useMemo(() => {
    const set = new Set<string>();
    targets.forEach((t) => t.tags.forEach((tag) => set.add(tag)));
    return Array.from(set).sort();
  }, [targets]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    const filtered = targets.filter((t) => {
      const matchesSearch = !q || t.name.toLowerCase().includes(q)
        || t.tags.some((tag) => tag.toLowerCase().includes(q));
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
              placeholder="Search name or tag…"
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

      {targets.length === 0 ? (
        <Card withBorder padding="xl">
          <Stack align="center" gap="sm">
            <IconStars size={48} color="var(--mantine-color-dark-3)" />
            <Text c="dimmed">No targets yet.</Text>
            <Text c="dimmed" size="sm">
              Drop your Seestar target folders into the watched dataset, or click “Scan incoming”.
            </Text>
            <Button component={Link} to="/jobs" variant="light">
              View jobs
            </Button>
          </Stack>
        </Card>
      ) : visible.length === 0 ? (
        <Text c="dimmed" mt="md">No targets match your filters.</Text>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3, lg: 4 }}>
          {visible.map((t) => (
            <TargetCard key={t.safe_name} t={t} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
