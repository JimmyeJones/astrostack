import { useState } from "react";
import {
  ActionIcon, Badge, Button, Card, Center, Group, Image, Loader, SimpleGrid,
  Slider, Stack, Text, Title, Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconAdjustments, IconDeviceFloppy, IconDownload, IconSparkles, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, type StackRun } from "../api/client";
import { ImageLightbox } from "../components/ImageLightbox";

// Asinh stretch controls, both 0..1 (see seestack asinh_stretch). "Stretch"
// lifts faint nebulosity; "Black point" cleans the sky background. Users push
// Stretch up to reveal detail the baked 8-bit preview clipped.
const DEFAULT_STRETCH = 0.5;
const DEFAULT_BLACK = 0.35;

function RunCard({ safe, run, onDelete }: { safe: string; run: StackRun; onDelete: () => void }) {
  const qc = useQueryClient();
  const [adjust, setAdjust] = useState(false);
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
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs", safe] }),
  });

  if (runs.isLoading) {
    return <Center h={300}><Loader /></Center>;
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
