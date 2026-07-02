import {
  ActionIcon, Alert, Button, Center, Grid, Group, Loader, Menu, Paper, Select, Stack, Text,
  TextInput, Title, Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import {
  IconAlertTriangle, IconArrowBackUp, IconArrowForwardUp, IconArrowLeft, IconDeviceFloppy,
  IconDownload, IconPhotoDown, IconPlus, IconRefresh, IconSparkles, IconZoomScan,
} from "@tabler/icons-react";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type EditOp, type OpInstance, type Recipe } from "../api/client";
import { useUndoable } from "../hooks/useUndoable";
import { ImageLightbox } from "../components/ImageLightbox";
import { Histogram } from "../components/editor/Histogram";
import { OpList } from "../components/editor/OpList";
import { OpParamPanel } from "../components/editor/OpParamPanel";
import { PresetMenu } from "../components/editor/PresetMenu";

const GROUP_LABELS: Record<string, string> = {
  background: "Background", tone: "Tone & color", detail: "Detail",
  stars_geometry: "Stars & geometry",
};
const GROUP_ORDER = ["background", "tone", "detail", "stars_geometry"];

function uid(): string {
  return (crypto.randomUUID?.() ?? Math.random().toString(36).slice(2)).slice(0, 8);
}

function newOp(spec: EditOp): OpInstance {
  const params: Record<string, unknown> = {};
  spec.params.forEach((p) => { params[p.key] = p.default; });
  return { uid: uid(), id: spec.id, enabled: true, params };
}

