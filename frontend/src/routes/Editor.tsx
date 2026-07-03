import {
  ActionIcon, Alert, Button, Center, Grid, Group, Loader, Menu, Paper, Select, Stack, Text,
  TextInput, Title, Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import {
  IconAlertTriangle, IconArrowBackUp, IconArrowForwardUp, IconArrowLeft, IconChevronDown,
  IconChevronUp, IconDeviceFloppy, IconDownload, IconInfoCircle, IconPhotoDown, IconPlus,
  IconRefresh, IconSparkles, IconWand, IconZoomScan,
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
import { hasEnabledStretch, insertOnCorrectSide, moveToCorrectSide } from "../components/editor/stageConflicts";
import { autoSummarySentence } from "../components/editor/autoSummary";
import { previewScaleCaption } from "../components/editor/previewScale";
import { OpParamPanel } from "../components/editor/OpParamPanel";
import { PresetMenu } from "../components/editor/PresetMenu";

const GROUP_LABELS: Record<string, string> = {
  background: "Background", tone: "Tone & color", detail: "Detail",
  stars_geometry: "Stars & geometry",
};
const GROUP_ORDER = ["background", "tone", "detail", "stars_geometry"];

// The handful of ops a beginner actually reaches for, surfaced in a curated
// "Common" section at the top of the Add-operation menu so the first-time path is
// obvious; the full grouped list stays one click away under "More operations".
const COMMON_OP_IDS = [
  "tone.stretch", "tone.curves", "tone.saturation", "tone.scnr",
  "detail.denoise", "detail.sharpen", "background.subtract",
];

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
  // Data-driven default for the deconvolution PSF width: the target's median
  // star FWHM converted to a Gaussian σ, offered as a one-click button.
  const psf = useQuery({
    queryKey: ["psf-suggestion", safe],
    queryFn: () => api.psfSuggestion(safe),
    staleTime: 60_000,
  });
  // Data-driven default for noise reduction: the run's measured background
  // noise mapped to a starting strength, offered as a one-click button.
  const denoise = useQuery({
    queryKey: ["denoise-suggestion", safe, rid],
    queryFn: () => api.denoiseSuggestion(safe, rid),
    staleTime: 60_000,
  });
  // Data-driven default for the sharpen radius: the target's median star FWHM
  // converted to a Gaussian σ (the natural detail scale), offered as a button.
  const sharpen = useQuery({
    queryKey: ["sharpen-suggestion", safe],
    queryFn: () => api.sharpenSuggestion(safe),
    staleTime: 60_000,
  });
  // Data-driven default for star reduction: the target's median star FWHM is the
  // star's own scale in px, offered as a one-click button for the `size` param.
  const starSize = useQuery({
    queryKey: ["star-size-suggestion", safe],
    queryFn: () => api.starSizeSuggestion(safe),
    staleTime: 60_000,
  });

  const { state: ops, set: setOps, reset: resetOps, undo, redo, canUndo, canRedo } =
    useUndoable<OpInstance[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [showAllOps, setShowAllOps] = useState(false);
  const [outputName, setOutputName] = useState("");
  const [tiffMode, setTiffMode] = useState("linear");
  const [lightbox, setLightbox] = useState(false);
  // Plain-language summary of what the last Auto-process run did, shown as a
  // dismissible note so the one-click result isn't a black box (null = hidden).
  // `autoKey` is the recipe signature right after Auto ran; once the pipeline
  // diverges from it (manual edit, undo, redo) the note is cleared so it never
  // misdescribes the current state.
  const [autoSummary, setAutoSummary] = useState<string | null>(null);
  const [autoKey, setAutoKey] = useState<string | null>(null);

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
  // Once the pipeline diverges from what Auto-process produced, drop the
  // "What Auto-process did" note so it can't misdescribe the current recipe.
  useEffect(() => {
    if (autoKey !== null && recipeKey !== autoKey) {
      setAutoSummary(null);
      setAutoKey(null);
    }
  }, [recipeKey, autoKey]);
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

  // Per-op "show without this op" compare: render the full recipe with just the
  // selected op bypassed, so while tuning one op the user sees exactly *its*
  // contribution (unlike Compare, which shows the whole recipe vs the raw base).
  // Resets whenever the selection changes so each op starts from "showing with".
  const [soloExclude, setSoloExclude] = useState(false);
  useEffect(() => { setSoloExclude(false); }, [selected]);
  const selForSolo = ops.find((o) => o.uid === selected) ?? null;
  const soloActive = soloExclude && !!selForSolo && selForSolo.enabled;
  const withoutOpPreview = useQuery({
    queryKey: ["edit-without-op", safe, rid, dKey, selected, bust],
    enabled: soloActive && !!opsSchema.data && !saved.isLoading,
    queryFn: async () => {
      const withoutRecipe: Recipe = {
        ops: dRecipe.ops.map((o) => (o.uid === selected ? { ...o, enabled: false } : o)),
        base_run_id: rid,
      };
      const res = await fetch(api.editPreviewUrl(safe, rid, withoutRecipe, bust));
      if (!res.ok) throw new Error("compare render failed");
      return URL.createObjectURL(await res.blob());
    },
  });
  useEffect(() => {
    const u = withoutOpPreview.data;
    return () => { if (u) URL.revokeObjectURL(u); };
  }, [withoutOpPreview.data]);

  const shownSrc = showMask
    ? (maskPreview.data ?? preview.data)
    : showBase
      ? (basePreview.data ?? preview.data)
      : soloActive
        ? (withoutOpPreview.data ?? preview.data)
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
      const built = (r.ops ?? []).map((o) => ({ ...o, uid: o.uid || uid() }));
      setOps(built);
      setAutoSummary(autoSummarySentence(built, specs));
      setAutoKey(JSON.stringify(built));
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
    // Insert on the correct side of the (enabled) stretch — linear ops just
    // before it, nonlinear just after — so a newly-added op doesn't land at the
    // end and immediately trip the stage-conflict caution. Falls back to
    // appending when there's no stretch or the op fits either side.
    setOps((p) => insertOnCorrectSide(p, op, specs));
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
  const fixStage = (u: string) => setOps((p) => moveToCorrectSide(p, u, specs));

  const selectedOp = ops.find((o) => o.uid === selected) ?? null;
  // No enabled stretch → the pipeline silently applies a default asinh stretch at
  // the end. Nudge the user to add/enable an explicit, controllable one.
  const disabledStretch = ops.find((o) => !o.enabled && specs[o.id]?.is_stretch) ?? null;
  const noStretch = ops.length > 0 && !hasEnabledStretch(ops, specs);
  const addOrEnableStretch = () => {
    if (disabledStretch) toggle(disabledStretch.uid);
    else if (specs["tone.stretch"]) addOp(specs["tone.stretch"]);
  };
  const grouped = useMemo(() => {
    const g: Record<string, EditOp[]> = {};
    (opsSchema.data ?? []).forEach((s) => { (g[s.group] ??= []).push(s); });
    return g;
  }, [opsSchema.data]);
  // The curated common ops, in the order they're listed, restricted to ops the
  // engine actually exposes (so it degrades gracefully if an op is removed).
  const commonOps = useMemo(
    () => COMMON_OP_IDS.map((id) => specs[id]).filter((s): s is EditOp => !!s),
    [specs],
  );

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
              {showMask || showBase || soloActive ? (
                <Text size="xs" c="white" style={{ position: "absolute", left: 12, top: 10,
                  background: "rgba(0,0,0,0.6)", padding: "2px 8px", borderRadius: 4 }}>
                  {showMask ? "Star mask" : showBase ? "Original"
                    : `Without: ${specs[selForSolo!.id]?.label ?? selForSolo!.id}`}
                </Text>
              ) : null}
              <Group gap={6} style={{ position: "absolute", right: 8, top: 8 }}>
                <Tooltip label="Show the soft mask that gates star ops (white = treated as a star)">
                  <Button size="xs" variant={showMask ? "filled" : "default"}
                    color="grape"
                    disabled={!preview.data}
                    loading={showMask && maskPreview.isLoading}
                    onClick={() => setShowMask((s) => {
                      if (!s) { setShowBase(false); setSoloExclude(false); } return !s;
                    })}>
                    {showMask ? "Hide mask" : "Star mask"}
                  </Button>
                </Tooltip>
                <Button size="xs" variant={showBase ? "filled" : "default"}
                  disabled={!preview.data || showMask}
                  onClick={() => setShowBase((s) => { if (!s) setSoloExclude(false); return !s; })}>
                  {showBase ? "Edited" : "Compare"}
                </Button>
                <Button size="xs" variant="default" leftSection={<IconRefresh size={14} />}
                  loading={preview.isFetching} onClick={refreshPreview}>Refresh</Button>
                <Button size="xs" variant="default" leftSection={<IconZoomScan size={14} />}
                  disabled={!shownSrc} onClick={() => setLightbox(true)}>Zoom</Button>
              </Group>
            </div>
            <Histogram data={hist.data} />
            {previewScaleCaption(hist.data) ? (
              <Text size="xs" c="dimmed" mt={4}>
                {previewScaleCaption(hist.data)}
              </Text>
            ) : null}
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
                {/* Curated "Common" section first so a beginner isn't faced with
                    all ~19 ops at once; the full list is one click away below. */}
                {commonOps.length ? (
                  <div>
                    <Menu.Label>Common</Menu.Label>
                    {commonOps.map((s) => (
                      <Menu.Item key={s.id} onClick={() => addOp(s)}>
                        <Text size="sm">{s.label}</Text>
                        {s.help ? (
                          <Text size="10px" c="dimmed" lineClamp={2}>{s.help}</Text>
                        ) : null}
                      </Menu.Item>
                    ))}
                  </div>
                ) : null}
                <Menu.Item closeMenuOnClick={false}
                  leftSection={showAllOps
                    ? <IconChevronUp size={14} /> : <IconChevronDown size={14} />}
                  onClick={() => setShowAllOps((v) => !v)}>
                  <Text size="sm" c="dimmed">
                    {showAllOps ? "Fewer operations" : "More operations"}
                  </Text>
                </Menu.Item>
                {showAllOps
                  ? GROUP_ORDER.filter((g) => grouped[g]).map((g) => (
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
                  ))
                  : null}
              </Menu.Dropdown>
            </Menu>

            {autoSummary ? (
              <Alert color="violet" variant="light" py={8} withCloseButton
                icon={<IconWand size={16} />} title="What Auto-process did"
                onClose={() => setAutoSummary(null)}>
                <Text size="xs">{autoSummary}</Text>
                <Text size="10px" c="dimmed" mt={4}>
                  These steps were chosen from your image — tweak or remove any of them below.
                </Text>
              </Alert>
            ) : null}

            <Paper withBorder p="sm">
              <Text fw={600} size="sm" mb={6}>Pipeline</Text>
              <OpList ops={ops} specs={specs} selected={selected} onSelect={setSelected}
                onMove={move} onToggle={toggle} onRemove={remove} onFix={fixStage} />
              {ops.length === 0 ? (
                <Alert color="grape" variant="light" py={8} mt="xs"
                  icon={<IconSparkles size={16} />}>
                  <Text size="xs" mb={6}>
                    New to this? Let <b>Auto-process</b> build a good starting recipe from
                    your image (background &amp; colour balance, a natural stretch, gentle
                    denoise/sharpen) — then tweak from there. Or add operations one at a time.
                  </Text>
                  <Button size="compact-xs" variant="light" color="grape"
                    leftSection={<IconSparkles size={14} />}
                    loading={auto.isPending} onClick={() => auto.mutate()}>
                    Auto-process
                  </Button>
                </Alert>
              ) : null}
              {noStretch ? (
                <Alert color="yellow" variant="light" py={8} mt="xs"
                  icon={<IconAlertTriangle size={16} />}>
                  <Text size="xs" mb={6}>
                    No <b>Stretch</b> step — a default stretch is applied automatically at
                    the end so the preview isn't black, but your tone &amp; colour ops are
                    running on un-stretched (linear) data. Add a Stretch op to control the
                    look and put those ops on the right side of it.
                  </Text>
                  <Button size="compact-xs" variant="light" color="yellow"
                    leftSection={<IconPlus size={14} />} onClick={addOrEnableStretch}>
                    {disabledStretch ? "Enable stretch" : "Add stretch"}
                  </Button>
                </Alert>
              ) : null}
            </Paper>

            {selectedOp && specs[selectedOp.id] ? (
              <Paper withBorder p="sm">
                <Group justify="space-between" wrap="nowrap" mb={6}>
                  <Text fw={600} size="sm">{specs[selectedOp.id].label}</Text>
                  {selectedOp.enabled ? (
                    <Tooltip
                      label="Preview the image with only this op bypassed, to see just its effect"
                      multiline w={220} withArrow>
                      <Button size="compact-xs"
                        variant={soloActive ? "filled" : "default"} color="grape"
                        loading={soloActive && withoutOpPreview.isLoading}
                        disabled={!preview.data}
                        onClick={() => setSoloExclude((s) => {
                          if (!s) { setShowBase(false); setShowMask(false); } return !s;
                        })}>
                        {soloActive ? "Showing without" : "Without this op"}
                      </Button>
                    </Tooltip>
                  ) : null}
                </Group>
                {specs[selectedOp.id].help ? (
                  <Text size="xs" c="dimmed" mb="xs">{specs[selectedOp.id].help}</Text>
                ) : null}
                {!specs[selectedOp.id].proxy_safe && selectedOp.enabled ? (
                  <Alert color="grape" variant="light" py={6} mb="xs"
                    icon={<IconInfoCircle size={16} />}>
                    <Text size="xs">
                      The live preview doesn't show this effect — it's heavy, so it only
                      runs when you Export or "Download full-res PNG". Adjust its settings
                      here, then export to see the result at full resolution.
                    </Text>
                  </Alert>
                ) : null}
                <OpParamPanel spec={specs[selectedOp.id]} params={selectedOp.params}
                  histogram={hist.data} onChange={(p) => setParams(selectedOp.uid, p)}
                  suggestions={
                    selectedOp.id === "detail.deconvolve" && psf.data?.psf_sigma != null
                      ? {
                        psf_sigma: {
                          value: psf.data.psf_sigma,
                          label: `From your stars (σ≈${psf.data.psf_sigma}, FWHM ${psf.data.fwhm_px}px)`,
                        },
                      }
                      : selectedOp.id === "detail.denoise" && denoise.data?.strength != null
                        ? {
                          strength: {
                            value: denoise.data.strength,
                            label: `From your image (strength ${denoise.data.strength})`,
                          },
                        }
                        : selectedOp.id === "detail.sharpen" && sharpen.data?.radius != null
                          ? {
                            radius: {
                              value: sharpen.data.radius,
                              label: `From your stars (radius ${sharpen.data.radius}, FWHM ${sharpen.data.fwhm_px}px)`,
                            },
                          }
                          : selectedOp.id === "stars.reduce" && starSize.data?.size != null
                            ? {
                              size: {
                                value: starSize.data.size,
                                label: `From your stars (size ${starSize.data.size}, FWHM ${starSize.data.fwhm_px}px)`,
                              },
                            }
                            : undefined
                  } />
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
        title={`${safe} — ${showBase ? "original" : "edited"}`
          + (previewScaleCaption(hist.data) ? ` · ${previewScaleCaption(hist.data)}` : "")}
        onClose={() => setLightbox(false)} />
    </Stack>
  );
}
