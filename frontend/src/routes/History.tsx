import { useState } from "react";
import {
  ActionIcon, Alert, Badge, Button, Card, Center, Group, Image, Loader, SegmentedControl,
  SimpleGrid, Slider, Stack, Table, Text, TextInput, Title, Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconAdjustments, IconCheck, IconCopy, IconDeviceFloppy, IconDownload, IconGitCompare, IconInfoCircle, IconPencil, IconSparkles, IconTrash, IconX } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api, type StackRun } from "../api/client";
import { formatIntegration } from "../format";
import { HazyNightBadge } from "../components/HazyNightBadge";
import { CalibrationBadge } from "../components/CalibrationBadge";
import { NoiseReadout, NoiseDelta, CleanestBadge, cleanestRunId, hasNoise } from "../components/NoiseBadge";
import { ImageLightbox } from "../components/ImageLightbox";
import { Sparkline } from "../components/Sparkline";

export type RunSort = "newest" | "cleanest";

// Order runs for display. "newest" preserves the API's timestamp-DESC order;
// "cleanest" puts the lowest-noise runs first, with runs that carry no measured
// σ (pre-v0.48 or not computable) kept after, in their original order. Pure and
// non-mutating so it's easy to test.
export function sortRuns(runs: StackRun[], sort: RunSort): StackRun[] {
  if (sort !== "cleanest") return runs;
  const measured = runs.filter((r) => hasNoise(r.noise_sigma));
  const rest = runs.filter((r) => !hasNoise(r.noise_sigma));
  measured.sort((a, b) => (a.noise_sigma as number) - (b.noise_sigma as number));
  return [...measured, ...rest];
}

// Map each run id → the fractional change in its background-noise σ against the
// same target's chronologically *previous* measured stack (the most recent older
// run that carries a σ). Negative = cleaner than last time. `runs` is the API's
// timestamp-DESC order; we walk it oldest→newest so "previous" means "earlier in
// time", independent of the display sort. Runs with no earlier measured σ (the
// first measured stack, or pre-v0.48 runs) get no entry. Pure/non-mutating.
export function noiseDeltas(runs: StackRun[]): Map<number, number> {
  const deltas = new Map<number, number>();
  let prev: number | null = null;
  for (let i = runs.length - 1; i >= 0; i--) {
    const r = runs[i];
    if (!hasNoise(r.noise_sigma)) continue;
    const sigma = r.noise_sigma as number;
    if (prev !== null && prev > 0) deltas.set(r.id, (sigma - prev) / prev);
    prev = sigma;
  }
  return deltas;
}

// Given the API's timestamp-DESC run list, return the id of the run that
// immediately *precedes* `id` in time (the next-older stack of this target) —
// the most common thing a user wants to compare against ("did adding subs /
// changing κ actually help vs my last run?"). The previous run is the next
// index in a newest-first list. Null when `id` is the oldest run or not found.
// Pure/non-mutating so it's easy to test.
export function previousRunId(runs: StackRun[], id: number): number | null {
  const idx = runs.findIndex((r) => r.id === id);
  if (idx < 0 || idx + 1 >= runs.length) return null;
  return runs[idx + 1].id;
}

// Build the bookmarkable /compare URL for two runs of the *same* target. The
// Compare view resolves each "<safe>:<run_id>" ref against the gallery (which
// carries every run), so a same-target link works with no backend change.
export function historyCompareHref(safe: string, aId: number, bId: number): string {
  return `/compare?a=${safe}:${aId}&b=${safe}:${bId}`;
}

