import {
  ActionIcon, Alert, Badge, Button, Center, Grid, Group, Loader, Menu, Paper, Select, Stack, Text,
  TextInput, Title, Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import {
  IconAlertTriangle, IconArrowBackUp, IconArrowForwardUp, IconArrowLeft, IconChevronDown,
  IconChevronUp, IconCrop, IconDeviceFloppy, IconDownload, IconInfoCircle, IconPhotoDown,
  IconPlus, IconRefresh, IconSparkles, IconWand, IconZoomScan,
} from "@tabler/icons-react";
import { notifications } from "@mantine/notifications";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type EditOp, type OpInstance, type Recipe } from "../api/client";
import { useUndoable } from "../hooks/useUndoable";
import { ImageLightbox } from "../components/ImageLightbox";
import { Histogram } from "../components/editor/Histogram";
import { levelsHistGuides } from "../components/editor/levelsGuides";
import { OpList } from "../components/editor/OpList";
import { degenerateLevelsUids, extraEnabledStretchUids, hasEnabledStretch, insertOnCorrectSide, moveToCorrectSide }
  from "../components/editor/stageConflicts";
import { autoSummarySentence, autoValueSentence } from "../components/editor/autoSummary";
import { applyDataDrivenDefaults, countDataDrivenDefaults, type OpSuggestion }
  from "../components/editor/dataDrivenDefaults";
import { previewScaleCaption } from "../components/editor/previewScale";
import { prependCoverageLeveling } from "../components/editor/coverageLeveling";
import { applyTrimCrop, trimRectStyle, trimKeptLabel, hasEnabledGeometryOp }
  from "../components/editor/mosaicTrim";
import { pngProgressLabel } from "../components/editor/pngProgress";
import { opErrorsMessage } from "../components/editor/opErrors";
import { clippingCaption } from "../components/editor/clipping";
import { previewDebounceMs } from "../components/editor/previewDebounce";
import { starMaskSizePx } from "../components/editor/starMaskSize";
import { levelsAtIdentity, resetLevelsPoints } from "../components/editor/levelsReset";
import { coalesceFwhm, measuredContextText } from "../components/editor/measuredContext";
import { OpParamPanel } from "../components/editor/OpParamPanel";
import { PresetMenu } from "../components/editor/PresetMenu";
import { HintLabel } from "../components/StackOptionControl";

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

/** A small "slower preview" chip for `heavy` ops, so a beginner knows before
 * adding the op why its live preview updates after a beat rather than instantly. */
