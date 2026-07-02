import { useMemo, useState } from "react";
import {
  Alert, Badge, Button, Card, Center, Checkbox, Group, Image, Loader, Menu, Paper,
  SimpleGrid, Spoiler, Stack, Text, Title, Tooltip,
} from "@mantine/core";
import { IconCopy, IconPhoto, IconWand } from "@tabler/icons-react";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, type GalleryItem, type StackOptionField } from "../api/client";
import { formatIntegration } from "../format";
import { ImageLightbox } from "../components/ImageLightbox";
import { QueryError } from "../components/QueryError";

/** Format an option value for display (booleans → On/Off, round floats). */
function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "On" : "Off";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return String(v);
}

/** A few headline settings shown as badges on every card. */
function highlightBadges(opts: Record<string, unknown>) {
  const badges: { label: string; on: boolean }[] = [];
  if (opts.sigma_clip) badges.push({ label: `σ-clip κ${fmt(opts.sigma_kappa)}`, on: true });
  if (opts.quality_weighted) badges.push({ label: "Quality-weighted", on: true });
  if (opts.background_flatten) badges.push({ label: "BG flatten", on: true });
  if (opts.drizzle) badges.push({ label: `Drizzle ×${fmt(opts.drizzle_scale)}`, on: true });
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
        <Badge variant="light" style={{ flexShrink: 0 }}>{item.n_frames_used} frames</Badge>
      </Group>
      <Text size="xs" c="dimmed">
        {item.output_basename} · {item.timestamp_utc.replace("T", " ").slice(0, 16)}
        {" · "}{item.canvas_w}×{item.canvas_h}
        {item.total_exposure_s ? ` · ${formatIntegration(item.total_exposure_s)}` : ""}
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

  const items = gallery.data?.items ?? [];

  return (
    <Stack>
      <Group gap="xs">
        <IconPhoto size={24} />
        <Title order={2}>Gallery</Title>
        <Tooltip label="Every stacked image across all targets">
          <Badge variant="light">{items.length}</Badge>
        </Tooltip>
      </Group>

      {selItems.length ? (
        <Paper withBorder p="sm" pos="sticky" top={8} style={{ zIndex: 3 }}>
          <Group justify="space-between" wrap="wrap" gap="xs">
            <Text fw={600}>{selItems.length} selected</Text>
            <Group gap="xs">
              <Button variant="subtle" size="xs" onClick={() => setSelected({})}>Clear</Button>
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
          No stacked images yet. Stack a target and its results will appear here.
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
        downloadHref={viewing?.has_fits
          ? api.stackArtifactUrl(viewing.safe, viewing.run_id, "fits") : undefined}
        onClose={() => setViewing(null)}
      />
    </Stack>
  );
}
