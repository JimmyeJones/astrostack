import {
  ActionIcon, Badge, Button, Card, Center, Group, Image, Loader, SimpleGrid, Stack, Text, Title,
} from "@mantine/core";
import { IconDownload, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, type StackRun } from "../api/client";

function RunCard({ safe, run, onDelete }: { safe: string; run: StackRun; onDelete: () => void }) {
  return (
    <Card withBorder padding="md" radius="md">
      <Card.Section>
        {run.has_preview ? (
          <Image src={api.stackArtifactUrl(safe, run.id, "preview")} h={180} fit="contain" bg="#000" />
        ) : (
          <Center h={180} bg="dark.6">
            <Text c="dimmed">No preview</Text>
          </Center>
        )}
      </Card.Section>
      <Group justify="space-between" mt="sm">
        <Text fw={600}>{run.output_basename}</Text>
        <Badge variant="light">{run.n_frames_used} frames</Badge>
      </Group>
      <Text size="xs" c="dimmed">
        {run.timestamp_utc.replace("T", " ").slice(0, 19)} · {run.canvas_w}×{run.canvas_h}
      </Text>
      <Group mt="sm" justify="space-between">
        <Group gap="xs">
          {run.has_fits && (
            <Button
              size="xs" variant="light" leftSection={<IconDownload size={14} />}
              component="a" href={api.stackArtifactUrl(safe, run.id, "fits")}
            >
              FITS
            </Button>
          )}
          {run.has_tiff && (
            <Button
              size="xs" variant="light" leftSection={<IconDownload size={14} />}
              component="a" href={api.stackArtifactUrl(safe, run.id, "tiff")}
            >
              TIFF
            </Button>
          )}
        </Group>
        <ActionIcon variant="subtle" color="red" onClick={onDelete}>
          <IconTrash size={16} />
        </ActionIcon>
      </Group>
    </Card>
  );
}

export function HistoryView() {
  const { safe = "" } = useParams();
  const qc = useQueryClient();
  const runs = useQuery({ queryKey: ["runs", safe], queryFn: () => api.listStackRuns(safe) });

  const del = useMutation({
    mutationFn: (id: number) => api.deleteStackRun(safe, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs", safe] }),
  });

  if (runs.isLoading) {
    return (
      <Center h={300}>
        <Loader />
      </Center>
    );
  }

  const list = runs.data ?? [];

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Stack history — {safe}</Title>
        <Button component={Link} to={`/targets/${safe}/stack`}>New stack</Button>
      </Group>
      {list.length === 0 ? (
        <Text c="dimmed">No stacks yet.</Text>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
          {list.map((r) => (
            <RunCard key={r.id} safe={safe} run={r} onDelete={() => del.mutate(r.id)} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
