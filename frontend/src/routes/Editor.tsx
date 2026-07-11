import {
  ActionIcon, Alert, Badge, Button, Center, Grid, Group, Loader, Menu, Paper, Select, Stack, Text,
  TextInput, Title, Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import {
  IconAlertTriangle, IconArrowBackUp, IconArrowForwardUp, IconArrowLeft, IconChevronDown,
  IconChevronUp, IconCrop, IconDeviceFloppy, IconDownload, IconHistory, IconInfoCircle,
  IconPhotoDown, IconPlus, IconRefresh, IconSparkles, IconStar, IconWand, IconZoomScan,
} from "@tabler/icons-react";
import { notifications } from "@mantine/notifications";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type EditOp, type OpInstance, type Recipe } from "../api/client";
import { useUndoable } from "../hooks/useUndoable";
import { ImageLightbox } from "../components/ImageLightbox";
import { Histogram } from "../components/editor/Histogram";
import { tonalHistGuides } from "../components/editor/tonalGuides";
import { OpList } from "../components/editor/OpList";
import { degenerateLevelsUids, extraEnabledStretchUids, hasEnabledStretch, insertOnCorrectSide, moveToCorrectSide }
  from "../components/editor/stageConflicts";
import { autoCauseSentence, autoSummarySentence, autoValueSentence, presetSuggestionSentence } from "../components/editor/autoSummary";
import { applyDataDrivenDefaults, countDataDrivenDefaults, type OpSuggestion }
  from "../components/editor/dataDrivenDefaults";
import { deconvUnderstatesCaption } from "../components/editor/deconvPreview";
import { starReduceOverstatesCaption } from "../components/editor/starReducePreview";
import { canNeutraliseSkyCast, neutraliseBackgroundOps, skyCastCaption }
  from "../components/editor/skyCast";
import { autoColorCalCaption } from "../components/editor/colorCal";
import { previewScaleCaption } from "../components/editor/previewScale";
import { prependCoverageLeveling } from "../components/editor/coverageLeveling";
import { applyTrimCrop, trimRectStyle, trimKeptLabel, geometryOpsKey, previewBoxStyle,
  cropCoveragePct, removeCropOps }
  from "../components/editor/mosaicTrim";
import { splitFraction, splitClipLeft, splitLeftPct, lookCompareOps, reshapesFrame }
  from "../components/editor/splitCompare";
import { LookComparePicker, type LookChoice } from "../components/editor/LookComparePicker";
import { pngProgressLabel } from "../components/editor/pngProgress";
import { opErrorsMessage } from "../components/editor/opErrors";
import { clippingCaption } from "../components/editor/clipping";
import { previewDebounceMs } from "../components/editor/previewDebounce";
import { starMaskSizePx } from "../components/editor/starMaskSize";
import { levelsAtIdentity, resetLevelsPoints } from "../components/editor/levelsReset";
import { curvePointsMatch, isIdentityCurve } from "../components/editor/curveMatch";
import { coalesceFwhm, measuredContextText } from "../components/editor/measuredContext";
import { calibrationSummaryText } from "../components/calibrationSummary";
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

/** Normalise a preset's (or the Auto recipe's) loosely-typed op list into full
 * `OpInstance`s, minting a uid and defaulting `enabled` where absent — so a look
 * can be sized/rendered through the same helpers as the working recipe. */
