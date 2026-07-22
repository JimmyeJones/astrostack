import { useMemo, useState } from "react";
import {
  Alert, Badge, Button, Card, Center, Checkbox, Group, Image, Loader, Menu, Paper,
  SegmentedControl, SimpleGrid, Spoiler, Stack, Text, TextInput, Title, Tooltip,
} from "@mantine/core";
import { IconCopy, IconGitCompare, IconPhoto, IconSearch, IconWand } from "@tabler/icons-react";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, type GalleryItem, type StackOptionField } from "../api/client";
import { sharePictureText } from "../share";
import { formatIntegration } from "../format";
import { HazyNightBadge } from "../components/HazyNightBadge";
import { CalibrationBadge } from "../components/CalibrationBadge";
import {
  RejectionBadge, combineMethodKey, COMBINE_METHOD_LABELS, type CombineMethod,
} from "../components/RejectionBadge";
import { NoiseReadout, hasNoise } from "../components/NoiseBadge";
import { ImageLightbox } from "../components/ImageLightbox";
import { WallpaperMenu } from "../components/WallpaperMenu";
import { QueryError } from "../components/QueryError";

export type GallerySort = "newest" | "cleanest";
export type CalFilter = "all" | "calibrated" | "uncalibrated";
export type MethodFilter = "all" | CombineMethod;

// A run counts as "calibrated" when it recorded a non-empty calibration status
// (the additive `calstat` column, "dark+flat"/"bias+flat"/…). Pre-v0.48 runs
// and uncalibrated stacks have a null/empty calstat.
export function isCalibrated(it: GalleryItem): boolean {
  return !!(it.calstat && it.calstat.trim());
}

// Filter items by calibration status. "all" is a passthrough; "calibrated" keeps
// runs that applied any master; "uncalibrated" keeps the rest. Pure and
// non-mutating so it's easy to test.
export function filterByCalibration(items: GalleryItem[], filter: CalFilter): GalleryItem[] {
  if (filter === "all") return items;
  const want = filter === "calibrated";
  return items.filter((it) => isCalibrated(it) === want);
}

// Order gallery items for display. "newest" preserves the API's timestamp-DESC
// order; "cleanest" puts the lowest-noise stacks first (a global "show me my
// cleanest results" across every target — the recorded σ is normalized to each
// image's own signal range so it's comparable across gain/exposure), with runs
// that carry no measured σ (pre-v0.48 or not computable) kept after, in their
// original order. Pure and non-mutating so it's easy to test.
export function sortGallery(items: GalleryItem[], sort: GallerySort): GalleryItem[] {
  if (sort !== "cleanest") return items;
  const measured = items.filter((it) => hasNoise(it.noise_sigma));
  const rest = items.filter((it) => !hasNoise(it.noise_sigma));
  measured.sort((a, b) => (a.noise_sigma as number) - (b.noise_sigma as number));
  return [...measured, ...rest];
}

// Free-text filter across a run's label (notes), target name, output basename
// and its calibration status ("dark+flat", …) — so a user can find "best RGB
// v2", "M42", or every "flat"-calibrated stack across every target. Pure and
// non-mutating so it's easy to test. An empty/whitespace query matches all.
export function filterGallery(items: GalleryItem[], query: string): GalleryItem[] {
  const q = query.trim().toLowerCase();
  if (!q) return items;
  return items.filter((it) =>
    [it.notes, it.target_name, it.output_basename, it.calstat]
      .some((s) => (s ?? "").toLowerCase().includes(q)));
}

// Filter items by their (coarse) combine method. "all" is a passthrough;
// otherwise keep runs whose effective method matches. Editor/channel-combine runs
// (no method key) are dropped by any non-"all" filter. Pure and non-mutating.
export function filterByMethod(items: GalleryItem[], filter: MethodFilter): GalleryItem[] {
  if (filter === "all") return items;
  return items.filter((it) => combineMethodKey(it.options) === filter);
}

/** Format an option value for display (booleans → On/Off, round floats). */
function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "On" : "Off";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return String(v);
}

/** A few headline settings shown as badges on every card. The combine method
 * (σ-clip / min-max / drizzle) is shown separately by <RejectionBadge>, which
 * carries a plain-language tooltip and honours the engine's method precedence. */
function highlightBadges(opts: Record<string, unknown>) {
  const badges: { label: string; on: boolean }[] = [];
  if (opts.quality_weighted) badges.push({ label: "Quality-weighted", on: true });
  if (opts.background_flatten) badges.push({ label: "BG flatten", on: true });
  if (opts.final_gradient_removal) badges.push({ label: "Gradient removal", on: true });
  if (typeof opts.lucky_fraction === "number" && opts.lucky_fraction < 1) {
    badges.push({ label: `Lucky ${Math.round(opts.lucky_fraction * 100)}%`, on: true });
  }
  return badges;
}