// Extract this target's background-noise σ across runs in chronological order
// (oldest→newest), keeping only runs that carry a measured σ. `runs` is the
// API's timestamp-DESC order, so we reverse it. Drives the trend sparkline —
// lets a user see whether their stacks are getting cleaner as they add nights,
// not just the last hop. Pure/non-mutating.
export function noiseTrendSeries(runs: StackRun[]): number[] {
  const out: number[] = [];
  for (let i = runs.length - 1; i >= 0; i--) {
    if (hasNoise(runs[i].noise_sigma)) out.push(runs[i].noise_sigma as number);
  }
  return out;
}

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
      {data.weighting ? (
        <Text size="xs" c="dimmed">
          Quality-weighted
          {typeof data.weighting.n_downweighted === "number"
            ? ` · ${data.weighting.n_downweighted} frame${data.weighting.n_downweighted === 1 ? "" : "s"} down-weighted`
            : ""}
          {typeof data.weighting.min === "number" && typeof data.weighting.max === "number"
            ? ` · weights ${data.weighting.min.toFixed(2)}–${data.weighting.max.toFixed(2)}`
            : ""}
          {typeof data.weighting.median === "number"
            ? ` (median ${data.weighting.median.toFixed(2)})`
            : ""}
        </Text>
      ) : null}
      {data.processing && data.processing.length > 0 ? (
        <Text size="xs" c="dimmed">
          Processing: {data.processing.map((s) => s.label).join(" → ")}
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

// Inline, editable free-text label for a run ("best RGB v2", "cloudy night").
// Persisted via PATCH; reuses the long-standing notes column.
function NotesEditor({ safe, run }: { safe: string; run: StackRun }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(run.notes ?? "");

  const save = useMutation({
    mutationFn: (notes: string) => api.updateStackRunNotes(safe, run.id, notes),
    onSuccess: () => {
      setEditing(false);
      qc.invalidateQueries({ queryKey: ["runs", safe] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  if (editing) {
    return (
      <Group gap={4} mt={4} wrap="nowrap">
        <TextInput
          size="xs" style={{ flex: 1 }} value={draft} maxLength={500} autoFocus
          placeholder="Label this stack (e.g. best RGB v2)"
          aria-label="Stack note"
          onChange={(e) => setDraft(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") save.mutate(draft);
            if (e.key === "Escape") { setDraft(run.notes ?? ""); setEditing(false); }
          }}
        />
        <ActionIcon size="sm" color="teal" variant="light" aria-label="Save note"
          loading={save.isPending} onClick={() => save.mutate(draft)}>
          <IconCheck size={14} />
        </ActionIcon>
        <ActionIcon size="sm" variant="subtle" aria-label="Cancel note"
          onClick={() => { setDraft(run.notes ?? ""); setEditing(false); }}>
          <IconX size={14} />
        </ActionIcon>
      </Group>
    );
  }
  return (
    <Group gap={4} mt={4} wrap="nowrap">
      {run.notes ? (
        <Text size="xs" c="dimmed" style={{ flex: 1 }} truncate>“{run.notes}”</Text>
      ) : (
        <Text size="xs" c="dimmed" fs="italic" style={{ flex: 1 }}>No label</Text>
      )}
      <Tooltip label={run.notes ? "Edit label" : "Add a label"}>
        <ActionIcon size="sm" variant="subtle" aria-label="Edit note"
          onClick={() => { setDraft(run.notes ?? ""); setEditing(true); }}>
          <IconPencil size={14} />
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}

// Asinh stretch controls, both 0..1 (see seestack asinh_stretch). "Stretch"
// lifts faint nebulosity; "Black point" cleans the sky background. Users push
// Stretch up to reveal detail the baked 8-bit preview clipped.
const DEFAULT_STRETCH = 0.5;
const DEFAULT_BLACK = 0.35;

function RunCard({ safe, run, onDelete, deleting, isCleanest, noiseDelta, compareToId }: {
  safe: string; run: StackRun; onDelete: () => void; deleting?: boolean;
  isCleanest?: boolean; noiseDelta?: number; compareToId?: number | null;
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

      <Group justify="space-between" mt="sm" wrap="nowrap">
        <Text fw={600}>{run.output_basename}</Text>
        <Group gap={4} wrap="nowrap">
          <CleanestBadge isCleanest={!!isCleanest} />
          <HazyNightBadge ratio={run.transparency_ratio} />
          <CalibrationBadge calstat={run.calstat} />
          <Badge variant="light">{run.n_frames_used} frames</Badge>
        </Group>
      </Group>
      <Text size="xs" c="dimmed">
        {run.timestamp_utc.replace("T", " ").slice(0, 19)} · {run.canvas_w}×{run.canvas_h}
        {run.total_exposure_s ? ` · ${formatIntegration(run.total_exposure_s)}` : ""}
        {hasNoise(run.noise_sigma) ? <> · <NoiseReadout sigma={run.noise_sigma} /></> : null}
      </Text>
      {typeof noiseDelta === "number" ? (
        <Text size="xs"><NoiseDelta delta={noiseDelta} /></Text>
      ) : null}
      <NotesEditor safe={safe} run={run} />

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
          {typeof compareToId === "number" && (
            <Tooltip label="Compare this stack side-by-side with your previous run of this target">
              <Button
                size="xs" variant="light" color="grape" leftSection={<IconGitCompare size={14} />}
                component={Link} to={historyCompareHref(safe, run.id, compareToId)}
              >
                Compare
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
  const [sort, setSort] = useState<RunSort>("newest");
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
  const cleanestId = cleanestRunId(list);
  const anyNoise = list.some((r) => hasNoise(r.noise_sigma));
  const deltas = noiseDeltas(list);
  const sorted = sortRuns(list, sort);
  const trend = noiseTrendSeries(list);

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Stack history — {safe}</Title>
        <Group gap="sm">
          {list.length > 1 && anyNoise ? (
            <SegmentedControl
              size="xs"
              value={sort}
              onChange={(v) => setSort(v as RunSort)}
              data={[
                { label: "Newest", value: "newest" },
                { label: "Cleanest", value: "cleanest" },
              ]}
              aria-label="Sort stacks"
            />
          ) : null}
          <Button component={Link} to={`/targets/${safe}/stack`}>New stack</Button>
        </Group>
      </Group>
      {trend.length >= 2 ? (
        <Card withBorder padding="sm" radius="md">
          <Group justify="space-between" wrap="nowrap" gap="md">
            <div>
              <Group gap={6}>
                <Text size="sm" fw={600}>Noise trend</Text>
                <Tooltip
                  label="Background-noise σ of each measured stack, oldest → newest. Lower is cleaner; a downward line means your results are improving as you add nights."
                  multiline w={260} withArrow>
                  <Text span size="xs" c="dimmed" style={{ cursor: "help" }}
                    td="underline dotted">what's this?</Text>
                </Tooltip>
              </Group>
              <Text size="xs" c="dimmed">
                {trend[trend.length - 1] < trend[0]
                  ? `Cleaner than your first measured stack (σ ${trend[trend.length - 1].toFixed(3)} vs ${trend[0].toFixed(3)}).`
                  : trend[trend.length - 1] > trend[0]
                    ? `Noisier than your first measured stack (σ ${trend[trend.length - 1].toFixed(3)} vs ${trend[0].toFixed(3)}).`
                    : `Steady around σ ${trend[0].toFixed(3)}.`}
              </Text>
            </div>
            <Sparkline
              values={trend}
              color={trend[trend.length - 1] <= trend[0]
                ? "var(--mantine-color-teal-5)" : "var(--mantine-color-orange-5)"}
              aria-label={`Noise trend across ${trend.length} measured stacks`}
            />
          </Group>
        </Card>
      ) : null}
      {list.length === 0 ? (
        <Card withBorder padding="xl">
          <Stack align="center" gap="sm">
            <Text c="dimmed">No stacks yet for this target.</Text>
            <Button component={Link} to={`/targets/${safe}/stack`}>Stack it now</Button>
          </Stack>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
          {sorted.map((r) => (
            <RunCard key={r.id} safe={safe} run={r}
              onDelete={() => del.mutate(r.id)}
              deleting={del.isPending && del.variables === r.id}
              isCleanest={r.id === cleanestId}
              noiseDelta={deltas.get(r.id)}
              compareToId={previousRunId(list, r.id)} />
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
