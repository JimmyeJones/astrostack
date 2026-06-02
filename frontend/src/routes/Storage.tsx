import {
  Badge, Button, Card, Center, Group, Loader, Menu, NumberInput, Progress,
  Stack, Text, Title,
} from "@mantine/core";
import { IconChevronDown, IconDatabase, IconTrash } from "@tabler/icons-react";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type TargetStorage } from "../api/client";

function gb(bytes: number): string {
  if (!bytes) return "0 MB";
  const mb = bytes / 1024 ** 2;
  return mb < 1024 ? `${mb.toFixed(0)} MB` : `${(mb / 1024).toFixed(2)} GB`;
}

function TargetRow({ row, total }: { row: TargetStorage; total: number }) {
  const qc = useQueryClient();
  const [keep, setKeep] = useState<number | string>(3);

  const clear = useMutation({
    mutationFn: (stage: "stage1" | "stage2" | "thumbs" | "all") => api.clearCache(row.safe, stage),
    onSuccess: (r) => {
      notifications.show({ message: `Cleared ${r.cleared.join(", ")} for ${row.name}`, color: "teal" });
      qc.invalidateQueries({ queryKey: ["storage"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const prune = useMutation({
    mutationFn: (k: number) => api.pruneStackRuns(row.safe, { keep: k }),
    onSuccess: (r) => {
      notifications.show({ message: `Deleted ${r.deleted.length} old stack(s)`, color: "teal" });
      qc.invalidateQueries({ queryKey: ["storage"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const pct = total ? (row.total_bytes / total) * 100 : 0;
  const cachePct = row.total_bytes ? (row.cache_bytes / row.total_bytes) * 100 : 0;

  const confirmClear = (stage: "stage1" | "stage2" | "thumbs" | "all", label: string) => {
    if (window.confirm(
      `Clear ${label} for ${row.name}?\n\nThis deletes regenerable cache files only — your `
      + `frames and stacked outputs are kept and the cache rebuilds on the next run.`)) {
      clear.mutate(stage);
    }
  };

  const confirmPrune = () => {
    if (window.confirm(
      `Keep the ${Number(keep)} newest stack(s) for ${row.name} and permanently delete the rest `
      + `(including their FITS/TIFF/preview files)?\n\nThis cannot be undone.`)) {
      prune.mutate(Number(keep));
    }
  };

  return (
    <Card withBorder padding="md" radius="md">
      <Group justify="space-between" wrap="nowrap">
        <div style={{ minWidth: 0 }}>
          <Text fw={600} lineClamp={1}>{row.name}</Text>
          <Text size="xs" c="dimmed">
            {gb(row.total_bytes)} total · cache {gb(row.cache_bytes)} · output {gb(row.output_bytes)}
            {" · "}{row.n_stack_runs} stack{row.n_stack_runs === 1 ? "" : "s"}
          </Text>
        </div>
        <Badge variant="light" color="gray">{pct.toFixed(0)}%</Badge>
      </Group>

      <Progress.Root size="lg" mt="sm">
        <Progress.Section value={cachePct} color="orange">
          <Progress.Label>cache</Progress.Label>
        </Progress.Section>
        <Progress.Section value={100 - cachePct} color="violet">
          <Progress.Label>data</Progress.Label>
        </Progress.Section>
      </Progress.Root>

      <Group mt="sm" gap="xs">
        <Menu shadow="md" position="bottom-start">
          <Menu.Target>
            <Button size="xs" variant="light" color="orange"
              leftSection={<IconTrash size={14} />} rightSection={<IconChevronDown size={14} />}
              loading={clear.isPending}>
              Clear cache
            </Button>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item onClick={() => confirmClear("all", "all caches")}>
              All caches ({gb(row.cache_bytes)})
            </Menu.Item>
            <Menu.Item onClick={() => confirmClear("stage1", "stage-1 raws")}>
              Stage-1 raws ({gb(row.stage1_bytes)})
            </Menu.Item>
            <Menu.Item onClick={() => confirmClear("stage2", "stage-2 aligned")}>
              Stage-2 aligned ({gb(row.stage2_bytes)})
            </Menu.Item>
            <Menu.Item onClick={() => confirmClear("thumbs", "thumbnails")}>
              Thumbnails ({gb(row.thumbs_bytes)})
            </Menu.Item>
          </Menu.Dropdown>
        </Menu>

        {row.n_stack_runs > 1 ? (
          <Group gap={6}>
            <Text size="xs" c="dimmed">keep</Text>
            <NumberInput size="xs" w={64} min={0} max={row.n_stack_runs}
              value={keep} onChange={setKeep} />
            <Button size="xs" variant="subtle" color="red" loading={prune.isPending}
              onClick={confirmPrune}>
              Prune stacks
            </Button>
          </Group>
        ) : null}
      </Group>
    </Card>
  );
}

export function StorageView() {
  const { data, isLoading } = useQuery({ queryKey: ["storage"], queryFn: api.getStorage });

  if (isLoading || !data) {
    return <Center h={300}><Loader /></Center>;
  }

  return (
    <Stack maw={900}>
      <Title order={2}>Storage</Title>
      <Group gap="lg">
        <Text size="sm">Library total: <b>{gb(data.total_bytes)}</b></Text>
        <Text size="sm">Cache: <b>{gb(data.cache_bytes)}</b></Text>
        <Text size="sm">Outputs: <b>{gb(data.output_bytes)}</b></Text>
        {data.disk.free_gb != null ? (
          <Text size="sm" c="dimmed">{data.disk.free_gb} GB free on disk</Text>
        ) : null}
      </Group>
      <Text size="sm" c="dimmed">
        Caches are intermediate files (downloaded raws, aligned frames, thumbnails) that are
        regenerated automatically — safe to clear to reclaim space. Pruning stacks permanently
        deletes old stacked outputs.
      </Text>

      {data.targets.length === 0 ? (
        <Card withBorder padding="xl">
          <Stack align="center" gap="sm">
            <IconDatabase size={40} color="var(--mantine-color-dark-3)" />
            <Text c="dimmed">No targets yet.</Text>
          </Stack>
        </Card>
      ) : (
        <Stack>
          {data.targets.map((row) => (
            <TargetRow key={row.safe} row={row} total={data.total_bytes} />
          ))}
        </Stack>
      )}
    </Stack>
  );
}