function toOpInstances(
  ops: { id: string; params: Record<string, unknown>; enabled?: boolean; uid?: string }[],
): OpInstance[] {
  return ops.map((o) => ({ uid: o.uid ?? uid(), id: o.id, enabled: o.enabled ?? true, params: o.params }));
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
  // Carry-over: the newest *other* run's saved edit, offered as a one-click seed
  // when *this* run has no saved recipe yet — so re-stacking a multi-night target
  // keeps the look the user dialled in, instead of reopening on the flat default.
  // Fetched only when the saved recipe is empty (never nags a run that has its own
  // edit); applying it is an explicit, undoable step and isn't persisted unless
  // the user Saves. The ops are server-validated on load, so a stale op can't 500.
  const savedIsEmpty = !!saved.data && (saved.data.ops?.length ?? 0) === 0;
  const prevRecipe = useQuery({
    queryKey: ["previous-recipe", safe, rid],
    queryFn: () => api.previousRecipe(safe, rid),
    enabled: !!opsSchema.data && savedIsEmpty,
    staleTime: 30_000,
  });
  // The user's library-wide default recipe ("my house style"), set via the Presets
  // menu. Offered as a one-click seed on any run with no saved edit yet, so a repeat
  // imager's default look is one click away on every new target. Off until they set
  // one (count 0 → the button simply doesn't appear). Server-validated on load.
  const defaultRecipe = useQuery({
    queryKey: ["default-recipe"],
    queryFn: () => api.getDefaultRecipe(),
    enabled: !!opsSchema.data && savedIsEmpty,
    staleTime: 30_000,
  });
  // The "what Auto did (and why)" note a *background* job stamped when it auto-edited
  // this run (Process-target / reprocess / watcher auto-stack — v0.92.0). The
  // Process-target deep-link lands the user straight in the editor on a recipe they
  // didn't build, so without this the editor opens with a non-empty pipeline and no
  // explanation. Fetched only when the run has a saved (non-empty) recipe — a note is
  // never stored for an empty or hand-built one — and surfaced read-only until the
  // user hand-edits (see `pristine` below), so a recipe the user tweaks never keeps a
  // stale explanation. Best-effort: null on an older backend without the endpoint.
  const autoNote = useQuery({
    queryKey: ["auto-note", safe, rid],
    queryFn: () => api.autoNote(safe, rid).catch(() => ({ note: null })),
    enabled: !!saved.data && !savedIsEmpty,
    staleTime: 30_000,
  });
  // The run's provenance cards, read only to tell the walk-away user whether
  // their hands-off result was calibrated (v0.103.7 surfaced this on the History
  // Info panel, but the Process-target deep-link actually lands them in the
  // editor). Fetched under the same condition as the auto-note — a run a
  // background job auto-edited — and used solely for the positive "Calibrated
  // with your master dark + flat" line inside that note. Best-effort: null on an
  // older backend / missing FITS, in which case the line is simply omitted.
  const runInfo = useQuery({
    queryKey: ["stack-run-info", safe, rid],
    queryFn: () => api.stackRunInfo(safe, rid).catch(() => null),
    enabled: !!saved.data && !savedIsEmpty,
    staleTime: 30_000,
  });
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
  // The causal inputs Auto measured from the image (sky, star size, noise, mosaic
  // trim) — the "why" behind the picks, shown above the values so the note reads
  // cause → effect. Best-effort: null on an older backend without the endpoint.
  const [autoCause, setAutoCause] = useState<string | null>(null);
  const [autoKey, setAutoKey] = useState<string | null>(null);

  // Seed ops from the saved recipe exactly once per run. Re-seeding on every
  // `saved.data` change would wipe undo/redo history and clobber edits made while
  // a save was in flight (saving invalidates the recipe query, which refetches a
  // structurally-different snapshot), so we gate on a per-run `seeded` flag. The
  // gate also holds the live preview until the recipe is loaded, so the editor
  // never flashes the un-edited image (and wastes a proxy render) on open.
  const [seeded, setSeeded] = useState(false);
  // Signature of the recipe the run opened with, captured once at seed time. The
  // background auto-edit note (`autoNote`) is shown only while the live pipeline
  // still equals this — i.e. the user hasn't hand-edited — so a note the user
  // didn't build fades the moment they change anything, and never re-appears (even
  // after a Save re-syncs `saved.data`) because this key stays frozen for the run.
  const [seedKey, setSeedKey] = useState<string | null>(null);
  useEffect(() => { setSeeded(false); setSeedKey(null); }, [rid]);
  useEffect(() => {
    if (saved.data && !seeded) {
      const ops0 = saved.data.ops ?? [];
      resetOps(ops0);
      setSeedKey(JSON.stringify(ops0));
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
      setAutoCause(null);
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
    // gcTime: 0 — these queries mint an object URL per fetch and revoke it (in the
    // effect below) the moment `data` changes. Without immediate GC, an inactive
    // blob query lingers in cache with its now-*revoked* URL string, so a later
    // undo/redo (which reproduces a prior recipe → prior query key) or re-entering
    // the editor would re-serve that dead URL and show a blank/broken preview. With
    // gcTime 0 a superseded blob query is dropped at once, so it's never re-served
    // after revocation; keepPreviousData still keeps the last good image on screen
    // while the fresh render loads (no flash).
    gcTime: 0,
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
    enabled: !!opsSchema.data,
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
  // Data-driven asinh Strength + Black point for the selected Stretch op, measured
  // from the *linear* image entering it (any prior linear ops applied). Enabled only
  // when an asinh Stretch op is selected; keyed on the debounced recipe + uid so it
  // refreshes as upstream ops change.
  const stretchSel = ops.find((o) => o.uid === selected && o.id === "tone.stretch");
  const stretchSelUid = stretchSel?.params?.mode !== "stf" ? stretchSel?.uid : undefined;
  const stretch = useQuery({
    queryKey: ["stretch-suggestion", safe, rid, dKey, stretchSelUid],
    queryFn: () => api.stretchSuggestion(safe, rid, dRecipe, stretchSelUid!),
    enabled: !!opsSchema.data && !saved.isLoading && !!stretchSelUid,
    staleTime: 30_000,
  });
  // Data-driven starting tone curve for the selected Curves op, measured from the
  // display-space image *entering* that op (all prior ops applied). Enabled only
  // when a Curves op is selected; keyed on the debounced recipe + uid so it
  // refreshes as upstream ops change.
  const curveSelUid = ops.find((o) => o.uid === selected && o.id === "tone.curves")?.uid;
  const curve = useQuery({
    queryKey: ["curve-suggestion", safe, rid, dKey, curveSelUid],
    queryFn: () => api.curveSuggestion(safe, rid, dRecipe, curveSelUid!),
    enabled: !!opsSchema.data && !saved.isLoading && !!curveSelUid,
    staleTime: 30_000,
  });
  // Recipe-aware denoise strength for the *selected* denoise op: measures the
  // linear image entering it (any prior linear ops — e.g. a background/gradient or
  // colour-balance op the Auto recipe places ahead of denoise — applied), so the
  // per-op "From your image" button reflects them instead of the bare proxy. The
  // eager `denoise` query above still feeds the recipe-independent "Your data"
  // noise chip + bulk apply; this one refines only the per-op button. Keyed on the
  // debounced recipe + uid so it refreshes as upstream ops change.
  const denoiseSelUid = ops.find((o) => o.uid === selected && o.id === "detail.denoise")?.uid;
  const denoiseOp = useQuery({
    queryKey: ["denoise-suggestion", safe, rid, dKey, denoiseSelUid],
    queryFn: () => api.denoiseSuggestion(safe, rid, dRecipe, denoiseSelUid!),
    enabled: !!opsSchema.data && !saved.isLoading && !!denoiseSelUid,
    staleTime: 30_000,
  });
  const refreshPreview = () => {
    setBust(Date.now());
    qc.invalidateQueries({ queryKey: ["edit-hist", safe, rid] });
  };

  // Before/after: lazily fetch the base (no-ops) render to compare against.
  const [showBase, setShowBase] = useState(false);
  // Split before/after: overlay the Original on the edited preview and clip it
  // with a draggable vertical divider, so the user sees exactly what an edit
  // changed in one frame (left = Original, right = edited) instead of flipping
  // the whole image with the Compare toggle. The Original image is the same
  // empty-recipe render Compare uses, so it needs `basePreview` loaded too.
  const [splitCompare, setSplitCompare] = useState(false);
  const [splitFrac, setSplitFrac] = useState(0.5);
  const [splitDragging, setSplitDragging] = useState(false);
  const previewBoxRef = useRef<HTMLDivElement>(null);
  // The "Original" is the raw stack with *only* the recipe's enabled geometry ops
  // (crop/rotate/resize) applied — not a full empty-recipe render. Reason: the
  // edited preview is reshaped by those ops, so an un-cropped Original would be a
  // different frame shape and letterbox/mis-align under the Split divider (and the
  // whole Compare would zoom out to the un-cropped frame). Sharing the edit's
  // framing keeps the divider aligned and makes Compare an honest "your processing
  // vs none" on the *same* view. With no geometry op this is exactly the old
  // empty-recipe render. Derived from the debounced recipe and keyed on just the
  // geometry ops so it only refetches when the framing actually changes.
  const baseGeometryOps = useMemo(
    () => dRecipe.ops.filter((o) => o.enabled && o.id.startsWith("geometry.")),
    [dRecipe],
  );
  const basePreview = useQuery({
    queryKey: ["edit-base", safe, rid, geometryOpsKey(dRecipe.ops)],
    gcTime: 0,  // see the preview query — blob URLs are revoked, never re-serve a dead one
    enabled: (showBase || splitCompare) && !!opsSchema.data && !saved.isLoading,
    queryFn: async ({ signal }) => {
      const res = await fetch(
        api.editPreviewUrl(safe, rid, { ops: baseGeometryOps, base_run_id: rid }), { signal });
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
  // The selected star op (if any): its uid tells the endpoint where in the pipeline
  // to stop so the mask reflects the display-space image the op actually gates on,
  // and its star size sizes the mask footprint. Both are debounced (via dKey/the
  // debounced size below) so a slider drag doesn't fire a mask render per tick.
  const starSelUid = ops.find(
    (o) => o.uid === selected && (o.id === "stars.reduce" || o.id === "stars.boost_nebula"),
  )?.uid;
  const maskSizePx = starMaskSizePx(ops.find((o) => o.uid === selected));
  const [dMaskSizePx] = useDebouncedValue(maskSizePx, debounceMs);
  const maskPreview = useQuery({
    queryKey: ["edit-mask", safe, rid, dMaskSizePx ?? "default", dKey, starSelUid ?? ""],
    gcTime: 0,  // see the preview query — blob URLs are revoked, never re-serve a dead one
    enabled: showMask && !!opsSchema.data && !saved.isLoading,
    queryFn: async ({ signal }) => {
      const res = await fetch(
        api.editStarMaskUrl(safe, rid, dMaskSizePx, dRecipe, starSelUid), { signal });
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
  // The overlay follows the recipe's enabled geometry ops (crop/rotate/resize) so
  // it tracks the reshaped preview; key on just those ops (via geometryOpsKey) so a
  // tone-op tweak doesn't refetch the coverage map, only a geometry change does.
  const geomKey = useMemo(() => geometryOpsKey(dRecipe.ops), [dRecipe]);
  const coveragePreview = useQuery({
    queryKey: ["edit-coverage", safe, rid, geomKey],
    gcTime: 0,  // see the preview query — blob URLs are revoked, never re-serve a dead one
    enabled: showCoverage && !!opsSchema.data && !saved.isLoading,
    queryFn: async ({ signal }) => {
      const res = await fetch(api.editCoverageMapUrl(safe, rid, dRecipe), { signal });
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
  // Split variant of the per-op compare: instead of swapping the whole preview to
  // "without this op", clip the without-this-op render to the left of a draggable
  // divider over the edited (with-this-op) preview — so the user drags to see
  // exactly what the *one op they're tuning* did, the per-op analogue of the
  // whole-recipe Split. Reuses the same `withoutOpPreview` render and the shared
  // `splitFrac`/divider drag machinery.
  const [soloSplit, setSoloSplit] = useState(false);
  useEffect(() => { setSoloExclude(false); setSoloSplit(false); }, [selected]);
  const selForSolo = ops.find((o) => o.uid === selected) ?? null;
  const soloActive = soloExclude && !!selForSolo && selForSolo.enabled;
  // Whether the without-op render is wanted by either per-op compare mode (full
  // swap or split), so the query fetches for both.
  const soloWanted = (soloExclude || soloSplit) && !!selForSolo && selForSolo.enabled;
  const withoutOpPreview = useQuery({
    queryKey: ["edit-without-op", safe, rid, dKey, selected, bust],
    gcTime: 0,  // see the preview query — blob URLs are revoked, never re-serve a dead one
    enabled: soloWanted && !!opsSchema.data && !saved.isLoading,
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

  // "Compare a look" split: preview another look (Auto / a built-in or saved
  // preset) as the "before" side of the divider, so the user can judge their
  // current edit against any other look in one frame without committing to it.
  // `lookSel` holds the chosen look's resolved ops + name (built-in presets are
  // sized to this target's data exactly as applying them would be); it's rendered
  // on the *current* edit's framing (see lookCompareOps) so the divider lines up.
  const [lookSplit, setLookSplit] = useState(false);
  const [lookSel, setLookSel] = useState<{ label: string; ops: OpInstance[] } | null>(null);
  const lookPreviewRecipe = useMemo<Recipe | null>(
    () => (lookSel
      ? { ops: lookCompareOps(lookSel.ops, baseGeometryOps), base_run_id: rid }
      : null),
    [lookSel, baseGeometryOps, rid],
  );
  const lookPreview = useQuery({
    queryKey: ["edit-look", safe, rid, lookSel?.label,
      lookPreviewRecipe ? JSON.stringify(lookPreviewRecipe.ops) : ""],
    gcTime: 0,  // see the preview query — blob URLs are revoked, never re-serve a dead one
    enabled: lookSplit && !!lookPreviewRecipe && !!opsSchema.data && !saved.isLoading,
    queryFn: async ({ signal }) => {
      const res = await fetch(api.editPreviewUrl(safe, rid, lookPreviewRecipe!), { signal });
      if (!res.ok) throw new Error("look preview failed");
      return URL.createObjectURL(await res.blob());
    },
  });
  useEffect(() => {
    const u = lookPreview.data;
    return () => { if (u) URL.revokeObjectURL(u); };
  }, [lookPreview.data]);

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
    // Fetch the recipe and its causal analysis together; the analysis is
    // best-effort (an older backend has no such endpoint) so it never blocks Auto.
    mutationFn: async () => {
      const [recipe, analysis] = await Promise.all([
        api.autoProcess(safe, rid),
        api.autoAnalysis(safe, rid).catch(() => null),
      ]);
      return { recipe, analysis };
    },
    onSuccess: ({ recipe, analysis }) => {
      const built = (recipe.ops ?? []).map((o) => ({ ...o, uid: o.uid || uid() }));
      setOps(built);
      setAutoSummary(autoSummarySentence(built, specs));
      setAutoValues(autoValueSentence(built));
      setAutoCause(autoCauseSentence(analysis));
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
  const setParams = (u: string, params: Record<string, unknown>, coalesceKey?: string) =>
    setOps(
      (p) => p.map((o) => (o.uid === u ? { ...o, params } : o)),
      // Namespace the coalesce key by op uid so dragging the same-named param on a
      // different op (after selecting it) starts a fresh undo step rather than
      // merging across ops.
      coalesceKey ? `${u}:${coalesceKey}` : undefined,
    );
  const fixStage = (u: string) => setOps((p) => moveToCorrectSide(p, u, specs));

  const selectedOp = ops.find((o) => o.uid === selected) ?? null;
  // Auto-contrast on the Curves op derives its curve at *render* time from the
  // image entering the op while the stored points stay a flat identity, so the
  // widget would otherwise draw a straight line that contradicts the preview.
  // When it's engaged (auto on + still identity) show the derived shape — the same
  // one `…/editor/curve-suggestion` returns — as a read-only ghost, and offer to
  // Bake it into editable points (clearing `auto`, so what you see is what you tune).
  const curveGhost = selectedOp?.id === "tone.curves"
    && selectedOp.params?.auto === true
    && isIdentityCurve(selectedOp.params?.points)
    && curve.data?.points != null && curve.data.points.length >= 2
    ? (curve.data.points as [number, number][]) : undefined;
  const bakeAutoCurve = () => {
    if (!selectedOp || !curveGhost) return;
    setParams(selectedOp.uid, { ...selectedOp.params, points: curveGhost, auto: false });
  };
  // One-click "neutralise background": append a display-space neutralise op when
  // the read-out shows a residual sky cast (and the fix will land in display space).
  // An undoable step, like the Auto-curve / trim buttons.
  const canNeutralise = canNeutraliseSkyCast(
    hist.data, ops, hasEnabledStretch(ops, specs));
  const neutraliseBackground = () =>
    setOps((p) => neutraliseBackgroundOps(p, specs, uid));
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
    // Carry each param's step so "already set" is judged with the same half-step
    // tolerance as the per-param "From your data" button — otherwise the toolbar
    // and the button disagree for a value within half a step of the suggestion.
    const step = (opId: string, param: string) =>
      specs[opId]?.params.find((p) => p.key === param)?.step ?? null;
    if (psf.data?.psf_sigma != null)
      m["detail.deconvolve"] = { param: "psf_sigma", value: psf.data.psf_sigma, step: step("detail.deconvolve", "psf_sigma") };
    if (denoise.data?.strength != null)
      m["detail.denoise"] = { param: "strength", value: denoise.data.strength, step: step("detail.denoise", "strength") };
    if (sharpen.data?.radius != null)
      m["detail.sharpen"] = { param: "radius", value: sharpen.data.radius, step: step("detail.sharpen", "radius") };
    if (starSize.data?.size != null)
      m["stars.reduce"] = { param: "size", value: starSize.data.size, step: step("stars.reduce", "size") };
    return m;
  }, [psf.data, denoise.data, sharpen.data, starSize.data, specs]);
  const nDataDriven = countDataDrivenDefaults(ops, dataDrivenSuggestions);
  const applyDataDefaults = () =>
    setOps((p) => applyDataDrivenDefaults(p, dataDrivenSuggestions));

  // Presets for the "Compare a look" picker (shares the ["presets"] cache with the
  // Presets menu, so no extra fetch).
  const lookPresets = useQuery({ queryKey: ["presets"], queryFn: api.listPresets });
  // A coarse content-classification *hint* — "this looks like a star cluster / nebula
  // / galaxy — try the matching preset?". Read-only and best-effort (an older backend
  // has no such endpoint): it never changes Auto, and `preset_id` is null when the
  // content isn't clearly one archetype, so the chip simply stays hidden then.
  const presetSuggest = useQuery({
    queryKey: ["preset-suggestion", safe, rid],
    queryFn: () => api.presetSuggestion(safe, rid).catch(() => null),
    staleTime: Infinity,
  });
  // Resolve a chosen look into concrete ops and switch on the look-compare split.
  // A built-in preset is sized to this target's data + made mosaic-aware exactly as
  // *applying* it would be (so the comparison is honest); a saved preset is used
  // verbatim; Auto is fetched fresh (the `…/editor/auto` endpoint only *returns* the
  // recipe — it never persists it, so this doesn't touch the user's saved edit).
  const pickLook = useMutation({
    mutationFn: async (choice: LookChoice): Promise<{ label: string; ops: OpInstance[] }> => {
      if (choice.kind === "auto") {
        const r = await api.autoProcess(safe, rid);
        return { label: "Auto", ops: toOpInstances(r.ops ?? []) };
      }
      const raw = toOpInstances(choice.preset.ops);
      const ops = choice.source === "builtin"
        ? prependCoverageLeveling(
            applyDataDrivenDefaults(raw, dataDrivenSuggestions),
            hist.data?.is_mosaic === true, specs, uid)
        : raw;
      return { label: choice.preset.label, ops };
    },
    onSuccess: (sel) => {
      setLookSel(sel);
      // Look-compare owns the preview box: turn off the other overlays/splits.
      setShowBase(false); setShowMask(false); setShowCoverage(false);
      setSoloExclude(false); setSoloSplit(false); setSplitCompare(false);
      setTrimPreview(false); setSplitFrac(0.5);
      setLookSplit(true);
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  // Adopt the look currently being compared as the working recipe (an undoable
  // step, not persisted until Save) — closes the compare→adopt loop so a user who
  // prefers the compared look switches to it in one click. Replaces the whole
  // pipeline, so confirm when that throws away a non-empty edit (mirrors applying
  // a preset from the Presets menu).
  const adoptLook = () => {
    if (!lookSel) return;
    if (ops.length && !window.confirm(
      `Switch to "${lookSel.label}"? This replaces your current `
      + `${ops.length}-operation edit (Undo to revert).`)) {
      return;
    }
    const next = lookSel.ops;
    setLookSplit(false);
    setOps(() => next);
    notifications.show({
      message: `Switched to "${lookSel.label}" (${next.length} step`
        + `${next.length === 1 ? "" : "s"}) — Undo to revert, Save to keep`,
      color: "violet",
    });
  };

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
  // Split before/after is its own mode: it renders over the edited preview
  // (`preview.data`, i.e. no `overlay`), so it's only live when no other overlay
  // and no trim preview owns the box.
  const splitActive = splitCompare && !overlay && !trimPreview;
  // Per-op split: only when its mode is on, the selected op is enabled, and no
  // other overlay/trim owns the box (the toggles keep these mutually exclusive,
  // but guard defensively). Shares the whole-recipe split's divider/drag state.
  const soloSplitActive = soloSplit && !!selForSolo && selForSolo.enabled
    && !overlay && !trimPreview;
  // "Compare a look" split: shows another look (Auto / a preset) as the "before"
  // side, only when a look is chosen and no other overlay/trim owns the box.
  const lookSplitActive = lookSplit && !!lookSel && !overlay && !trimPreview;
  // The split overlay's left ("before") image + labels, so one render block serves
  // the whole-recipe split (Original vs Edited), the per-op split (without-this-op
  // vs with-this-op) and the look split (a chosen look vs the current edit).
  const splitLeftSrc = splitActive
    ? basePreview.data
    : soloSplitActive ? withoutOpPreview.data
    : lookSplitActive ? lookPreview.data : undefined;
  const splitLeftLabel = soloSplitActive && selForSolo
    ? `Without ${specs[selForSolo.id]?.label ?? selForSolo.id}`
    : lookSplitActive && lookSel ? lookSel.label
    : "Original";
  const splitRightLabel = soloSplitActive ? "With" : "Edited";
  const anySplitActive = splitActive || soloSplitActive || lookSplitActive;
  // Entering trim preview auto-shows the coverage heatmap so the proposed crop is
  // drawn over exactly what it's addressing — you can see it lands on the
  // well-covered interior. Remember the prior overlay state so Cancel/Apply
  // restores it (null = we didn't change it, e.g. the histogram isn't a mosaic).
  const [coverageBeforeTrim, setCoverageBeforeTrim] = useState<boolean | null>(null);
  const enterTrimPreview = () => {
    setTrimPreview(true);
    setSplitCompare(false);
    setSoloSplit(false);
    setLookSplit(false);
    // Clear any active overlay/compare unconditionally so the proposed crop is
    // never drawn over a contradictory backdrop (e.g. the un-edited "Original")
    // with a mislabelled caption. This must run even before the heavier histogram
    // query resolves — the "Trim border" button appears as soon as the lighter
    // trim-suggestion query does, so a fast click could otherwise enter trim with
    // an overlay still on and the coverage backdrop not yet forced.
    setShowMask(false);
    setShowBase(false);
    setSoloExclude(false);
    if (hist.data?.is_mosaic) {
      // On a mosaic, auto-show the coverage heatmap so the crop is drawn over
      // exactly what it addresses; remember the prior state so Cancel/Apply
      // restores it (null = we didn't change it).
      setCoverageBeforeTrim(showCoverage);
      setShowCoverage(true);
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
  const applyPreviousRecipe = () => {
    const prev = prevRecipe.data;
    if (!prev?.ops?.length) return;
    // Replace the (empty) working recipe with a copy of the previous run's edit as
    // a single undoable step. Not persisted until the user Saves.
    setOps(() => prev.ops);
    notifications.show({
      message: `Applied your edit from the previous run (${prev.count} step`
        + `${prev.count === 1 ? "" : "s"}) — Undo to revert, Save to keep`,
      color: "violet",
    });
  };
  const applyDefaultRecipe = () => {
    const def = defaultRecipe.data;
    if (!def?.ops?.length) return;
    // Seed the (empty) working recipe from the user's saved default as a single
    // undoable step. Not persisted until the user Saves.
    setOps(() => def.ops);
    notifications.show({
      message: `Started from your default edit (${def.count} step`
        + `${def.count === 1 ? "" : "s"}) — Undo to revert, Save to keep`,
      color: "violet",
    });
  };
  // Apply the suggested built-in preset (from the classification chip) exactly as
  // the Presets menu would — sized to this target's data + made mosaic-aware — as a
  // single undoable step. Not persisted until the user Saves. No confirm needed: the
  // chip only shows on an empty pipeline, so there's no work to overwrite.
  const applySuggestedPreset = () => {
    const pid = presetSuggest.data?.preset_id;
    const preset = lookPresets.data?.builtin.find((p) => p.id === pid);
    if (!preset) return;
    const sized = prependCoverageLeveling(
      applyDataDrivenDefaults(toOpInstances(preset.ops), dataDrivenSuggestions),
      hist.data?.is_mosaic === true, specs, uid);
    setOps(() => sized);
    notifications.show({
      message: `Started from the ${preset.label} preset — Undo to revert, Save to keep`,
      color: "violet",
    });
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
                // The image box is sized to the shown image's exact content box
                // (its own aspect ratio, width-capped so the height never exceeds
                // 62vh) so overlays positioned as a percentage of it line up even
                // when a portrait frame / short window would otherwise letterbox.
                <div ref={previewBoxRef} style={{ position: "relative",
                  // Size to the *rendered* dims (post-geometry, what the preview
                  // PNG actually is) so a cropped/rotated frame fills the box
                  // instead of letterboxing inside the un-cropped aspect — which
                  // would put black bars around the trimmed preview and mis-align
                  // the Split divider / trim rectangle. Fall back to the raw proxy
                  // dims on an older backend that doesn't send render_* yet.
                  ...previewBoxStyle(hist.data?.render_width ?? hist.data?.proxy_width,
                                     hist.data?.render_height ?? hist.data?.proxy_height) }}>
                  <img src={shownSrc} alt="preview"
                    style={{ display: "block", width: "100%", height: "100%",
                             objectFit: "contain", cursor: "zoom-in" }}
                    onClick={() => setLightbox(true)} />
                  {/* Split before/after: the "before" image (the Original for the
                      whole-recipe split, or the without-this-op render for the
                      per-op split) clipped to the left of a draggable divider, over
                      the edited/with-op image below. Only when a split mode is on and
                      both renders are ready; sits inside the image box so it lines up
                      under objectFit:contain, and never during a trim preview (that
                      owns the box). */}
                  {anySplitActive && splitLeftSrc ? (
                    <>
                      <img src={splitLeftSrc} alt="original"
                        style={{ position: "absolute", inset: 0, width: "100%",
                                 height: "100%", objectFit: "contain",
                                 clipPath: splitClipLeft(splitFrac),
                                 pointerEvents: "none" }} />
                      <div aria-label="split divider"
                        onPointerDown={(e) => {
                          e.currentTarget.setPointerCapture(e.pointerId);
                          setSplitDragging(true);
                        }}
                        onPointerMove={(e) => {
                          if (!splitDragging) return;
                          const r = previewBoxRef.current?.getBoundingClientRect();
                          if (r) setSplitFrac(splitFraction(e.clientX, r.left, r.width));
                        }}
                        onPointerUp={(e) => {
                          setSplitDragging(false);
                          try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* ignore */ }
                        }}
                        style={{ position: "absolute", top: 0, bottom: 0,
                                 left: splitLeftPct(splitFrac), width: 24,
                                 transform: "translateX(-50%)", cursor: "ew-resize",
                                 touchAction: "none", zIndex: 3 }}>
                        <div style={{ position: "absolute", top: 0, bottom: 0, left: "50%",
                          width: 2, transform: "translateX(-50%)",
                          background: "rgba(255,255,255,0.85)",
                          boxShadow: "0 0 3px rgba(0,0,0,0.7)" }} />
                        <div style={{ position: "absolute", top: "50%", left: "50%",
                          width: 18, height: 18, borderRadius: "50%",
                          transform: "translate(-50%,-50%)",
                          background: "rgba(255,255,255,0.9)",
                          boxShadow: "0 0 3px rgba(0,0,0,0.7)" }} />
                      </div>
                      <Text size="xs" c="white" style={{ position: "absolute", left: 12, top: 10,
                        background: "rgba(0,0,0,0.6)", padding: "2px 8px", borderRadius: 4 }}>
                        {splitLeftLabel}</Text>
                      <Text size="xs" c="white" style={{ position: "absolute", right: 12, top: 10,
                        background: "rgba(0,0,0,0.6)", padding: "2px 8px", borderRadius: 4 }}>
                        {splitRightLabel}</Text>
                    </>
                  ) : null}
                  {/* Proposed "Trim border" crop, drawn as a dashed outline over
                      the image so the user sees exactly what would be kept before
                      it's applied. Inside the image box so it stays aligned when
                      the preview is letterboxed. */}
                  {trimPreview && trimCrop ? (
                    <div aria-label="proposed crop" style={{ position: "absolute",
                      ...trimRectStyle(trimCrop), boxSizing: "border-box",
                      border: "2px dashed #f0e", pointerEvents: "none",
                      outline: "9999px solid rgba(0,0,0,0.35)" }} />
                  ) : null}
                </div>
              ) : (
                <Center h={240}><Loader /></Center>
              )}
              {overlay && !overlayError && !trimPreview ? (
                <Text size="xs" c="white" style={{ position: "absolute", left: 12, top: 10,
                  background: "rgba(0,0,0,0.6)", padding: "2px 8px", borderRadius: 4 }}>
                  {showCoverage
                    ? "Coverage map"
                    : showMask ? "Star mask" : showBase ? "Original"
                    : `Without: ${specs[selForSolo!.id]?.label ?? selForSolo!.id}`}
                </Text>
              ) : null}
              {/* Caption for the proposed "Trim border" crop (the dashed rectangle
                  itself is drawn inside the image box above so it stays aligned
                  on a letterboxed preview). */}
              {trimPreview && trimCrop && shownSrc ? (
                <Text size="xs" c="white" style={{ position: "absolute", left: 12, top: 10,
                  background: "rgba(0,0,0,0.6)", padding: "2px 8px", borderRadius: 4 }}>
                  Proposed crop{showCoverage ? " over coverage" : ""} — {trimKeptLabel(trimCrop)}
                </Text>
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
                      disabled={!preview.data || trimPreview}
                      loading={showCoverage && coveragePreview.isLoading}
                      onClick={() => setShowCoverage((s) => {
                        if (!s) { setShowMask(false); setShowBase(false); setSoloExclude(false); setSoloSplit(false); setSplitCompare(false); setLookSplit(false); }
                        return !s;
                      })}>
                      {showCoverage ? "Hide coverage" : "Coverage"}
                    </Button>
                  </Tooltip>
                ) : null}
                <Tooltip label="Show the soft mask that gates star ops (white = treated as a star)">
                  <Button size="xs" variant={showMask ? "filled" : "default"}
                    color="grape"
                    disabled={!preview.data || trimPreview}
                    loading={showMask && maskPreview.isLoading}
                    onClick={() => setShowMask((s) => {
                      if (!s) { setShowBase(false); setSoloExclude(false); setSoloSplit(false); setShowCoverage(false); setSplitCompare(false); setLookSplit(false); }
                      return !s;
                    })}>
                    {showMask ? "Hide mask" : "Star mask"}
                  </Button>
                </Tooltip>
                <Button size="xs" variant={showBase ? "filled" : "default"}
                  disabled={!preview.data || showMask || showCoverage || splitCompare || lookSplit || trimPreview}
                  onClick={() => setShowBase((s) => { if (!s) { setSoloExclude(false); setSoloSplit(false); setLookSplit(false); } return !s; })}>
                  {showBase ? "Edited" : "Compare"}
                </Button>
                <Tooltip multiline w={230} withArrow
                  label="Drag a divider across the preview to reveal the Original on the left and your edit on the right in one frame — the clearest way to judge exactly what a change did.">
                  <Button size="xs" variant={splitCompare ? "filled" : "default"}
                    disabled={!preview.data || showMask || showCoverage || trimPreview}
                    onClick={() => setSplitCompare((s) => {
                      if (!s) { setShowBase(false); setShowMask(false);
                        setShowCoverage(false); setSoloExclude(false); setSoloSplit(false);
                        setLookSplit(false); setSplitFrac(0.5); }
                      return !s;
                    })}>
                    {splitCompare ? "Hide split" : "Split"}
                  </Button>
                </Tooltip>
                {/* Compare the current edit against another look (Auto / a preset)
                    under the same split divider, so a repeat imager can judge
                    "this look vs mine" in one frame before committing. */}
                <LookComparePicker
                  builtin={lookPresets.data?.builtin ?? []}
                  user={lookPresets.data?.user ?? []}
                  disabled={!preview.data || showMask || showCoverage || trimPreview}
                  active={lookSplit}
                  activeLabel={lookSel?.label ?? null}
                  loading={pickLook.isPending}
                  onPick={(choice) => pickLook.mutate(choice)}
                  onStop={() => setLookSplit(false)}
                  onAdopt={adoptLook} />
                <Button size="xs" variant="default" leftSection={<IconRefresh size={14} />}
                  loading={preview.isFetching} onClick={refreshPreview}>Refresh</Button>
                <Button size="xs" variant="default" leftSection={<IconZoomScan size={14} />}
                  disabled={!shownSrc} onClick={() => setLightbox(true)}>Zoom</Button>
              </Group>
            </div>
            <Histogram data={hist.data}
              guides={tonalHistGuides(selectedOp,
                levels.data?.black != null && levels.data?.white != null
                  ? { black: levels.data.black, white: levels.data.white } : null,
                hist.data)} />
            {selectedOp?.id === "tone.levels" ? (
              <Text size="xs" c="dimmed" mt={4}>
                <b>B</b>/<b>W</b> mark your black &amp; white points on the histogram
                {levels.data?.black != null ? "; the dashed blue lines are the suggested points" : ""}.
              </Text>
            ) : selectedOp?.id === "tone.curves" ? (
              <Text size="xs" c="dimmed" mt={4}>
                The dashed purple lines mark where your curve's points sit on the tonal range.
              </Text>
            ) : null}
            {previewScaleCaption(hist.data) ? (
              <Text size="xs" c="dimmed" mt={4}>
                {previewScaleCaption(hist.data)}
              </Text>
            ) : null}
            {/* A geometry.crop op silently shrinks the visible frame — an
                auto-applied trim or a forgotten manual crop just looks like "my
                image got smaller". Flag any *enabled* crop with how much is left
                and a one-click way to undo it. Advisory; changes nothing unless
                clicked. */}
            {cropCoveragePct(ops) != null ? (
              <Group gap={6} wrap="nowrap" align="center" mt={4}>
                <IconCrop size={14} color="var(--mantine-color-dimmed)"
                  style={{ flexShrink: 0 }} />
                <Text size="xs" c="dimmed">
                  Cropped view — showing {cropCoveragePct(ops)}% of the frame.
                </Text>
                <Button size="compact-xs" variant="subtle" color="grape"
                  onClick={() => setOps((p) => removeCropOps(p))}>
                  Remove crop
                </Button>
              </Group>
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
            {/* Deconvolution reverses a sub-pixel blur that isn't representable
                on the decimated preview proxy, so on a large mosaic/drizzle the
                preview understates it. Say so honestly rather than let the
                preview↔export look diverge silently. Advisory only. */}
            {deconvUnderstatesCaption(hist.data) ? (
              <Group gap={6} wrap="nowrap" align="flex-start" mt={4}>
                <IconInfoCircle size={14} color="var(--mantine-color-dimmed)"
                  style={{ flexShrink: 0, marginTop: 2 }} />
                <Text size="xs" c="dimmed">{deconvUnderstatesCaption(hist.data)}</Text>
              </Group>
            ) : null}
            {/* Star reduction erodes with a footprint that clamps to 1 px on a
                heavily-decimated proxy, so on a large mosaic/drizzle the preview
                *overstates* the effect (opposite of deconv). Caption it honestly
                so the user doesn't under-set the amount. Advisory only. */}
            {starReduceOverstatesCaption(hist.data) ? (
              <Group gap={6} wrap="nowrap" align="flex-start" mt={4}>
                <IconInfoCircle size={14} color="var(--mantine-color-dimmed)"
                  style={{ flexShrink: 0, marginTop: 2 }} />
                <Text size="xs" c="dimmed">{starReduceOverstatesCaption(hist.data)}</Text>
              </Group>
            ) : null}
            {/* Which white-balance path the recipe's colour-calibration op ran on
                this live preview (the one-click Auto includes one) — star-based,
                the too-few-stars background-neutral fallback, or gave up. Mirrors
                the History Info read-out the autonomous auto-edit shows, so a user
                who clicks Auto *in the editor* also learns whether their picture
                was really white-balanced. Read-only; absent until a colour-cal op
                runs. */}
            {(() => {
              const cc = autoColorCalCaption(hist.data?.color_cal);
              if (!cc) return null;
              return (
                <Group gap={6} wrap="nowrap" align="flex-start" mt={4}>
                  <IconInfoCircle size={14} color="var(--mantine-color-dimmed)"
                    style={{ flexShrink: 0, marginTop: 2 }} />
                  <Text size="xs" c={cc.neutral ? "teal.6" : "dimmed"}>{cc.text}</Text>
                </Group>
              );
            })()}
            {/* Robust read-out of the *finished* sky background's colour balance,
                measured over the sky population of the post-recipe display image.
                Beginners have no other way to see whether their background ended
                up neutral; this makes a residual green/magenta cast visible.
                Read-only advisory — changes nothing. */}
            {skyCastCaption(hist.data) ? (
              <Group gap={6} wrap="nowrap" align="flex-start" mt={4}>
                <IconInfoCircle size={14} color="var(--mantine-color-dimmed)"
                  style={{ flexShrink: 0, marginTop: 2 }} />
                <Text size="xs" c="dimmed">{skyCastCaption(hist.data)!.text}</Text>
                {/* When there's a real cast and the fix will land in display space,
                    offer a one-click neutralise (appends a display-space op that
                    balances the sky to neutral grey) — an undoable step. */}
                {canNeutralise ? (
                  <Button variant="subtle" size="compact-xs" px={6}
                    onClick={neutraliseBackground}>Neutralize</Button>
                ) : null}
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

            {/* A recipe a *background* job auto-edited (Process-target / reprocess /
                watcher auto-stack): explain it — the user landed here on an edit
                they didn't build. Shown only while the pipeline is still pristine
                (unedited) and no interactive Auto note is up, and only when a note
                was actually stored, so a hand-built recipe never surfaces it. */}
            {!autoSummary && seedKey !== null && recipeKey === seedKey
              && autoNote.data?.note ? (
              <Alert color="violet" variant="light" py={8}
                icon={<IconWand size={16} />} title="This picture was auto-edited">
                <Text size="xs" c="dimmed">{autoNote.data.note}</Text>
                {/* The pipeline is still pristine here, so it *is* the auto recipe:
                    surface the same data-driven values the interactive Auto note
                    shows, so a user who lands here via Process-target gets the same
                    explanation as one who clicked Auto. */}
                {autoValueSentence(ops) ? (
                  <Text size="xs" c="dimmed" mt={4}>{autoValueSentence(ops)}</Text>
                ) : null}
                {/* The walk-away user landed here via Process-target — tell them
                    the hands-off master was calibrated (the same trust line the
                    History Info panel shows). Positive case only: the "build a
                    master" nudge stays on History so the editor note doesn't
                    scold a user mid-edit. */}
                {(() => {
                  const cards = runInfo.data?.cards;
                  if (!cards) return null;
                  const cal = calibrationSummaryText(cards);
                  if (!cal || !cal.calibrated) return null;
                  return <Text size="xs" c="dimmed" mt={4}>{cal.text}</Text>;
                })()}
                <Text size="10px" c="dimmed" mt={4}>
                  These steps were chosen from your image — tweak or remove any of them below.
                </Text>
              </Alert>
            ) : null}

            {autoSummary ? (
              <Alert color="violet" variant="light" py={8} withCloseButton
                icon={<IconWand size={16} />} title="What Auto-process did"
                onClose={() => { setAutoSummary(null); setAutoValues(null); setAutoCause(null); }}>
                <Text size="xs">{autoSummary}</Text>
                {autoCause ? (
                  <Text size="xs" mt={4} c="dimmed">{autoCause}</Text>
                ) : null}
                {autoValues ? (
                  <Text size="xs" mt={4}>{autoValues}</Text>
                ) : null}
                {/* Content classification: the "try this preset?" chip only shows on
                    an empty pipeline, so a user who clicked Auto straight away never
                    learns their image was classified. Surface the same hint here as a
                    purely-informational line (another starting point to compare, never
                    a claim Auto was wrong) — hidden when the classifier is unsure. */}
                {presetSuggestionSentence(presetSuggest.data) ? (
                  <Text size="xs" mt={4} c="dimmed">
                    {presetSuggestionSentence(presetSuggest.data)}
                  </Text>
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
                  <Group gap={6}>
                    <Button size="compact-xs" variant="light" color="grape"
                      leftSection={<IconSparkles size={14} />}
                      loading={auto.isPending} onClick={() => auto.mutate()}>
                      Auto-process
                    </Button>
                    {/* Carry-over: if this target has a previous run you edited, offer to
                        reuse that look in one click, so a multi-night project stays
                        consistent without redoing the edit. Undoable; not saved unless
                        the user Saves. */}
                    {prevRecipe.data?.run_id != null && prevRecipe.data.count > 0 ? (
                      <Tooltip multiline w={240} withArrow
                        label="Copy the edit you saved on this target's previous stack onto this one (as an undoable step you can tweak, then Save).">
                        <Button size="compact-xs" variant="default" color="grape"
                          leftSection={<IconHistory size={14} />}
                          onClick={applyPreviousRecipe}>
                          Use my previous edit ({prevRecipe.data.count})
                        </Button>
                      </Tooltip>
                    ) : null}
                    {/* Personal "house style": if the user set a default recipe (via
                        the Presets menu), offer it as a one-click seed here too, so
                        their preferred look is one click away on every new target.
                        Undoable; not saved unless the user Saves. */}
                    {(defaultRecipe.data?.count ?? 0) > 0 ? (
                      <Tooltip multiline w={240} withArrow
                        label="Start from the default edit you saved in the Presets menu (as an undoable step you can tweak, then Save).">
                        <Button size="compact-xs" variant="default" color="grape"
                          leftSection={<IconStar size={14} />}
                          onClick={applyDefaultRecipe}>
                          Use my default ({defaultRecipe.data!.count})
                        </Button>
                      </Tooltip>
                    ) : null}
                  </Group>
                  {/* Coarse content classification: when this run's image clearly
                      looks like one archetype, offer its matching built-in preset as
                      an alternative starting point to the general Auto recipe. A hint
                      only — a wrong guess costs a click, not an image — so it's hidden
                      whenever the backend is unsure (preset_id null). */}
                  {presetSuggest.data?.preset_id ? (
                    <Group gap={6} mt={8} align="center" wrap="nowrap">
                      <Text size="xs" c="dimmed">
                        This looks like a <b>{presetSuggest.data.label}</b>
                        {presetSuggest.data.reason ? ` — ${presetSuggest.data.reason}.` : "."}
                      </Text>
                      <Tooltip multiline w={240} withArrow
                        label={`Start from the ${presetSuggest.data.label} preset (sized to your data), as an undoable step you can tweak, then Save.`}>
                        <Button size="compact-xs" variant="default" color="grape"
                          leftSection={<IconWand size={14} />}
                          onClick={applySuggestedPreset}>
                          Try the {presetSuggest.data.label} preset
                        </Button>
                      </Tooltip>
                    </Group>
                  ) : null}
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
                    {/* One-click "Auto stretch" sets the asinh Strength and Black
                        point from the run's own linear data (sky floor → black, sky
                        median lifted to a clean dark grey), so the most consequential
                        tonal control gets a well-exposed start in a single click. The
                        per-param "From your image" buttons stay for fine control. */}
                    {selectedOp.id === "tone.stretch"
                      && selectedOp.params?.mode !== "stf"
                      && stretch.data?.stretch != null && stretch.data?.black != null ? (
                      <Tooltip
                        label="Set the asinh strength and black point from this image's own data"
                        multiline w={220} withArrow>
                        <Button size="compact-xs" variant="light" color="blue"
                          onClick={() => setParams(selectedOp.uid, {
                            ...selectedOp.params,
                            stretch: stretch.data!.stretch,
                            black: stretch.data!.black,
                          })}>
                          Auto stretch ({stretch.data.stretch})
                        </Button>
                      </Tooltip>
                    ) : null}
                    {/* One-click "Auto curve" drops a gentle, monotone midtone-lift
                        curve derived from this image's own histogram, so the Curves
                        op gives a pleasant contrast start to nudge instead of a flat
                        identity line. Hidden while Auto-contrast is already engaged
                        (the ghost + "Bake to edit" below is the control then). */}
                    {selectedOp.id === "tone.curves" && curve.data?.points != null
                      && !curveGhost ? (
                      (() => {
                        const applied = curvePointsMatch(
                          selectedOp.params?.points, curve.data.points);
                        const greyPct = curve.data.target_bg != null
                          ? Math.round(curve.data.target_bg * 100) : null;
                        return (
                          <Tooltip
                            label="Set a gentle starting curve from this image's histogram — lifts the midtones toward a pleasant grey, keeping the sky and star cores anchored"
                            multiline w={240} withArrow>
                            <Button size="compact-xs" variant="light" color="blue"
                              disabled={applied}
                              onClick={() => setParams(selectedOp.uid, {
                                ...selectedOp.params,
                                points: curve.data!.points,
                              })}>
                              {applied
                                ? "Auto curve ✓"
                                : greyPct != null
                                  ? `Auto curve (lifts to ~${greyPct}% grey)`
                                  : "Auto curve"}
                            </Button>
                          </Tooltip>
                        );
                      })()
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
                        label={reshapesFrame(selectedOp.id)
                          ? "This op changes the frame's shape (crop/rotate/resize), so a per-op compare can't line up pixel-for-pixel — use Compare or Split to judge the whole edit"
                          : "Preview the image with only this op bypassed, to see just its effect"}
                        multiline w={240} withArrow>
                        <Button size="compact-xs"
                          variant={soloActive ? "filled" : "default"} color="grape"
                          loading={soloActive && withoutOpPreview.isLoading}
                          disabled={!preview.data || reshapesFrame(selectedOp.id) || trimPreview}
                          onClick={() => setSoloExclude((s) => {
                            if (!s) { setShowBase(false); setShowMask(false); setShowCoverage(false); setSoloSplit(false); setSplitCompare(false); setLookSplit(false); }
                            return !s;
                          })}>
                          {soloActive ? "Showing without" : "Without this op"}
                        </Button>
                      </Tooltip>
                    ) : null}
                    {/* Split analogue of "Without this op": drag a divider to compare
                        the image with vs without just this op in one frame, the most
                        precise answer to "is this slider actually helping?". */}
                    {selectedOp.enabled ? (
                      <Tooltip
                        label={reshapesFrame(selectedOp.id)
                          ? "This op changes the frame's shape (crop/rotate/resize), so a per-op split can't line up pixel-for-pixel — use the whole-edit Split instead"
                          : "Drag a divider across the preview to reveal the image without this op on the left and with it on the right — see exactly what just this op did"}
                        multiline w={240} withArrow>
                        <Button size="compact-xs"
                          variant={soloSplitActive ? "filled" : "default"} color="grape"
                          loading={soloSplitActive && withoutOpPreview.isLoading}
                          disabled={!preview.data || reshapesFrame(selectedOp.id) || trimPreview}
                          onClick={() => setSoloSplit((s) => {
                            if (!s) { setShowBase(false); setShowMask(false); setShowCoverage(false);
                              setSoloExclude(false); setSplitCompare(false); setLookSplit(false); setSplitFrac(0.5); }
                            return !s;
                          })}>
                          {soloSplitActive ? "Hide op split" : "Split this op"}
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
                  histogram={hist.data}
                  curveGhost={curveGhost} onBakeCurve={bakeAutoCurve}
                  onChange={(p, coalesceKey) => setParams(selectedOp.uid, p, coalesceKey)}
                  suggestions={
                    selectedOp.id === "detail.deconvolve" && psf.data?.psf_sigma != null
                      ? {
                        psf_sigma: {
                          value: psf.data.psf_sigma,
                          label: `From your stars (σ≈${psf.data.psf_sigma}, FWHM ${psf.data.fwhm_px}px)`,
                        },
                      }
                      : selectedOp.id === "detail.denoise" &&
                        (denoiseOp.data?.strength ?? denoise.data?.strength) != null
                        ? {
                          strength: {
                            value: (denoiseOp.data?.strength ?? denoise.data!.strength)!,
                            label: `From your image (strength ${denoiseOp.data?.strength ?? denoise.data!.strength})`,
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
                            : selectedOp.id === "tone.stretch"
                              && selectedOp.params?.mode !== "stf"
                              && stretch.data?.stretch != null && stretch.data?.black != null
                              ? {
                                // Each button sets only its own slider, so label it
                                // with just that value. Strength names the goal it
                                // solves for (the sky grey), like the gamma button.
                                stretch: {
                                  value: stretch.data.stretch,
                                  label: stretch.data.target_bg != null
                                    ? `From your image (strength ${stretch.data.stretch} — lands the sky at ~${Math.round(stretch.data.target_bg * 100)}% grey)`
                                    : `From your image (strength ${stretch.data.stretch})`,
                                },
                                black: {
                                  value: stretch.data.black,
                                  label: `From your image (black ${stretch.data.black})`,
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
                                    // Name the goal the lift solves for (like the
                                    // sharpen/denoise buttons naming FWHM/σ), so the
                                    // number has visible provenance for a beginner.
                                    label: levels.data.gamma_target != null
                                      ? `From your image (midtones ${levels.data.gamma} — lands the sky at ~${Math.round(levels.data.gamma_target * 100)}% grey)`
                                      : `From your image (midtones ${levels.data.gamma})`,
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
        title={`${safe} — ${overlay ? overlay.label : "edited"}`
          + (previewScaleCaption(hist.data) ? ` · ${previewScaleCaption(hist.data)}` : "")}
        onClose={() => setLightbox(false)} />
    </Stack>
  );
}
