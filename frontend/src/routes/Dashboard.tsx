import {
  Alert, Badge, Card, Center, Group, Image, Loader, Paper, SimpleGrid, Stack, Text, Title,
} from "@mantine/core";
import {
  IconActivity, IconClock, IconLayoutGrid, IconPhoto, IconStack2, IconStars,
} from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";

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
          {sub ? <Text size="xs" c="dimmed">{sub}</Text> : null}
        </div>
      </Group>
    </Paper>
  );
}

export function Dashboard() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["stats"], queryFn: api.getStats, refetchInterval: 10_000,
  });

  if (isError) {
    return <Alert color="red" m="md" title="Could not load the dashboard">{(error as Error)?.message}</Alert>;
  }
  if (isLoading || !data) {
    return <Center h={300}><Loader /></Center>;
  }

  const accept = data.acceptance_rate == null ? "—" : `${Math.round(data.acceptance_rate * 100)}%`;
  const free = data.disk.free_gb != null ? `${data.disk.free_gb} GB` : "—";
  const usedSub = data.disk.total_gb != null ? `of ${data.disk.total_gb} GB` : undefined;

  return (
    <Stack>
      <Title order={2}>Dashboard</Title>

      <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }}>
        <StatCard icon={<IconStars size={22} color="var(--mantine-color-violet-4)" />}
          label="Targets" value={String(data.n_targets)}
          sub={`${data.n_targets_with_stacks} stacked`} />
        <StatCard icon={<IconClock size={22} color="var(--mantine-color-violet-4)" />}
          label="Integration" value={`${data.integration_hours.toFixed(1)}h`} />
        <StatCard icon={<IconPhoto size={22} color="var(--mantine-color-violet-4)" />}
          label="Frames" value={String(data.n_frames)}
          sub={`${data.n_frames_accepted} kept · ${accept}`} />
        <StatCard icon={<IconStack2 size={22} color="var(--mantine-color-violet-4)" />}
          label="Stacks" value={String(data.n_stack_runs)} />
        <StatCard icon={<IconActivity size={22} color="var(--mantine-color-violet-4)" />}
          label="Active jobs" value={String(data.active_jobs)} />
        <StatCard icon={<IconLayoutGrid size={22} color="var(--mantine-color-violet-4)" />}
          label="Free disk" value={free} sub={usedSub} />
      </SimpleGrid>

      <Group justify="space-between" mt="sm">
        <Title order={4}>Recent stacks</Title>
        <Text component={Link} to="/gallery" size="sm" c="violet">View gallery →</Text>
      </Group>

      {data.recent_stacks.length === 0 ? (
        <Card withBorder padding="xl">
          <Stack align="center" gap="sm">
            <IconStack2 size={40} color="var(--mantine-color-dark-3)" />
            <Text c="dimmed">No stacks yet. Stack a target to see it here.</Text>
            <Text component={Link} to="/library" size="sm" c="violet">Go to Library →</Text>
          </Stack>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, xs: 2, sm: 3, lg: 4 }}>
          {data.recent_stacks.map((s) => (
            <Card key={`${s.safe}-${s.run_id}`} withBorder padding="sm" radius="md"
              component={Link} to={`/targets/${s.safe}/history`}>
              <Card.Section>
                {s.has_preview ? (
                  <Image src={s.preview_url} h={140} alt={s.target_name} />
                ) : (
                  <Center h={140} bg="dark.6">
                    <IconStack2 size={36} color="var(--mantine-color-dark-3)" />
                  </Center>
                )}
              </Card.Section>
              <Text fw={600} mt="xs" lineClamp={1}>{s.target_name}</Text>
              <Group justify="space-between" mt={4}>
                <Badge variant="light" color="violet">{s.n_frames_used} frames</Badge>
                <Text size="xs" c="dimmed">{s.timestamp_utc.slice(0, 10)}</Text>
              </Group>
            </Card>
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
