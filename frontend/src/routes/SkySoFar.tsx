import {
  Card, Center, Group, Image, Loader, Paper, SimpleGrid, Stack, Text, Title,
} from "@mantine/core";
import {
  IconCalendarStar, IconClock, IconPhoto, IconStack2, IconStars, IconTrophy,
} from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type SummaryTarget } from "../api/client";
import { formatIntegration, formatMonthYear } from "../format";
import { QueryError } from "../components/QueryError";

function StatCard({ icon, label, value, sub }: {
  icon: React.ReactNode; label: string; value: string; sub?: string;
}) {
  return (
    <Paper withBorder p="md" radius="md">
      <Group gap="sm" wrap="nowrap">
        <Center w={40} h={40} bg="dark.6" style={{ borderRadius: 8, flexShrink: 0 }}>
          {icon}
        </Center>
        <div style={{ minWidth: 0 }}>
          <Text size="xs" c="dimmed">{label}</Text>
          <Text fw={700} size="lg" lh={1.2}>{value}</Text>
          {sub ? <Text size="xs" c="dimmed" truncate>{sub}</Text> : null}
        </div>
      </Group>
    </Paper>
  );
}

// A "your standout" card — the longest project / most-imaged target, with its
// finished picture if it has one. Links straight to the target so the reader can
// jump from "look what I made" into that target's page.
function StandoutCard({ icon, title, target, detail }: {
  icon: React.ReactNode;
  title: string;
  target: SummaryTarget;
  detail: string;
}) {
  return (
    <Card withBorder radius="md" padding="sm"
      component={Link} to={`/targets/${target.safe}`}>
      {target.thumbnail_url ? (
        <Card.Section>
          <Image src={target.thumbnail_url} h={120} alt={target.name} />
        </Card.Section>
      ) : null}
      <Group gap="xs" mt={target.thumbnail_url ? "sm" : 0} wrap="nowrap">
        <Center w={28} h={28} style={{ flexShrink: 0 }}>{icon}</Center>
        <div style={{ minWidth: 0 }}>
          <Text size="xs" c="dimmed">{title}</Text>
          <Text fw={600} truncate>{target.name}</Text>
          <Text size="xs" c="dimmed">{detail}</Text>
        </div>
      </Group>
    </Card>
  );
}

export function SkySoFarView() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["library-summary"], queryFn: api.getLibrarySummary,
    refetchInterval: 30_000,
  });

  if (isError && !data) {
    return <QueryError error={error} onRetry={() => refetch()} />;
  }
  if (isLoading || !data) {
    return <Center h={300}><Loader /></Center>;
  }

  const hasAnything = data.n_targets_imaged > 0;

  return (
    <Stack gap="md">
      <div>
        <Title order={2}>Your sky, so far</Title>
        <Text c="dimmed" size="sm">
          Everything you've captured, all in one place — look how it adds up.
        </Text>
      </div>

      {!hasAnything ? (
        <Card withBorder padding="xl">
          <Stack align="center" gap="sm">
            <IconStars size={40} color="var(--mantine-color-dark-3)" />
            <Text c="dimmed">
              Nothing here yet. Once you've captured and kept some frames, this page
              will show how your collection is growing.
            </Text>
            <Text component={Link} to="/library" size="sm" c="violet">Go to Library →</Text>
          </Stack>
        </Card>
      ) : (
        <>
          <SimpleGrid cols={{ base: 2, sm: 4 }}>
            <StatCard
              icon={<IconClock size={22} color="var(--mantine-color-violet-4)" />}
              label="Total integration"
              value={formatIntegration(data.total_integration_s)} />
            <StatCard
              icon={<IconStars size={22} color="var(--mantine-color-violet-4)" />}
              label="Targets imaged"
              value={String(data.n_targets_imaged)} />
            <StatCard
              icon={<IconPhoto size={22} color="var(--mantine-color-violet-4)" />}
              label="Subs kept"
              value={data.n_subs_kept.toLocaleString()} />
            <StatCard
              icon={<IconCalendarStar size={22} color="var(--mantine-color-violet-4)" />}
              label="First light"
              value={formatMonthYear(data.first_light_utc)} />
          </SimpleGrid>

          {(data.longest_target || data.most_imaged_target) ? (
            <SimpleGrid cols={{ base: 1, sm: 2 }}>
              {data.longest_target ? (
                <StandoutCard
                  icon={<IconTrophy size={20} color="var(--mantine-color-yellow-5)" />}
                  title="Your biggest project"
                  target={data.longest_target}
                  detail={`${formatIntegration(data.longest_target.total_exposure_s)} of integration`} />
              ) : null}
              {data.most_imaged_target ? (
                <StandoutCard
                  icon={<IconStack2 size={20} color="var(--mantine-color-teal-4)" />}
                  title="Most-imaged target"
                  target={data.most_imaged_target}
                  detail={`${data.most_imaged_target.n_frames_accepted.toLocaleString()} subs kept`} />
              ) : null}
            </SimpleGrid>
          ) : null}

          <div>
            <Title order={4} mb="xs">Your pictures</Title>
            {data.heroes.length === 0 ? (
              <Card withBorder padding="lg">
                <Text c="dimmed" size="sm">
                  No finished pictures yet. Stack a target and it'll appear here as
                  part of your collection.
                </Text>
              </Card>
            ) : (
              <SimpleGrid cols={{ base: 2, xs: 3, sm: 4, lg: 5 }}>
                {data.heroes.map((h) => (
                  <Card key={h.safe} withBorder padding={0} radius="md"
                    component={Link} to={`/targets/${h.safe}`}>
                    <Image src={h.thumbnail_url ?? undefined} h={130} alt={h.name} />
                    <Text size="xs" fw={500} p="xs" truncate>{h.name}</Text>
                  </Card>
                ))}
              </SimpleGrid>
            )}
          </div>
        </>
      )}
    </Stack>
  );
}