function SlowPreviewChip() {
  return (
    <Tooltip label="Slow to render — the live preview updates after a short pause" withArrow>
      <Badge size="xs" variant="light" color="grape" style={{ flexShrink: 0, cursor: "help" }}>
        slower preview
      </Badge>
    </Tooltip>
  );
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
  // One-click "trim the ragged mosaic border": the largest well-covered rectangle
  // of this run's coverage map, offered only on a mosaic (the endpoint returns a
  // null crop for a single-field stack, so the button simply doesn't appear).
  const trim = useQuery({
    queryKey: ["trim-suggestion", safe, rid],
    queryFn: () => api.trimSuggestion(safe, rid),
    staleTime: 60_000,
  });

  // "Your data" context chip: a single dimmed line near the title showing what
  // the editor measured about *this* stack (star FWHM, background noise), so the
  // data-driven suggestion buttons have visible provenance. Reuses the already-
  // fetched suggestion queries; shown only when at least one measure is available.
  const measuredText = useMemo(
    () => measuredContextText({
      fwhm_px: coalesceFwhm(
        psf.data?.fwhm_px, sharpen.data?.fwhm_px, starSize.data?.fwhm_px),
      noise_sigma: denoise.data?.noise_sigma,
    }),
    [psf.data, sharpen.data, starSize.data, denoise.data],
  );

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
  // The data-driven values Auto picked (denoise strength, STF sky level,
  // saturation, sharpen radius), shown under the summary so the note explains
  // *this, because of my data* — not just which ops ran.
  const [autoValues, setAutoValues] = useState<string | null>(null);
  const [autoKey, setAutoKey] = useState<string | null>(null);

  // Seed ops from the saved recipe exactly once per run. Re-seeding on every
  // `saved.data` change would wipe undo/redo history and clobber edits made while
  // a save was in flight (saving invalidates the recipe query, which refetches a
  // structurally-different snapshot), so we gate on a per-run `seeded` flag. The
  // gate also holds the live preview until the recipe is loaded, so the editor
  // never flashes the un-edited image (and wastes a proxy render) on open.
  const [seeded, setSeeded] = useState(false);
  useEffect(() => { setSeeded(false); }, [rid]);
  useEffect(() => {
    if (saved.data && !seeded) {
      resetOps(saved.data.ops ?? []);
      setSeeded(true);
    }
  }, [saved.data, seeded, resetOps]);

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
      setAutoValues(null);
      setAutoKey(null);
    }
  }, [recipeKey, autoKey]);
  // Settle the live preview longer while an *enabled, expensive* op is in the
  // pipeline (deconvolution, wavelet denoise), so dragging a slider re-renders
  // only the value you land on instead of every intermediate frame through a
  // slow op; light-only recipes keep the snappy short debounce.
  const debounceMs = useMemo(() => previewDebounceMs(ops, specs), [ops, specs]);
  const [dKey] = useDebouncedValue(recipeKey, debounceMs);
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
    enabled: !!opsSchema.data && !saved.isLoading && seeded,
    // Keep the previous render visible while the next one loads (rather than
    // flashing to a black Loader on every slider drag); the "Updating…" badge
    // signals the shown image is momentarily stale.
    placeholderData: keepPreviousData,
    queryFn: async ({ signal }) => {
      const res = await fetch(api.editPreviewUrl(safe, rid, dRecipe, bust), { signal });
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
    queryFn: ({ signal }) => api.getHistogram(safe, rid, dRecipe, signal),
    enabled: !!opsSchema.data && seeded,
  });
  // Data-driven black/white points for the selected Levels op, measured from the
  // display-space image *entering* that op (all prior ops applied), so a beginner
  // gets a safe auto-levels to nudge instead of hand-guessing. Enabled only when a
  // Levels op is selected; keyed on the debounced recipe + uid so it refreshes as
  // upstream ops change.
  const levelsSelUid = ops.find((o) => o.uid === selected && o.id === "tone.levels")?.uid;
  const levels = useQuery({
    queryKey: ["levels-suggestion", safe, rid, dKey, levelsSelUid],
    queryFn: () => api.levelsSuggestion(safe, rid, dRecipe, levelsSelUid!),
    enabled: !!opsSchema.data && !saved.isLoading && !!levelsSelUid,
    staleTime: 30_000,
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
    queryFn: async ({ signal }) => {
      const res = await fetch(api.editPreviewUrl(safe, rid, { ops: [], base_run_id: rid }), { signal });
      if (!res.ok) throw new Error("base preview failed");
      return URL.createObjectURL(await res.blob());
    },
  });
  useEffect(() => {
    const u = basePreview.data;
    return () => { if (u) URL.revokeObjectURL(u); };
  }, [basePreview.data]);

  // Star-mask overlay: lazily fetch the soft mask that gates the star ops so the
  // user can see what the editor treats as stars vs background/nebula. When a star
  // op is selected, size the overlay to *its* star size (reduce → 2× size,
  // boost-nebula → size) so tuning "Star size" moves the overlay to match what the
  // op actually gates — otherwise it's frozen at the endpoint's default 4 px.
  const [showMask, setShowMask] = useState(false);
  const maskSizePx = starMaskSizePx(ops.find((o) => o.uid === selected));
  const maskPreview = useQuery({
    queryKey: ["edit-mask", safe, rid, maskSizePx ?? "default"],
    enabled: showMask && !!opsSchema.data && !saved.isLoading,
    queryFn: async ({ signal }) => {
      const res = await fetch(api.editStarMaskUrl(safe, rid, maskSizePx), { signal });
      if (!res.ok) throw new Error("star mask preview failed");
      return URL.createObjectURL(await res.blob());
    },
  });
  useEffect(() => {
    const u = maskPreview.data;
    return () => { if (u) URL.revokeObjectURL(u); };
  }, [maskPreview.data]);

  // Coverage-map overlay: on a mosaic, show the per-pixel frame coverage (white =
  // most frames overlapped, black = uncovered ragged edges/gaps) so the user can
  // see what the "Trim border" and "Coverage leveling" tools are acting on.
  const [showCoverage, setShowCoverage] = useState(false);
  const coveragePreview = useQuery({
    queryKey: ["edit-coverage", safe, rid],
    enabled: showCoverage && !!opsSchema.data && !saved.isLoading,
    queryFn: async ({ signal }) => {
      const res = await fetch(api.editCoverageMapUrl(safe, rid), { signal });
      if (!res.ok) throw new Error("coverage map failed");
      return URL.createObjectURL(await res.blob());
    },
  });
  useEffect(() => {
    const u = coveragePreview.data;
    return () => { if (u) URL.revokeObjectURL(u); };
  }, [coveragePreview.data]);

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
    queryFn: async ({ signal }) => {
      const withoutRecipe: Recipe = {
        ops: dRecipe.ops.map((o) => (o.uid === selected ? { ...o, enabled: false } : o)),
        base_run_id: rid,
      };
      const res = await fetch(api.editPreviewUrl(safe, rid, withoutRecipe, bust), { signal });
      if (!res.ok) throw new Error("compare render failed");
      return URL.createObjectURL(await res.blob());
    },
  });
  useEffect(() => {
    const u = withoutOpPreview.data;
    return () => { if (u) URL.revokeObjectURL(u); };
  }, [withoutOpPreview.data]);

  // The active overlay (if any) and its query, so the shown image, its caption,
  // and any error all come from the *same* source. Previously a failed overlay
  // fetch silently fell back to the edited preview while the caption still read
  // "Star mask"/"Original"/etc — so the user A/B'd the edited image against
  // itself with no error. Precedence mirrors the toggle order below.
  const overlay = showCoverage
    ? { q: coveragePreview, label: "Coverage map" }
    : showMask
      ? { q: maskPreview, label: "Star mask" }
      : showBase
        ? { q: basePreview, label: "Original" }
        : soloActive
          ? { q: withoutOpPreview, label: "without-op comparison" }
          : null;

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
      setAutoValues(autoValueSentence(built));
      setAutoKey(JSON.stringify(built));
      notifications.show({ message: "Auto-process applied — tweak from here", color: "violet" });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const exportRun = useMutation({
    mutationFn: () => api.exportRun(safe, rid, recipe, outputName.trim() || `${safe}_edit`, tiffMode),
    onSuccess: ({ job_id }) => {
      // Stay in the editor (don't bounce to Jobs); the navbar job badge tracks it.
      notifications.show({
        message: "Export running — the new image will appear in History when done.",
        color: "violet",
      });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      // Poll the job in the background purely to surface any ops that failed on the
      // full-res data (dropped best-effort, so the export look changed silently).
      void pollJobForOpErrors(job_id);
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  // Watch an export/render job to completion and warn if any op was dropped on the
  // full-res data. Best-effort and non-blocking; failures to poll are ignored.
  const pollJobForOpErrors = async (jobId: string) => {
    try {
      for (;;) {
        const j = await api.getJob(jobId);
        if (["error", "cancelled", "interrupted"].includes(j.state)) return;
        if (j.state === "done") {
          const msg = opErrorsMessage(j.result?.op_errors);
          if (msg) notifications.show({ message: msg, color: "orange", autoClose: 10000 });
          return;
        }
        await new Promise((r) => setTimeout(r, 800));
      }
    } catch {
      /* advisory only — never surface a polling error */
    }
  };

  // Live progress of the full-res PNG render, shown under the button while it
  // polls (the slowest editor action — a bare spinner reads as "stuck").
  const [pngProgress, setPngProgress] = useState<string | null>(null);
  const downloadPng = useMutation({
    mutationFn: async () => {
      setPngProgress("Rendering…");
      const { job_id } = await api.exportPng(safe, rid, recipe);
      // Full-res render can be slow on mosaics — poll the job to completion.
      for (;;) {
        const j = await api.getJob(job_id);
        if (j.state === "done") return { jobId: job_id, opErrors: opErrorsMessage(j.result?.op_errors) };
        if (["error", "cancelled", "interrupted"].includes(j.state)) {
          throw new Error(j.error || "PNG render failed");
        }
        setPngProgress(pngProgressLabel(j));
        await new Promise((r) => setTimeout(r, 500));
      }
    },
    onSuccess: ({ jobId, opErrors }) => {
      const a = document.createElement("a");
      a.href = api.editPngUrl(safe, rid, jobId);
      document.body.appendChild(a);
      a.click();
      a.remove();
      notifications.show({ message: "Full-resolution PNG ready", color: "teal" });
      if (opErrors) notifications.show({ message: opErrors, color: "orange", autoClose: 10000 });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
    onSettled: () => setPngProgress(null),
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
  // Two enabled Stretch ops compound: the second re-stretches display-space data
  // and washes the image out. Flag it and offer a one-click "disable the extras".
  const extraStretchUids = extraEnabledStretchUids(ops, specs);
  const disableExtraStretches = () =>
    setOps((p) => p.map((o) =>
      extraStretchUids.includes(o.uid) ? { ...o, enabled: false } : o));
  // A Levels op with its white point at or below its black point collapses the
  // range: the engine treats it as identity (does nothing), which is confusing.
  // Flag it and offer a one-click reset of black/white to the full 0..1 range.
  const degenerateLevels = degenerateLevelsUids(ops);
  const resetDegenerateLevels = () =>
    setOps((p) => p.map((o) =>
      degenerateLevels.includes(o.uid)
        ? { ...o, params: { ...o.params, black: 0, white: 1 } } : o));
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

  // Map every op that carries a data-driven suggestion to (param, value), so the
  // per-op "From your data" buttons can be applied across the whole pipeline in
  // one click. Only present, still-diverging ops are counted/changed.
  const dataDrivenSuggestions = useMemo(() => {
    const m: Record<string, OpSuggestion> = {};
    if (psf.data?.psf_sigma != null) m["detail.deconvolve"] = { param: "psf_sigma", value: psf.data.psf_sigma };
    if (denoise.data?.strength != null) m["detail.denoise"] = { param: "strength", value: denoise.data.strength };
    if (sharpen.data?.radius != null) m["detail.sharpen"] = { param: "radius", value: sharpen.data.radius };
    if (starSize.data?.size != null) m["stars.reduce"] = { param: "size", value: starSize.data.size };
    return m;
  }, [psf.data, denoise.data, sharpen.data, starSize.data]);
  const nDataDriven = countDataDrivenDefaults(ops, dataDrivenSuggestions);
  const applyDataDefaults = () =>
    setOps((p) => applyDataDrivenDefaults(p, dataDrivenSuggestions));

  // The trim-border crop is only offered when this run is a mosaic and a
  // well-covered rectangle worth cropping to was found.
  const trimCrop = trim.data?.is_mosaic ? trim.data.crop : null;
  // Show the proposed crop as a dashed outline on the preview first (a
  // lower-commitment step than applying immediately), with an explicit "Apply".
  const [trimPreview, setTrimPreview] = useState(false);
  // During trim preview the coverage overlay is only a backdrop for the proposed
  // crop rectangle, so keep the old fall-back there (and don't let a coverage
  // failure block the crop UI); for a genuine A/B overlay, surface the error.
  const overlayError = overlay?.q.isError && !trimPreview ? overlay : null;
  // No silent fall-back to the edited preview for A/B overlays: while an overlay
  // is on we show only that overlay's own data (a loader while it loads, an error
  // if it fails) so the caption never mislabels the edited image as the overlay.
  const shownSrc = overlay
    ? (overlay.q.data ?? (trimPreview ? preview.data : undefined))
    : preview.data;
  // Entering trim preview auto-shows the coverage heatmap so the proposed crop is
  // drawn over exactly what it's addressing — you can see it lands on the
  // well-covered interior. Remember the prior overlay state so Cancel/Apply
  // restores it (null = we didn't change it, e.g. the histogram isn't a mosaic).
  const [coverageBeforeTrim, setCoverageBeforeTrim] = useState<boolean | null>(null);
  const enterTrimPreview = () => {
    setTrimPreview(true);
    if (hist.data?.is_mosaic) {
      setCoverageBeforeTrim(showCoverage);
      setShowCoverage(true);
      setShowMask(false);
      setShowBase(false);
      setSoloExclude(false);
    }
  };
  const restoreCoverageAfterTrim = () => {
    if (coverageBeforeTrim !== null) {
      setShowCoverage(coverageBeforeTrim);
      setCoverageBeforeTrim(null);
    }
  };
  const cancelTrim = () => {
    setTrimPreview(false);
    restoreCoverageAfterTrim();
  };
  const applyTrim = () => {
    if (!trimCrop) return;
    const next = applyTrimCrop(ops, trimCrop, specs, uid);
    setOps(() => next);
    setTrimPreview(false);
    restoreCoverageAfterTrim();
    // Select the crop op so its (adjustable) bounds are visible immediately — it's
    // a normal op the user can fine-tune or remove, not a baked-in change.
    const crop = next.find((o) => o.id === "geometry.crop");
    if (crop) setSelected(crop.uid);
    notifications.show({
      message: `Trimmed to the well-covered area (${trimKeptLabel(trimCrop)})`
        + " — adjust or remove the Crop op to undo",
      color: "violet",
    });
  };

  if (opsSchema.isLoading || saved.isLoading) {
    return <Center h={300}><Loader /></Center>;
  }

  return (
    <Stack>
      <Group justify="space-between" wrap="wrap">
        <Group gap="xs">
          <Button component={Link} to={`/targets/${safe}/history`} variant="subtle"
            leftSection={<IconArrowLeft size={16} />}>History</Button>
          <div>
            <Title order={2}>Editor — {safe}</Title>
            {measuredText ? (
              <Tooltip multiline w={260} withArrow
                label="What the editor measured from this stack — the same values behind the 'From your data' suggestion buttons.">
                <Text size="xs" c="dimmed">{measuredText}</Text>
              </Tooltip>
            ) : null}
          </div>
        </Group>
        <Group gap="xs">
          <Tooltip label="Undo (Ctrl+Z)"><ActionIcon variant="default" disabled={!canUndo}
            onClick={undo} aria-label="Undo"><IconArrowBackUp size={16} /></ActionIcon></Tooltip>
          <Tooltip label="Redo (Ctrl+Shift+Z)"><ActionIcon variant="default" disabled={!canRedo}
            onClick={redo} aria-label="Redo"><IconArrowForwardUp size={16} /></ActionIcon></Tooltip>
          <Button variant="light" color="grape" leftSection={<IconSparkles size={16} />}
            loading={auto.isPending} onClick={() => auto.mutate()}>Auto-process</Button>
          {nDataDriven > 0 ? (
            <Tooltip multiline w={240} withArrow
              label="Set the blur width, sharpen radius, denoise strength and star size of the ops in your pipeline to the values measured from your data, in one click">
              <Button variant="default" color="grape" leftSection={<IconWand size={16} />}
                onClick={applyDataDefaults}>
                Use data defaults{nDataDriven > 1 ? ` (${nDataDriven})` : ""}
              </Button>
            </Tooltip>
          ) : null}
          {trimCrop ? (
            trimPreview ? (
              <Button.Group>
                <Tooltip label="Add the Crop op for this rectangle (you can fine-tune or remove it after)">
                  <Button variant="filled" color="grape" leftSection={<IconCrop size={16} />}
                    onClick={applyTrim}>Apply crop</Button>
                </Tooltip>
                <Button variant="default" onClick={cancelTrim}>Cancel</Button>
              </Button.Group>
            ) : (
              <Tooltip multiline w={250} withArrow
                label="This is a mosaic with ragged, low-coverage edges. Preview the largest well-covered rectangle as a dashed outline over the coverage heatmap, then apply it as a Crop op you can fine-tune or remove.">
                <Button variant="default" color="grape" leftSection={<IconCrop size={16} />}
                  onClick={enterTrimPreview}>Trim border</Button>
              </Tooltip>
            )
          ) : null}
          {/* Built-in presets carry a fixed op list with generic sizes: seed their
              data-driven params (sharpen radius, star size) from this target's own
              stars, and on a mosaic prepend a Coverage-leveling pass to flatten the
              panel steps (the same pass Auto-process adds) — so a built-in preset
              lands both sized to your data and mosaic-aware. User presets are
              applied exactly as the user tuned them. */}
          <PresetMenu currentOps={ops}
            onApply={(o, source) =>
              setOps(source === "builtin"
                ? prependCoverageLeveling(
                    applyDataDrivenDefaults(o, dataDrivenSuggestions),
                    hist.data?.is_mosaic === true, specs, uid)
                : o)} />
          <Button variant="default" leftSection={<IconDeviceFloppy size={16} />}
            loading={saveRecipe.isPending} onClick={() => saveRecipe.mutate()}>Save</Button>
        </Group>
      </Group>

      <Grid>
        {/* Preview + histogram */}
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Paper withBorder p="xs">
            <div style={{ position: "relative", background: "#000", borderRadius: 8,
              minHeight: 220, overflow: "hidden" }}>
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
              ) : overlayError ? (
                <Alert color="red" icon={<IconAlertTriangle size={16} />} m="md">
                  The {overlayError.label} overlay failed to load
                  {(overlayError.q.error as Error)?.message
                    ? `: ${(overlayError.q.error as Error).message}` : "."}
                  <div>
                    <Button size="xs" variant="light" color="red" mt="xs"
                      leftSection={<IconRefresh size={14} />}
                      onClick={() => overlayError.q.refetch()}>
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
              {overlay && !overlayError && !trimPreview ? (
                <Text size="xs" c="white" style={{ position: "absolute", left: 12, top: 10,
                  background: "rgba(0,0,0,0.6)", padding: "2px 8px", borderRadius: 4 }}>
                  {showCoverage
                    ? (hasEnabledGeometryOp(ops)
                        ? "Coverage map — shown for the uncropped frame"
                        : "Coverage map")
                    : showMask ? "Star mask" : showBase ? "Original"
                    : `Without: ${specs[selForSolo!.id]?.label ?? selForSolo!.id}`}
                </Text>
              ) : null}
              {/* Proposed "Trim border" crop, drawn as a dashed outline over the
                  preview so the user sees exactly what would be kept before it's
                  applied. Fractional bounds map straight to image-space percentages
                  (the preview fills the container width, so this lines up). */}
              {trimPreview && trimCrop && shownSrc ? (
                <>
                  <div aria-label="proposed crop" style={{ position: "absolute",
                    ...trimRectStyle(trimCrop), boxSizing: "border-box",
                    border: "2px dashed #f0e", pointerEvents: "none",
                    outline: "9999px solid rgba(0,0,0,0.35)" }} />
                  <Text size="xs" c="white" style={{ position: "absolute", left: 12, top: 10,
                    background: "rgba(0,0,0,0.6)", padding: "2px 8px", borderRadius: 4 }}>
                    Proposed crop{showCoverage ? " over coverage" : ""} — {trimKeptLabel(trimCrop)}
                  </Text>
                </>
              ) : null}
              {/* Coverage heatmap legend: the overlay is a viridis map (dark blue =
                  fewest frames → yellow = most), so a small gradient bar with a
                  "fewer ↔ more frames" caption makes the gradient legible. */}
              {showCoverage && coveragePreview.data ? (
                <Group gap={6} align="center" style={{ position: "absolute", right: 12, bottom: 10,
                  background: "rgba(0,0,0,0.6)", padding: "3px 8px", borderRadius: 4 }}>
                  <Text size="xs" c="white">fewer</Text>
                  <div style={{ width: 72, height: 8, borderRadius: 2,
                    background: "linear-gradient(to right, rgb(68,1,84), rgb(49,104,142), rgb(31,158,137), rgb(110,206,88), rgb(253,231,37))" }} />
                  <Text size="xs" c="white">more frames</Text>
                </Group>
              ) : null}
              {/* While a superseded render is being replaced (the older result is
                  aborted server-side), tell the user the shown image is stale and
                  a fresh render is on the way — so a laggy heavy op doesn't read as
                  "nothing happened". Only when an image is already showing. */}
              {preview.isFetching && shownSrc && !preview.isError ? (
                <Group gap={6} style={{ position: "absolute", left: 12, bottom: 10,
                  background: "rgba(0,0,0,0.6)", padding: "2px 8px", borderRadius: 4 }}>
                  <Loader size={12} color="gray" />
                  <Text size="xs" c="white">Updating…</Text>
                </Group>
              ) : null}
              <Group gap={6} style={{ position: "absolute", right: 8, top: 8 }}>
                {hist.data?.is_mosaic ? (
                  <Tooltip multiline w={230} withArrow
                    label="Show this mosaic's frame-coverage map as a colour heatmap: yellow where the most frames overlap, dark blue at the ragged, uncovered edges. This is what 'Trim border' and 'Coverage leveling' act on.">
                    <Button size="xs" variant={showCoverage ? "filled" : "default"}
                      color="grape"
                      disabled={!preview.data}
                      loading={showCoverage && coveragePreview.isLoading}
                      onClick={() => setShowCoverage((s) => {
                        if (!s) { setShowMask(false); setShowBase(false); setSoloExclude(false); }
                        return !s;
                      })}>
                      {showCoverage ? "Hide coverage" : "Coverage"}
                    </Button>
                  </Tooltip>
                ) : null}
                <Tooltip label="Show the soft mask that gates star ops (white = treated as a star)">
                  <Button size="xs" variant={showMask ? "filled" : "default"}
                    color="grape"
                    disabled={!preview.data}
                    loading={showMask && maskPreview.isLoading}
                    onClick={() => setShowMask((s) => {
                      if (!s) { setShowBase(false); setSoloExclude(false); setShowCoverage(false); }
                      return !s;
                    })}>
                    {showMask ? "Hide mask" : "Star mask"}
                  </Button>
                </Tooltip>
                <Button size="xs" variant={showBase ? "filled" : "default"}
                  disabled={!preview.data || showMask || showCoverage}
                  onClick={() => setShowBase((s) => { if (!s) setSoloExclude(false); return !s; })}>
                  {showBase ? "Edited" : "Compare"}
                </Button>
                <Button size="xs" variant="default" leftSection={<IconRefresh size={14} />}
                  loading={preview.isFetching} onClick={refreshPreview}>Refresh</Button>
                <Button size="xs" variant="default" leftSection={<IconZoomScan size={14} />}
                  disabled={!shownSrc} onClick={() => setLightbox(true)}>Zoom</Button>
              </Group>
            </div>
            <Histogram data={hist.data}
              guides={levelsHistGuides(selectedOp,
                levels.data?.black != null && levels.data?.white != null
                  ? { black: levels.data.black, white: levels.data.white } : null)} />
            {selectedOp?.id === "tone.levels" ? (
              <Text size="xs" c="dimmed" mt={4}>
                <b>B</b>/<b>W</b> mark your black &amp; white points on the histogram
                {levels.data?.black != null ? "; the dashed blue lines are the suggested points" : ""}.
              </Text>
            ) : null}
            {previewScaleCaption(hist.data) ? (
              <Text size="xs" c="dimmed" mt={4}>
                {previewScaleCaption(hist.data)}
              </Text>
            ) : null}
            {/* Over-stretching blows out star cores (a spike at pure white) or
                crushes the sky (a spike at pure black), losing detail on export.
                Surface it from the live histogram so a beginner eases off before
                baking in the clip. Advisory only — changes nothing. */}
            {clippingCaption(hist.data) ? (
              <Group gap={6} wrap="nowrap" align="flex-start" mt={4}>
                <IconAlertTriangle size={14} color="var(--mantine-color-orange-6)"
                  style={{ flexShrink: 0, marginTop: 2 }} />
                <Text size="xs" c="orange.6">{clippingCaption(hist.data)}</Text>
              </Group>
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
                        <Group gap={6} wrap="nowrap">
                          <Text size="sm">{s.label}</Text>
                          {s.heavy ? <SlowPreviewChip /> : null}
                        </Group>
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
                          <Group gap={6} wrap="nowrap">
                            <Text size="sm">{s.label}</Text>
                            {s.heavy ? <SlowPreviewChip /> : null}
                          </Group>
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
                onClose={() => { setAutoSummary(null); setAutoValues(null); }}>
                <Text size="xs">{autoSummary}</Text>
                {autoValues ? (
                  <Text size="xs" mt={4}>{autoValues}</Text>
                ) : null}
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
              {extraStretchUids.length > 0 ? (
                <Alert color="orange" variant="light" py={8} mt="xs"
                  icon={<IconAlertTriangle size={16} />}>
                  <Text size="xs" mb={6}>
                    More than one <b>Stretch</b> is enabled. Stretches compound — the
                    second one re-stretches already-stretched data and washes the image
                    out (flat or dark). Keep a single Stretch and tune <i>that</i> one.
                  </Text>
                  <Button size="compact-xs" variant="light" color="orange"
                    onClick={disableExtraStretches}>
                    Disable the extra stretch{extraStretchUids.length > 1 ? "es" : ""}
                  </Button>
                </Alert>
              ) : null}
              {degenerateLevels.length > 0 ? (
                <Alert color="orange" variant="light" py={8} mt="xs"
                  icon={<IconAlertTriangle size={16} />}>
                  <Text size="xs" mb={6}>
                    A <b>Levels</b> op has its white point at or below its black point,
                    so its range is empty — it does nothing. Reset the black and white
                    points to spread across the full range again.
                  </Text>
                  <Button size="compact-xs" variant="light" color="orange"
                    onClick={resetDegenerateLevels}>
                    Reset the black &amp; white points
                  </Button>
                </Alert>
              ) : null}
            </Paper>

            {selectedOp && specs[selectedOp.id] ? (
              <Paper withBorder p="sm">
                <Group justify="space-between" wrap="nowrap" mb={6}>
                  <Text fw={600} size="sm">{specs[selectedOp.id].label}</Text>
                  <Group gap="xs" wrap="nowrap">
                    {/* One-click "Auto levels" sets the black and white points
                        (and the midtone gamma, when a lift is suggested) from the
                        image's own histogram at once, so the common case is a
                        single click (the per-param "From your image" buttons stay
                        for fine control). */}
                    {selectedOp.id === "tone.levels"
                      && levels.data?.black != null && levels.data?.white != null ? (
                      <Tooltip
                        label={"Set the black and white points"
                          + (levels.data.gamma != null ? " and midtone brightness" : "")
                          + " from this image's histogram"}
                        multiline w={220} withArrow>
                        <Button size="compact-xs" variant="light" color="blue"
                          onClick={() => setParams(selectedOp.uid, {
                            ...selectedOp.params,
                            black: levels.data!.black,
                            white: levels.data!.white,
                            ...(levels.data!.gamma != null ? { gamma: levels.data!.gamma } : {}),
                          })}>
                          Auto levels ({levels.data.black}–{levels.data.white})
                        </Button>
                      </Tooltip>
                    ) : null}
                    {/* Escape hatch symmetric with "Auto levels": one click sets
                        the black/white/gamma points back to their neutral identity
                        so an over-dragged Levels op is easy to undo. Dimmed when
                        already neutral. */}
                    {selectedOp.id === "tone.levels" ? (
                      <Tooltip
                        label="Reset the black, white and midtone points to neutral (no tonal change)"
                        multiline w={220} withArrow>
                        <Button size="compact-xs" variant="default"
                          disabled={levelsAtIdentity(selectedOp.params)}
                          onClick={() => setParams(selectedOp.uid,
                            resetLevelsPoints(selectedOp.params))}>
                          Reset points
                        </Button>
                      </Tooltip>
                    ) : null}
                    {selectedOp.enabled ? (
                      <Tooltip
                        label="Preview the image with only this op bypassed, to see just its effect"
                        multiline w={220} withArrow>
                        <Button size="compact-xs"
                          variant={soloActive ? "filled" : "default"} color="grape"
                          loading={soloActive && withoutOpPreview.isLoading}
                          disabled={!preview.data}
                          onClick={() => setSoloExclude((s) => {
                            if (!s) { setShowBase(false); setShowMask(false); setShowCoverage(false); }
                            return !s;
                          })}>
                          {soloActive ? "Showing without" : "Without this op"}
                        </Button>
                      </Tooltip>
                    ) : null}
                  </Group>
                </Group>
                {specs[selectedOp.id].help ? (
                  <Text size="xs" c="dimmed" mb="xs">{specs[selectedOp.id].help}</Text>
                ) : null}
                {/* Coverage leveling only equalises panels on a mosaic; on a
                    single-field stack (uniform coverage) it's a deliberate no-op,
                    so tell the user rather than let the control silently do nothing. */}
                {selectedOp.id === "background.level_coverage" && hist.data?.is_mosaic === false ? (
                  <Alert color="gray" variant="light" py={6} mb="xs"
                    icon={<IconInfoCircle size={16} />}>
                    <Text size="xs">
                      No effect on this stack — it's a single-field image with even
                      coverage. This op equalises the sky across the panels of a
                      <b> mosaic</b>, where frames overlap unevenly.
                    </Text>
                  </Alert>
                ) : null}
                {specs[selectedOp.id].heavy && selectedOp.enabled ? (
                  <Alert color="grape" variant="light" py={6} mb="xs"
                    icon={<IconInfoCircle size={16} />}>
                    <Text size="xs">
                      This op is slow to render, so the live preview waits for a short
                      pause after you change a slider before updating — it's not stuck.
                      The full-resolution result appears when you Export.
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
                            : selectedOp.id === "tone.levels"
                              && levels.data?.black != null && levels.data?.white != null
                              ? {
                                // Each button sets only its own point, so label it
                                // with just that value (not both) to match what it does.
                                black: {
                                  value: levels.data.black,
                                  label: `From your image (black ${levels.data.black})`,
                                },
                                white: {
                                  value: levels.data.white,
                                  label: `From your image (white ${levels.data.white})`,
                                },
                                // A midtone lift is only suggested when one meaningfully
                                // helps, so the gamma button appears conditionally.
                                ...(levels.data.gamma != null ? {
                                  gamma: {
                                    value: levels.data.gamma,
                                    label: `From your image (midtones ${levels.data.gamma})`,
                                  },
                                } : {}),
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
                <Select w={150} value={tiffMode} allowDeselect={false}
                  label={<HintLabel label="TIFF"
                    hint="The exported .tiff (and its History thumbnail) saves the
                      edited image exactly as shown here. It's already display-ready,
                      so both options produce that same result; for the underlying
                      unstretched data, use the separate FITS output." />}
                  data={[{ value: "linear", label: "Linear" },
                         { value: "autostretch", label: "Auto-stretched" }]}
                  onChange={(v) => setTiffMode(v ?? "linear")} />
              </Group>
              <Button mt="sm" fullWidth leftSection={<IconDownload size={16} />}
                loading={exportRun.isPending} onClick={() => exportRun.mutate()}>
                Export as new image
              </Button>
              <Button mt="xs" fullWidth variant="light" leftSection={<IconPhotoDown size={16} />}
                loading={downloadPng.isPending} onClick={() => downloadPng.mutate()}>
                Download full-res PNG
              </Button>
              {downloadPng.isPending && pngProgress ? (
                <Text size="xs" c="dimmed" ta="center" mt={4}>{pngProgress}</Text>
              ) : null}
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
