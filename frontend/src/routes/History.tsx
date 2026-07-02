import { useState } from "react";
import {
  ActionIcon, Alert, Badge, Button, Card, Center, Group, Image, Loader, SimpleGrid,
  Slider, Stack, Table, Text, Title, Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconAdjustments, IconCopy, IconDeviceFloppy, IconDownload, IconInfoCircle, IconSparkles, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, type StackRun } from "../api/client";
import { formatIntegration } from "../format";
import { ImageLightbox } from "../components/ImageLightbox";

function StackInfoPanel({ safe, runId }: { safe: string; runId: number }) {
  const info = useQuery({
    queryKey: ["stack-info", safe, runId],
    queryFn: () => api.stackRunInfo(safe, runId),
  });
  if (info.isLoading) return <Center h={60}><Loader size="sm" /></Center>;
  if (info.isError) {
    return <Text size="xs" c="dimmed">Could not read FITS header.</Text>;
  }
  const data = info.data!;
  if (data.cards.length === 0) {
    return <Text size="xs" c="dimmed">No provenance recorded in this stack's FITS.</Text>;
  }
  return (
    <Stack gap={4} mt="xs">
      {data.integration_s ? (
        <Text size="xs" fw={600}>
          Integration: {formatIntegration(data.integration_s)}
          {data.n_frames ? ` · ${data.n_frames} subs` : ""}
        </Text>
      ) : null}
      <Table verticalSpacing={2} horizontalSpacing="xs" fz="xs" withRowBorders={false}>
        <Table.Tbody>
          {data.cards.map((c) => (
            <Table.Tr key={c.key}>
              <Table.Td c="dimmed" style={{ whiteSpace: "nowrap" }}>{c.key}</Table.Td>
              <Table.Td>{String(c.value)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}

// Asinh stretch controls, both 0..1 (see seestack asinh_stretch). "Stretch"
// lifts faint nebulosity; "Black point" cleans the sky background. Users push
// Stretch up to reveal detail the baked 8-bit preview clipped.
const DEFAULT_STRETCH = 0.5;
const DEFAULT_BLACK = 0.35;

function RunCard({ safe, run, onDelete, deleting }: {
  safe: string; run: StackRun; onDelete: () => void; deleting?: boolean;
}) {
  const qc = useQueryClient();
  const [adjust, setAdjust] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
  const [stretch, setStretch] = useState(DEFAULT_STRETCH);
  const [black, setBlack] = useState(DEFAULT_BLACK);
  const [cacheBust, setCacheBust] = useState(0);
  const [light, setLight] = useState(false);
  const [dStretch] = useDebouncedValue(stretch, 250);
  const [dBlack] = useDebouncedValue(black, 250);

  const save = useMutation({
    mutationFn: () => api.saveStackPreview(safe, run.id, dStretch, dBlack),
    onSuccess: () => {
      setCacheBust(Date.now());
      qc.invalidateQueries({ queryKey: ["sky"] });
      qc.invalidateQueries({ queryKey: ["gallery"] });
      notifications.show({ message: "Preview updated", color: "teal" });
    },
    onError: () => notifications.show({ message: "Could not save preview", color: "red" }),
  });

  const previewSrc = `${api.stackArtifactUrl(safe, run.id, "preview")}${cacheBust ? `?v=${cacheBust}` : ""}`;
  const imgSrc = adjust && run.has_fits
    ? api.stackRenderUrl(safe, run.id, dStretch, dBlack)
    : previewSrc;

  return (
    <Card withBorder padding="md" radius="md">
      <Card.Section>
        {run.has_preview || (adjust && run.has_fits) ? (
          <Image
            src={imgSrc} h={180} fit="contain" bg="#000"
            style={{ cursor: "zoom-in" }} onClick={() => setLight(true)}
          />
        ) : (
          <Center h={180} bg="dark.6"><Text c="dimmed">No preview</Text></Center>
        )}
      </Card.Section>

      <Group justify="space-between" mt="sm">
        <Text fw={600}>{run.output_basename}</Text>
        <Badge variant="light">{run.n_frames_used} frames</Badge>
      </Group>
      <Text size="xs" c="dimmed">
        {run.timestamp_utc.replace("T", " ").slice(0, 19)} · {run.canvas_w}×{run.canvas_h}
      </Text>

      {adjust && run.has_fits ? (
        <Stack gap={6} mt="sm">
          <div>
            <Group justify="space-between" gap={4}>
              <Text size="xs">Stretch (asinh)</Text>
              <Text size="xs" c="dimmed">{stretch.toFixed(2)}</Text>
            </Group>
            <Slider
              min={0} max={1} step={0.01} value={stretch} onChange={setStretch}
              label={(v) => v.toFixed(2)} size="sm"
            />
          </div>
          <div>
            <Group justify="space-between" gap={4}>
              <Text size="xs">Black point</Text>
              <Text size="xs" c="dimmed">{black.toFixed(2)}</Text>
            </Group>
            <Slider
              min={0} max={1} step={0.01} value={black} onChange={setBlack}
              label={(v) => v.toFixed(2)} size="sm"
            />
          </div>
          <Group gap="xs" mt={4}>
            <Button
              size="xs" leftSection={<IconDeviceFloppy size={14} />}
              loading={save.isPending} onClick={() => save.mutate()}
            >
              Save as preview
            </Button>
            <Button
              size="xs" variant="subtle"
              onClick={() => { setStretch(DEFAULT_STRETCH); setBlack(DEFAULT_BLACK); }}
            >
              Reset
            </Button>
          </Group>
        </Stack>
      ) : null}

      <Group mt="sm" justify="space-between">
        <Group gap="xs">
          {run.has_fits && (
            <Button
              size="xs" variant="light" color="grape" leftSection={<IconSparkles size={14} />}
              component={Link} to={`/targets/${safe}/edit/${run.id}`}
            >
              Edit
            </Button>
          )}
          {run.reusable && (
            <Tooltip label="Pre-fill the Stack form with the exact settings used for this run">
              <Button
                size="xs" variant="light" leftSection={<IconCopy size={14} />}
                component={Link} to={`/targets/${safe}/stack?from=${run.id}`}
              >
                Reuse settings
              </Button>
            </Tooltip>
          )}
          {run.has_fits && (
            <Tooltip label="Adjust stretch / black point from the full-range FITS">
              <Button
                size="xs" variant={adjust ? "filled" : "light"}
                leftSection={<IconAdjustments size={14} />}
                onClick={() => setAdjust((a) => !a)}
              >
                Adjust
              </Button>
            </Tooltip>
          )}
          {run.has_fits && (
            <Tooltip label="Show how this stack was made (from the FITS header)">
              <Button
                size="xs" variant={showInfo ? "filled" : "light"}
                leftSection={<IconInfoCircle size={14} />}
                onClick={() => setShowInfo((s) => !s)}
              >
                Info
              </Button>
            </Tooltip>
          )}
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
        <Tooltip label="Delete this stack run">
          <ActionIcon variant="subtle" color="red" loading={deleting} aria-label="Delete stack"
            onClick={() => {
              if (window.confirm(
                `Delete "${run.output_basename}" permanently? Its FITS/TIFF/preview will be removed.`)) {
                onDelete();
              }
            }}>
            <IconTrash size={16} />
          </ActionIcon>
        </Tooltip>
      </Group>

      {showInfo && run.has_fits ? <StackInfoPanel safe={safe} runId={run.id} /> : null}

      <ImageLightbox
        src={light
          ? (adjust && run.has_fits
              ? `${api.stackRenderUrl(safe, run.id, dStretch, dBlack)}&size=2048`
              : previewSrc)
          : null}
        title={run.output_basename}
        downloadHref={run.has_fits ? api.stackArtifactUrl(safe, run.id, "fits") : undefined}
        onClose={() => setLight(false)}
      />
    </Card>
  );
}

export function HistoryView() {
  const { safe = "" } = useParams();
  const qc = useQueryClient();
  const runs = useQuery({ queryKey: ["runs", safe], queryFn: () => api.listStackRuns(safe) });

  const del = useMutation({
    mutationFn: (id: number) => api.deleteStackRun(safe, id),
    onSuccess: () => {
      notifications.show({ message: "Stack deleted", color: "teal" });
      // A deleted run also vanishes from the Gallery, Sky map and Dashboard.
      qc.invalidateQueries({ queryKey: ["runs", safe] });
      qc.invalidateQueries({ queryKey: ["gallery"] });
      qc.invalidateQueries({ queryKey: ["sky"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  if (runs.isLoading) {
    return <Center h={300}><Loader /></Center>;
  }
  if (runs.isError) {
    return <Alert color="red" m="md" title="Could not load stacks">{(runs.error as Error)?.message}</Alert>;
  }

  const list = runs.data ?? [];

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Stack history — {safe}</Title>
        <Button component={Link} to={`/targets/${safe}/stack`}>New stack</Button>
      </Group>
      {list.length === 0 ? (
        <Card withBorder padding="xl">
          <Stack align="center" gap="sm">
            <Text c="dimmed">No stacks yet for this target.</Text>
            <Button component={Link} to={`/targets/${safe}/stack`}>Stack it now</Button>
          </Stack>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
          {list.map((r) => (
            <RunCard key={r.id} safe={safe} run={r}
              onDelete={() => del.mutate(r.id)}
              deleting={del.isPending && del.variables === r.id} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