function GalleryCard({ item, labels, onView, selected, onToggleSelect }: {
  item: GalleryItem;
  labels: Map<string, string>;
  onView: (item: GalleryItem) => void;
  selected: boolean;
  onToggleSelect: () => void;
}) {
  const badges = highlightBadges(item.options);
  // Full settings list (only keys we have a label for, in schema order).
  const rows = useMemo(
    () =>
      [...labels.entries()]
        .filter(([key]) => item.options[key] !== undefined)
        .map(([key, label]) => ({ label, value: fmt(item.options[key]) })),
    [item.options, labels],
  );

  return (
    <Card withBorder padding="md" radius="md"
      style={selected ? { outline: "2px solid var(--mantine-color-violet-5)" } : undefined}>
      <Card.Section style={{ position: "relative" }}>
        <Checkbox
          checked={selected} onChange={onToggleSelect}
          aria-label="Select for batch edit"
          styles={{ root: { position: "absolute", top: 8, left: 8, zIndex: 2 } }}
        />
        {item.has_preview ? (
          <Tooltip label="Click to view fullscreen" openDelay={400}>
            <Image
              src={item.preview_url} h={200} fit="contain" bg="#000"
              style={{ cursor: "zoom-in" }}
              onClick={() => onView(item)}
            />
          </Tooltip>
        ) : (
          <Center h={200} bg="dark.6"><Text c="dimmed">No preview</Text></Center>
        )}
      </Card.Section>

      <Group justify="space-between" mt="sm" wrap="nowrap">
        <Text fw={600} truncate component={Link} to={`/targets/${item.safe}/history`}>
          {item.target_name}
        </Text>
        <Group gap={4} wrap="nowrap" style={{ flexShrink: 0 }}>
          <RejectionBadge options={item.options} />
          <HazyNightBadge ratio={item.transparency_ratio} />
          <CalibrationBadge calstat={item.calstat} />
          <Badge variant="light">{item.n_frames_used} frames</Badge>
        </Group>
      </Group>
      {item.notes ? (
        <Text size="sm" c="violet.4" fw={500} truncate title={item.notes}>
          {item.notes}
        </Text>
      ) : null}
      <Text size="xs" c="dimmed">
        {item.output_basename} · {item.timestamp_utc.replace("T", " ").slice(0, 16)}
        {" · "}{item.canvas_w}×{item.canvas_h}
        {item.total_exposure_s ? ` · ${formatIntegration(item.total_exposure_s)}` : ""}
        {hasNoise(item.noise_sigma) ? <> · <NoiseReadout sigma={item.noise_sigma} /></> : null}
      </Text>

      <Group gap="xs" mt="xs" wrap="nowrap">
        <Button
          component={Link} to={`/targets/${item.safe}/edit/${item.run_id}`}
          leftSection={<IconWand size={14} />} variant="light" size="xs"
          style={{ flex: 1 }}
        >
          Edit image
        </Button>
        {item.reusable ? (
          <Tooltip label="Re-run the Stack form pre-filled with this image's settings">
            <Button
              component={Link} to={`/targets/${item.safe}/stack?from=${item.run_id}`}
              leftSection={<IconCopy size={14} />} variant="light" color="gray" size="xs"
            >
              Reuse settings
            </Button>
          </Tooltip>
        ) : null}
      </Group>

      {badges.length > 0 ? (
        <Group gap={6} mt="xs">
          {badges.map((b) => (
            <Badge key={b.label} size="sm" variant="dot" color="violet">{b.label}</Badge>
          ))}
        </Group>
      ) : null}

      {rows.length > 0 ? (
        <Spoiler maxHeight={0} showLabel="Stacking settings" hideLabel="Hide settings" mt="xs">
          <Stack gap={2} mt={6}>
            {rows.map((r) => (
              <Group key={r.label} justify="space-between" gap="xs" wrap="nowrap">
                <Text size="xs" c="dimmed" truncate>{r.label}</Text>
                <Text size="xs" style={{ flexShrink: 0 }}>{r.value}</Text>
              </Group>
            ))}
          </Stack>
        </Spoiler>
      ) : null}
    </Card>
  );
}