export function EditorView() {
  const { safe = "", runId = "" } = useParams();
  const rid = Number(runId);
  const qc = useQueryClient();

  const opsSchema = useQuery({ queryKey: ["editor-ops"], queryFn: api.editorOps, staleTime: 60_000 });
  const saved = useQuery({ queryKey: ["recipe", safe, rid], queryFn: () => api.getRecipe(safe, rid) });

  const { state: ops, set: setOps, reset: resetOps, undo, redo, canUndo, canRedo } =
    useUndoable<OpInstance[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [outputName, setOutputName] = useState("");
  const [tiffMode, setTiffMode] = useState("linear");
  const [lightbox, setLightbox] = useState(false);

  // Seed ops from the saved recipe once (clears undo history).
  useEffect(() => {
    if (saved.data) resetOps(saved.data.ops ?? []);
  }, [saved.data, resetOps]);

  const specs = useMemo(() => {
    const m: Record<string, EditOp> = {};
    (opsSchema.data ?? []).forEach((s) => { m[s.id] = s; });
    return m;
  }, [opsSchema.data]);

  const recipe: Recipe = useMemo(() => ({ ops, base_run_id: rid }), [ops, rid]);
  const recipeKey = JSON.stringify(ops);
  const [dKey] = useDebouncedValue(recipeKey, 250);
  const [bust, setBust] = useState(0);
  const dRecipe: Recipe = useMemo(() => {
    let parsed: OpInstance[] = [];
    try { const p = JSON.parse(dKey); if (Array.isArray(p)) parsed = p; } catch { /* keep [] */ }
    return { ops: parsed, base_run_id: rid };
  }, [dKey, rid]);

  // Live preview: fetch as a blob so we get real loading/error states (a failed
  // render shows a message instead of a silently blank panel) and can revoke URLs.
  const preview = useQuery({
    queryKey: ["edit-preview", safe, rid, dKey, bust],
    enabled: !!opsSchema.data && !saved.isLoading,
    queryFn: async () => {
      const res = await fetch(api.editPreviewUrl(safe, rid, dRecipe, bust));
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try { detail = (await res.json()).detail ?? detail; } catch { /* ignore */ }
        throw new Error(detail);
      }
      return URL.createObjectURL(await res.blob());
    },
  });
  useEffect(() => {
    const url = preview.data;
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [preview.data]);

  const hist = useQuery({
    queryKey: ["edit-hist", safe, rid, dKey],
    queryFn: () => api.getHistogram(safe, rid, dRecipe),
    enabled: !!opsSchema.data,
  });
  const refreshPreview = () => {
    setBust(Date.now());
    qc.invalidateQueries({ queryKey: ["edit-hist", safe, rid] });
  };

  // Before/after: lazily fetch the base (no-ops) render to compare against.
  const [showBase, setShowBase] = useState(false);
  const basePreview = useQuery({
    queryKey: ["edit-base", safe, rid],
    enabled: showBase && !!opsSchema.data && !saved.isLoading,
    queryFn: async () => {
      const res = await fetch(api.editPreviewUrl(safe, rid, { ops: [], base_run_id: rid }));
      if (!res.ok) throw new Error("base preview failed");
      return URL.createObjectURL(await res.blob());
    },
  });
  useEffect(() => {
    const u = basePreview.data;
    return () => { if (u) URL.revokeObjectURL(u); };
  }, [basePreview.data]);

  // Star-mask overlay: lazily fetch the soft mask that gates the star ops so the
  // user can see what the editor treats as stars vs background/nebula.
  const [showMask, setShowMask] = useState(false);
  const maskPreview = useQuery({
    queryKey: ["edit-mask", safe, rid],
    enabled: showMask && !!opsSchema.data && !saved.isLoading,
    queryFn: async () => {
      const res = await fetch(api.editStarMaskUrl(safe, rid));
      if (!res.ok) throw new Error("star mask preview failed");
      return URL.createObjectURL(await res.blob());
    },
  });
  useEffect(() => {
    const u = maskPreview.data;
    return () => { if (u) URL.revokeObjectURL(u); };
  }, [maskPreview.data]);

  const shownSrc = showMask
    ? (maskPreview.data ?? preview.data)
    : showBase
      ? (basePreview.data ?? preview.data)
      : preview.data;

  // Keyboard undo/redo for the op pipeline: Cmd/Ctrl+Z undoes, Cmd/Ctrl+Shift+Z
  // (or Ctrl+Y) redoes. Skipped while typing in a field so editing the output
  // name / curve inputs isn't hijacked.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || el?.isContentEditable) return;
      const key = e.key.toLowerCase();
      if (key === "z") {
        e.preventDefault();
        if (e.shiftKey) { if (canRedo) redo(); }
        else if (canUndo) undo();
      } else if (key === "y") {
        e.preventDefault();
        if (canRedo) redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo, canUndo, canRedo]);

  // --- mutations -----------------------------------------------------------
  const saveRecipe = useMutation({
    mutationFn: () => api.putRecipe(safe, rid, recipe),
    onSuccess: () => {
      notifications.show({ message: "Recipe saved", color: "teal" });
      qc.invalidateQueries({ queryKey: ["recipe", safe, rid] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const auto = useMutation({
    mutationFn: () => api.autoProcess(safe, rid),
    onSuccess: (r) => {
      setOps((r.ops ?? []).map((o) => ({ ...o, uid: o.uid || uid() })));
      notifications.show({ message: "Auto-process applied — tweak from here", color: "violet" });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const exportRun = useMutation({
    mutationFn: () => api.exportRun(safe, rid, recipe, outputName.trim() || `${safe}_edit`, tiffMode),
    onSuccess: () => {
      // Stay in the editor (don't bounce to Jobs); the navbar job badge tracks it.
      notifications.show({
        message: "Export running — the new image will appear in History when done.",
        color: "violet",
      });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const downloadPng = useMutation({
    mutationFn: async () => {
      const { job_id } = await api.exportPng(safe, rid, recipe);
      // Full-res render can be slow on mosaics — poll the job to completion.
      for (;;) {
        const j = await api.getJob(job_id);
        if (j.state === "done") return job_id;
        if (["error", "cancelled", "interrupted"].includes(j.state)) {
          throw new Error(j.error || "PNG render failed");
        }
        await new Promise((r) => setTimeout(r, 500));
      }
    },
    onSuccess: (jobId) => {
      const a = document.createElement("a");
      a.href = api.editPngUrl(safe, rid, jobId);
      document.body.appendChild(a);
      a.click();
      a.remove();
      notifications.show({ message: "Full-resolution PNG ready", color: "teal" });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  // --- op list ops ---------------------------------------------------------
  const addOp = (spec: EditOp) => {
    const op = newOp(spec);
    setOps((p) => [...p, op]);
    setSelected(op.uid);
  };
  const move = (u: string, dir: -1 | 1) => setOps((p) => {
    const i = p.findIndex((o) => o.uid === u);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= p.length) return p;
    const next = [...p];
    [next[i], next[j]] = [next[j], next[i]];
    return next;
  });
  const toggle = (u: string) =>
    setOps((p) => p.map((o) => (o.uid === u ? { ...o, enabled: !o.enabled } : o)));
  const remove = (u: string) => {
    setOps((p) => p.filter((o) => o.uid !== u));
    setSelected((s) => (s === u ? null : s));
  };
  const setParams = (u: string, params: Record<string, unknown>) =>
    setOps((p) => p.map((o) => (o.uid === u ? { ...o, params } : o)));

  const selectedOp = ops.find((o) => o.uid === selected) ?? null;
  const grouped = useMemo(() => {
    const g: Record<string, EditOp[]> = {};
    (opsSchema.data ?? []).forEach((s) => { (g[s.group] ??= []).push(s); });
    return g;
  }, [opsSchema.data]);

  if (opsSchema.isLoading || saved.isLoading) {
    return <Center h={300}><Loader /></Center>;
  }

  return (
    <Stack>
      <Group justify="space-between" wrap="wrap">
        <Group gap="xs">
          <Button component={Link} to={`/targets/${safe}/history`} variant="subtle"
            leftSection={<IconArrowLeft size={16} />}>History</Button>
          <Title order={2}>Editor — {safe}</Title>
        </Group>
        <Group gap="xs">
          <Tooltip label="Undo (Ctrl+Z)"><ActionIcon variant="default" disabled={!canUndo}
            onClick={undo} aria-label="Undo"><IconArrowBackUp size={16} /></ActionIcon></Tooltip>
          <Tooltip label="Redo (Ctrl+Shift+Z)"><ActionIcon variant="default" disabled={!canRedo}
            onClick={redo} aria-label="Redo"><IconArrowForwardUp size={16} /></ActionIcon></Tooltip>
          <Button variant="light" color="grape" leftSection={<IconSparkles size={16} />}
            loading={auto.isPending} onClick={() => auto.mutate()}>Auto-process</Button>
          <PresetMenu currentOps={ops} onApply={(o) => setOps(o)} />
          <Button variant="default" leftSection={<IconDeviceFloppy size={16} />}
            loading={saveRecipe.isPending} onClick={() => saveRecipe.mutate()}>Save</Button>
        </Group>
      </Group>

      <Grid>
        {/* Preview + histogram */}
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Paper withBorder p="xs">
            <div style={{ position: "relative", background: "#000", borderRadius: 8, minHeight: 220 }}>
              {hist.data?.empty ? (
                <Alert color="yellow" icon={<IconAlertTriangle size={16} />} m="md">
                  This stack has no image data (all pixels are empty) — it likely failed to
                  plate-solve or stack, so there's nothing to edit. Check the stack on the
                  Target page.
                </Alert>
              ) : preview.isError ? (
                <Alert color="red" icon={<IconAlertTriangle size={16} />} m="md">
                  Preview failed: {(preview.error as Error)?.message}
                  <div>
                    <Button size="xs" variant="light" color="red" mt="xs"
                      leftSection={<IconRefresh size={14} />} onClick={refreshPreview}>
                      Retry
                    </Button>
                  </div>
                </Alert>
              ) : shownSrc ? (
                <img src={shownSrc} alt="preview"
                  style={{ display: "block", width: "100%", maxHeight: "62vh",
                           objectFit: "contain", cursor: "zoom-in" }}
                  onClick={() => setLightbox(true)} />
              ) : (
                <Center h={240}><Loader /></Center>
              )}
              {showMask || showBase ? (
                <Text size="xs" c="white" style={{ position: "absolute", left: 12, top: 10,
                  background: "rgba(0,0,0,0.6)", padding: "2px 8px", borderRadius: 4 }}>
                  {showMask ? "Star mask" : "Original"}
                </Text>
              ) : null}
              <Group gap={6} style={{ position: "absolute", right: 8, top: 8 }}>
                <Tooltip label="Show the soft mask that gates star ops (white = treated as a star)">
                  <Button size="xs" variant={showMask ? "filled" : "default"}
                    color="grape"
                    disabled={!preview.data}
                    loading={showMask && maskPreview.isLoading}
                    onClick={() => setShowMask((s) => { if (!s) setShowBase(false); return !s; })}>
                    {showMask ? "Hide mask" : "Star mask"}
                  </Button>
                </Tooltip>
                <Button size="xs" variant={showBase ? "filled" : "default"}
                  disabled={!preview.data || showMask}
                  onClick={() => setShowBase((s) => !s)}>
                  {showBase ? "Edited" : "Compare"}
                </Button>
                <Button size="xs" variant="default" leftSection={<IconRefresh size={14} />}
                  loading={preview.isFetching} onClick={refreshPreview}>Refresh</Button>
                <Button size="xs" variant="default" leftSection={<IconZoomScan size={14} />}
                  disabled={!shownSrc} onClick={() => setLightbox(true)}>Zoom</Button>
              </Group>
            </div>
            <Histogram data={hist.data} />
            {hist.data?.errors?.length ? (
              <Alert color="orange" icon={<IconAlertTriangle size={16} />} mt="xs" py={6}>
                <Text size="xs">
                  Skipped {hist.data.errors.length} failed operation(s): {hist.data.errors.join("; ")}
                </Text>
              </Alert>
            ) : null}
          </Paper>
        </Grid.Col>

        {/* Controls */}
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Stack>
            <Menu shadow="md" position="bottom-start" width={240}>
              <Menu.Target>
                <Button leftSection={<IconPlus size={16} />} variant="light">Add operation</Button>
              </Menu.Target>
              <Menu.Dropdown mah={400} style={{ overflowY: "auto" }}>
                {GROUP_ORDER.filter((g) => grouped[g]).map((g) => (
                  <div key={g}>
                    <Menu.Label>{GROUP_LABELS[g] ?? g}</Menu.Label>
                    {grouped[g].map((s) => (
                      <Menu.Item key={s.id} onClick={() => addOp(s)}>
                        <Text size="sm">{s.label}</Text>
                        {s.help ? (
                          <Text size="10px" c="dimmed" lineClamp={2}>{s.help}</Text>
                        ) : null}
                      </Menu.Item>
                    ))}
                  </div>
                ))}
              </Menu.Dropdown>
            </Menu>

            <Paper withBorder p="sm">
              <Text fw={600} size="sm" mb={6}>Pipeline</Text>
              <OpList ops={ops} specs={specs} selected={selected} onSelect={setSelected}
                onMove={move} onToggle={toggle} onRemove={remove} />
            </Paper>

            {selectedOp && specs[selectedOp.id] ? (
              <Paper withBorder p="sm">
                <Text fw={600} size="sm" mb={6}>{specs[selectedOp.id].label}</Text>
                {specs[selectedOp.id].help ? (
                  <Text size="xs" c="dimmed" mb="xs">{specs[selectedOp.id].help}</Text>
                ) : null}
                <OpParamPanel spec={specs[selectedOp.id]} params={selectedOp.params}
                  histogram={hist.data} onChange={(p) => setParams(selectedOp.uid, p)} />
              </Paper>
            ) : null}

            <Paper withBorder p="sm">
              <Text fw={600} size="sm" mb={6}>Export full resolution</Text>
              <Group align="flex-end" gap="xs">
                <TextInput label="Output name" placeholder={`${safe}_edit`} value={outputName}
                  onChange={(e) => setOutputName(e.currentTarget.value)} style={{ flex: 1 }} />
                <Select label="TIFF" w={130} data={["linear", "autostretch"]} value={tiffMode}
                  allowDeselect={false} onChange={(v) => setTiffMode(v ?? "linear")} />
              </Group>
              <Button mt="sm" fullWidth leftSection={<IconDownload size={16} />}
                loading={exportRun.isPending} onClick={() => exportRun.mutate()}>
                Export as new image
              </Button>
              <Button mt="xs" fullWidth variant="light" leftSection={<IconPhotoDown size={16} />}
                loading={downloadPng.isPending} onClick={() => downloadPng.mutate()}>
                Download full-res PNG
              </Button>
              <Text size="xs" c="dimmed" mt={6}>
                "Export" writes a new stack run (FITS/TIFF/PNG); the original is never
                changed. "Download full-res PNG" renders your edits at native resolution
                and downloads the PNG (can be slow on large/mosaic images).
              </Text>
            </Paper>
          </Stack>
        </Grid.Col>
      </Grid>

      <ImageLightbox src={lightbox ? (shownSrc ?? null) : null}
        title={`${safe} — ${showBase ? "original" : "edited"}`} onClose={() => setLightbox(false)} />
    </Stack>
  );
}
