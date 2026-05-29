import {
  Badge, Button, Card, Group, Image, SimpleGrid, Stack, Text, Title, Loader, Center,
} from "@mantine/core";
import { IconChevronRight, IconStars } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Target } from "../api/client";

function expo(seconds: number): string {
  if (!seconds) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
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
    </Card>
  );
}

export function Library() {
  const { data, isLoading } = useQuery({ queryKey: ["targets"], queryFn: api.listTargets });

  if (isLoading) {
    return (
      <Center h={300}>
        <Loader />
      </Center>
    );
  }

  const targets = data ?? [];

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Library</Title>
      </Group>
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
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3, lg: 4 }}>
          {targets.map((t) => (
            <TargetCard key={t.safe_name} t={t} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