export function GalleryView() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const gallery = useQuery({ queryKey: ["gallery"], queryFn: api.getGallery });
  const schema = useQuery({ queryKey: ["stackSchema"], queryFn: api.optionsSchema });
  const presets = useQuery({ queryKey: ["presets"], queryFn: api.listPresets });
  const [viewing, setViewing] = useState<GalleryItem | null>(null);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<GallerySort>("newest");
  const [calFilter, setCalFilter] = useState<CalFilter>("all");
  const [methodFilter, setMethodFilter] = useState<MethodFilter>("all");
  // Batch selection: key "safe:run_id" -> {safe, run_id}.
  const [selected, setSelected] = useState<Record<string, { safe: string; run_id: number }>>({});
  const selKey = (it: GalleryItem) => `${it.safe}:${it.run_id}`;
  const toggleSelect = (it: GalleryItem) =>
    setSelected((s) => {
      const k = selKey(it);
      const next = { ...s };
      if (next[k]) delete next[k]; else next[k] = { safe: it.safe, run_id: it.run_id };
      return next;
    });
  const selItems = Object.values(selected);

  const batch = useMutation({
    mutationFn: (preset_id: string) => api.batchApply({ items: selItems, preset_id }),
    onSuccess: () => {
      notifications.show({ message: `Batch edit started on ${selItems.length} images`, color: "violet" });
      setSelected({});
      qc.invalidateQueries({ queryKey: ["jobs"] });
      navigate("/jobs");
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const applyPreset = (id: string, label: string) => {
    if (window.confirm(`Apply "${label}" to ${selItems.length} image(s)? Each becomes a new edited stack.`)) {
      batch.mutate(id);
    }
  };

  const labels = useMemo(() => {
    const m = new Map<string, string>();
    for (const f of (schema.data ?? []) as StackOptionField[]) {
      // output_name isn't an interesting "setting" to show in the gallery.
      if (f.key !== "output_name") m.set(f.key, f.label);
    }
    return m;
  }, [schema.data]);

  if (gallery.isError && !gallery.data) {
    return <QueryError error={gallery.error} onRetry={() => gallery.refetch()} />;
  }
  if (gallery.isLoading) {
    return <Center h={300}><Loader /></Center>;
  }
  if (gallery.isError) {
    return <Alert color="red" m="md" title="Could not load the gallery">
      {(gallery.error as Error)?.message}
    </Alert>;
  }

  const allItems = gallery.data?.items ?? [];
  // Free-text filter across the run's label (notes), target name, output
  // basename and calibration status — so a user can find "best RGB v2", "M42",
  // or their "flat"-calibrated stacks across every target.
  const items = sortGallery(
    filterByMethod(filterByCalibration(filterGallery(allItems, search), calFilter), methodFilter),
    sort,
  );
  // Only offer the Cleanest sort once it's a meaningful comparison: more than one
  // image and at least one carries a measured σ (pre-v0.48 runs have none).
  const anyNoise = allItems.some((it) => hasNoise(it.noise_sigma));
  const showSort = allItems.length > 1 && anyNoise;
  // Only offer the calibration filter when the set is *mixed* — some calibrated
  // and some not — so it's a useful cut, not a no-op chip.
  const anyCalibrated = allItems.some(isCalibrated);
  const anyUncalibrated = allItems.some((it) => !isCalibrated(it));
  const showCalFilter = anyCalibrated && anyUncalibrated;
  // Combine-method facet: the distinct methods present across all runs (in the
  // engine's precedence order). Only offered when the set is *mixed* (>1 distinct
  // method) so it's a useful cut, not a no-op chip — mirroring the cal filter.
  const METHOD_ORDER: CombineMethod[] = ["drizzle", "min-max", "sigma-clip", "mean"];
  const presentMethods = METHOD_ORDER.filter((m) =>
    allItems.some((it) => combineMethodKey(it.options) === m));
  const showMethodFilter = presentMethods.length > 1;

  return (
    <Stack>
      <Group gap="xs">
        <IconPhoto size={24} />
        <Title order={2}>Gallery</Title>
        <Tooltip label="Every stacked image across all targets">
          <Badge variant="light">{allItems.length}</Badge>
        </Tooltip>
      </Group>

      {allItems.length > 0 ? (
        <Group justify="space-between" wrap="wrap" gap="xs">
          <TextInput
            value={search}
            onChange={(e) => setSearch(e.currentTarget.value)}
            placeholder="Search by label, target, filename or calibration…"
            leftSection={<IconSearch size={16} />}
            maw={420}
            style={{ flex: 1, minWidth: 220 }}
          />
          {showCalFilter ? (
            <Tooltip label="Filter by whether a stack had calibration masters (dark/flat/bias) applied to its lights.">
              <SegmentedControl
                size="xs"
                value={calFilter}
                onChange={(v) => setCalFilter(v as CalFilter)}
                data={[
                  { label: "All", value: "all" },
                  { label: "Calibrated", value: "calibrated" },
                  { label: "Uncalibrated", value: "uncalibrated" },
                ]}
              />
            </Tooltip>
          ) : null}
          {showMethodFilter ? (
            <Tooltip label="Filter by how each stack was combined (drizzle / min-max / σ-clip / mean).">
              <SegmentedControl
                size="xs"
                value={methodFilter}
                onChange={(v) => setMethodFilter(v as MethodFilter)}
                data={[
                  { label: "All", value: "all" },
                  ...presentMethods.map((m) => ({ label: COMBINE_METHOD_LABELS[m], value: m })),
                ]}
              />
            </Tooltip>
          ) : null}
          {showSort ? (
            <Tooltip label="Cleanest sorts by lowest background noise across every target — the σ is normalized so it's comparable between images.">
              <SegmentedControl
                size="xs"
                value={sort}
                onChange={(v) => setSort(v as GallerySort)}
                data={[
                  { label: "Newest", value: "newest" },
                  { label: "Cleanest", value: "cleanest" },
                ]}
              />
            </Tooltip>
          ) : null}
        </Group>
      ) : null}

      {selItems.length ? (
        <Paper withBorder p="sm" pos="sticky" top={8} style={{ zIndex: 3 }}>
          <Group justify="space-between" wrap="wrap" gap="xs">
            <Text fw={600}>{selItems.length} selected</Text>
            <Group gap="xs">
              <Button variant="subtle" size="xs" onClick={() => setSelected({})}>Clear</Button>
              {selItems.length === 2 ? (
                <Button
                  component={Link}
                  to={`/compare?a=${selItems[0].safe}:${selItems[0].run_id}&b=${selItems[1].safe}:${selItems[1].run_id}`}
                  variant="light" color="grape" size="xs"
                  leftSection={<IconGitCompare size={14} />}
                >
                  Compare
                </Button>
              ) : null}
              <Menu shadow="md" position="bottom-end" width={240}>
                <Menu.Target>
                  <Button size="xs" leftSection={<IconWand size={14} />} loading={batch.isPending}>
                    Apply preset to selected
                  </Button>
                </Menu.Target>
                <Menu.Dropdown mah={400} style={{ overflowY: "auto" }}>
                  <Menu.Label>Built-in</Menu.Label>
                  {(presets.data?.builtin ?? []).map((p) => (
                    <Menu.Item key={p.id} onClick={() => applyPreset(p.id, p.label)}>{p.label}</Menu.Item>
                  ))}
                  {(presets.data?.user ?? []).length ? <Menu.Label>My presets</Menu.Label> : null}
                  {(presets.data?.user ?? []).map((p) => (
                    <Menu.Item key={p.id} onClick={() => applyPreset(p.id, p.label)}>{p.label}</Menu.Item>
                  ))}
                </Menu.Dropdown>
              </Menu>
            </Group>
          </Group>
        </Paper>
      ) : null}

      {items.length === 0 ? (
        <Text c="dimmed">
          {search.trim()
            ? `No images match “${search.trim()}”.`
            : methodFilter !== "all"
              ? `No ${COMBINE_METHOD_LABELS[methodFilter]}-combined images.`
              : calFilter !== "all"
                ? `No ${calFilter} images.`
                : "No stacked images yet. Stack a target and its results will appear here."}
        </Text>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3, lg: 4 }}>
          {items.map((it) => (
            <GalleryCard
              key={`${it.safe}-${it.run_id}`} item={it} labels={labels}
              onView={setViewing}
              selected={!!selected[selKey(it)]}
              onToggleSelect={() => toggleSelect(it)}
            />
          ))}
        </SimpleGrid>
      )}

      <ImageLightbox
        src={viewing ? viewing.preview_url : null}
        title={viewing ? `${viewing.target_name} · ${viewing.output_basename}` : undefined}
        downloadHref={viewing?.has_preview
          ? api.stackArtifactUrl(viewing.safe, viewing.run_id, "preview") : undefined}
        jpegHref={viewing?.has_preview
          ? api.stackArtifactUrl(viewing.safe, viewing.run_id, "jpeg") : undefined}
        rawHref={viewing?.has_fits
          ? api.stackArtifactUrl(viewing.safe, viewing.run_id, "fits") : undefined}
        toolbarExtra={viewing?.has_preview
          ? <WallpaperMenu safe={viewing.safe} runId={viewing.run_id} variant="subtle" /> : undefined}
        {...(viewing?.has_preview
          ? (() => {
              const { title, text, filename } = sharePictureText(
                viewing.target_name,
                new Date(viewing.timestamp_utc).toLocaleDateString(),
              );
              return { shareFilename: filename, shareTitle: title, shareText: text };
            })()
          : {})}
        onClose={() => setViewing(null)}
      />
    </Stack>
  );
}
