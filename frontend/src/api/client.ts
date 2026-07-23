// Tiny typed fetch wrapper around the AstroStack API.

import type { SkyImage, SkyStar } from "../sky/projection";

export interface SkyData {
  stars: SkyStar[];
  images: SkyImage[];
}

export interface PlannedTarget {
  id: string;
  name: string;
  ra_deg: number;
  dec_deg: number;
  type: string;
  con: string;
  already_targeted: boolean;
  max_altitude_deg: number;
  transit_utc: string | null;
  minutes_above_min_alt: number;
  moon_separation_deg: number;
  score: number;
  // Share (0..1) of this target's usable window the Moon is above the horizon —
  // the overlap that weights its Moon penalty. Lets the UI explain why a
  // bright-Moon night still ranked a target well (the Moon was down while it was
  // up). null/absent when the target has no usable window or on an older backend.
  moon_up_fraction?: number | null;
  // Clock bounds (UTC ISO) of when the target is actually shootable tonight — the
  // first/last moment it clears the floor — complementing the peak transit time.
  // null/absent when never usable or on an older backend.
  usable_start_utc?: string | null;
  usable_end_utc?: string | null;
  target_safe: string | null;
  frames_accepted: number | null;
  total_exposure_s: number | null;
  // "Will it fit in one Seestar frame?" — major-axis size (arcmin) and the
  // verdict, for catalog candidates the bundled catalog has a size for. Absent
  // on library rows and older backends. See FramingHint.
  size_arcmin?: number | null;
  framing?: FramingHint | null;
}

export interface NightPlan {
  location_source: "settings" | "fits" | "none";
  observer: { lat_deg: number; lon_deg: number; elevation_m: number } | null;
  generated_utc: string;
  dark_window: {
    start_utc: string;
    end_utc: string;
    duration_minutes: number;
    sun_alt_threshold_deg: number;
  } | null;
  moon_illumination: number | null;
  // Whether the Moon is waxing (sets in the evening) or waning (rises after
  // midnight); null when no plan could be computed. Lets the UI say "Waxing
  // gibbous" vs "Waning gibbous" — the fraction alone can't tell them apart.
  moon_waxing?: boolean | null;
  // When the Moon rises/sets during tonight's dark window (concrete UTC times),
  // or that it stays up / down for the whole window. Absent/null when no dark
  // window could be computed. Complements the phase with the actual clock time.
  moon_window?: {
    rise_utc: string | null;
    set_utc: string | null;
    up_all_night: boolean;
    down_all_night: boolean;
  } | null;
  min_altitude_deg: number;
  // True when a horizon/tree mask (Settings → Observing site) shaped the usable
  // windows, so the UI can note that low-sky obstructions were accounted for.
  horizon_active?: boolean;
  targets: PlannedTarget[];
}

// One upcoming night a target is well-placed in a dark window — the forward-
// looking companion to the retrospective trend cards. All times are UTC ISO.
export interface NextObservingWindow {
  dark_start_utc: string;
  dark_end_utc: string;
  usable_start_utc: string | null;
  usable_end_utc: string | null;
  max_altitude_deg: number;
  minutes_above_min_alt: number;
  moon_illumination: number;
  moon_up_fraction: number | null;
  score: number;
}

export interface NextSession {
  location_source: "settings" | "fits" | "none";
  observer: { lat_deg: number; lon_deg: number; elevation_m: number } | null;
  // False when the library has no RA/Dec for this target (never solved) — the
  // card then can't say *when*, only *how much* is left.
  target_has_position: boolean;
  min_altitude_deg: number;
  nights_scanned: number;
  // The next few nights it's shootable, soonest first; empty when no location is
  // set, the target has no position, or nothing clears the floor in the horizon.
  windows: NextObservingWindow[];
}

// One not-yet-captured showpiece that's well-placed tonight — a "try something
// new" discovery suggestion (from /api/plan/suggest). Carries the friendly
// catalog blurb ("what am I looking at?") plus tonight's observability.
export interface SuggestedTarget {
  id: string;
  name: string;
  ra_deg: number;
  dec_deg: number;
  type: string;
  con: string;
  blurb: string;
  max_altitude_deg: number;
  transit_utc: string | null;
  minutes_above_min_alt: number;
  moon_separation_deg: number;
  moon_up_fraction: number | null;
  usable_start_utc: string | null;
  usable_end_utc: string | null;
  score: number;
  size_arcmin?: number | null;
  framing?: FramingHint | null;
}

export interface SuggestResponse {
  location_source: "settings" | "fits" | "none";
  observer: { lat_deg: number; lon_deg: number; elevation_m: number } | null;
  min_altitude_deg: number;
  // A few famous showpieces the user hasn't captured that are up tonight,
  // best-first; empty when no location is set or nothing new is well-placed.
  suggestions: SuggestedTarget[];
}

// Plain-language "why were some frames left out?" breakdown (from
// /frames/reject-summary). Buckets are non-zero and pre-ordered by the server.
export interface RejectionBucket {
  key: string;
  label: string;
  count: number;
  note: string;
}
export interface RejectionSummary {
  used: number;
  dropped: number;
  dropped_fraction: number;
  verdict: { tone: "good" | "ok" | "warn"; text: string };
  buckets: RejectionBucket[];
}

export interface Target {
  safe_name: string;
  name: string;
  ra_deg: number | null;
  dec_deg: number | null;
  n_frames: number;
  n_frames_accepted: number;
  total_exposure_s: number;
  last_activity_utc: string | null;
  has_preview: boolean;
  notes: string | null;
  tags: string[];
  cover_stack_run_id?: number | null;
}

export interface MergeSuggestionTarget {
  safe: string;
  name: string;
  n_frames_accepted: number;
  total_exposure_s: number;
}

// A "these look like the same object — combine them?" suggestion: a cluster of
// ≥2 targets whose plate-solved centres agree. `targets` are ordered
// deepest-integration first, so `targets[0].safe` is the natural merge `into`.
export interface MergeSuggestion {
  object_name: string | null;
  center_ra_deg: number;
  center_dec_deg: number;
  max_sep_arcmin: number;
  targets: MergeSuggestionTarget[];
}

export interface FramingHint {
  level: "fits" | "tight" | "mosaic";
  text: string;
}

export interface ObjectInfo {
  id: string;
  name: string;
  type: string;
  constellation: string;
  constellation_abbr: string;
  ra_deg: number;
  dec_deg: number;
  matched_by: "name" | "coords";
  // Major-axis size (arcmin) and the "will it fit in one frame?" verdict, when
  // the catalog records a size for this object; absent otherwise (older backends
  // omit both — treat as "no framing hint").
  size_arcmin?: number | null;
  framing?: FramingHint | null;
  // A plain-language, beginner-friendly one-liner about the object ("what am I
  // looking at?"), for the popular targets; absent/"" when the catalog has none
  // (older backends omit it — the card reads fine from type + constellation).
  blurb?: string;
}

export interface SessionQualityDrift {
  kind: string;
  latest_fwhm_px: number;
  baseline_fwhm_px: number;
  n_latest: number;
  n_baseline: number;
}

export interface SessionRecap {
  n_frames: number;
  n_kept: number;
  n_set_aside: number;
  session_exposure_s: number;
  kept_exposure_s: number;
  total_kept_exposure_s: number;
  start_utc: string | null;
  end_utc: string | null;
  reject_buckets: Record<string, number>;
  quality_drift: SessionQualityDrift | null;
}

export interface HealthNote {
  kind: string;
  severity: "good" | "info";
  message: string;
  action: string | null;
}

export interface StackHealth {
  run_id: number | null;
  notes: HealthNote[];
}

export interface BestFrame {
  frame_id: number | null;
  captured_utc: string | null;
  fwhm_px: number | null;
  star_count: number | null;
  n_accepted: number;
}

export interface TargetNight {
  name: string;
  safe: string;
  n_frames: number;
  n_kept: number;
  n_set_aside: number;
  exposure_s: number;
  kept_exposure_s: number;
}

export interface NightSummary {
  start_utc: string | null;
  end_utc: string | null;
  n_frames: number;
  n_kept: number;
  n_set_aside: number;
  exposure_s: number;
  kept_exposure_s: number;
  median_fwhm_px: number | null;
  verdict: string; // "sharp" | "soft" | "hazy" | "" (too few measured)
  is_best: boolean;
  reject_buckets: Record<string, number>;
}

export interface FocusTrendPoint {
  t_utc: string;
  fwhm_px: number;
}

export interface FocusTrend {
  verdict: string; // "steady" | "softened" | "improved"
  points: FocusTrendPoint[];
  n_points: number;
  median_fwhm_px: number;
  early_fwhm_px: number;
  late_fwhm_px: number;
  start_utc: string | null;
  end_utc: string | null;
  soft_after_utc: string | null;
}

export interface TransparencyTrendPoint {
  t_utc: string;
  transparency: number;
}

export interface TransparencyTrend {
  verdict: string; // "clear" | "degraded" | "cleared"
  points: TransparencyTrendPoint[];
  n_points: number;
  median_transparency: number;
  early_transparency: number;
  late_transparency: number;
  start_utc: string | null;
  end_utc: string | null;
  degraded_after_utc: string | null;
}

export interface LibrarySessionRecap {
  n_targets: number;
  n_frames: number;
  n_kept: number;
  n_set_aside: number;
  session_exposure_s: number;
  kept_exposure_s: number;
  start_utc: string | null;
  end_utc: string | null;
  targets: TargetNight[];
  reject_buckets: Record<string, number>;
}

export interface TargetProgress {
  safe: string;
  name: string;
  total_exposure_s: number;
  object_type: string | null;
  goal_s: number | null;
}

export interface SummaryTarget {
  safe: string;
  name: string;
  total_exposure_s: number;
  integration_hours: number;
  n_frames_accepted: number;
  thumbnail_url: string | null;
}

export interface LibrarySummary {
  n_targets_imaged: number;
  n_subs_kept: number;
  total_integration_s: number;
  integration_hours: number;
  first_light_utc: string | null;
  longest_target: SummaryTarget | null;
  most_imaged_target: SummaryTarget | null;
  heroes: SummaryTarget[];
}

export interface DashboardStats {
  n_targets: number;
  n_frames: number;
  n_frames_accepted: number;
  total_exposure_s: number;
  integration_hours: number;
  acceptance_rate: number | null;
  n_stack_runs: number;
  n_targets_with_stacks: number;
  active_jobs: number;
  recent_stacks: {
    safe: string;
    target_name: string;
    run_id: number;
    output_basename: string;
    timestamp_utc: string;
    n_frames_used: number;
    has_preview: boolean;
    preview_url: string;
  }[];
  disk: { total_gb?: number; used_gb?: number; free_gb?: number };
}

export interface TargetStorage {
  safe: string;
  name: string;
  total_bytes: number;
  output_bytes: number;
  cache_bytes: number;
  stage1_bytes: number;
  stage2_bytes: number;
  thumbs_bytes: number;
  n_stack_runs: number;
}

export interface StorageInfo {
  targets: TargetStorage[];
  total_bytes: number;
  output_bytes: number;
  cache_bytes: number;
  disk: { total_gb?: number; used_gb?: number; free_gb?: number };
}

export interface SeestarTelemetry {
  device_name: string | null;
  model: string | null;
  firmware: string | null;
  temp_c: number | null;
  battery_pct: number | null;
  charging: boolean | null;
  charger_status: string | null;
  free_storage_mb: number | null;
  total_storage_mb: number | null;
  mode: string | null;
  state: string | null;
  stage: string | null;
  target_name: string | null;
  stacked_frames: number | null;
  dropped_frames: number | null;
  ra_hours: number | null;
  dec_deg: number | null;
}

export interface SeestarDevice {
  id: string;
  ip: string;
  device_name: string | null;
  model: string | null;
  firmware: string | null;
  reachable: boolean;
  connected: boolean;
  reconnecting?: boolean;
  last_seen_utc: string | null;
  telemetry: SeestarTelemetry | null;
  error: string | null;
}

export interface SeestarDevices {
  enabled: boolean;
  control_enabled: boolean;
  devices: SeestarDevice[];
}

export interface Frame {
  id: number;
  name: string;
  timestamp_utc: string | null;
  exposure_s: number | null;
  gain: number | null;
  width_px: number | null;
  height_px: number | null;
  bayer_pattern: string | null;
  solved: boolean;
  ra_center_deg: number | null;
  dec_center_deg: number | null;
  ra_hint_deg: number | null;
  dec_hint_deg: number | null;
  fwhm_px: number | null;
  star_count: number | null;
  sky_adu_median: number | null;
  eccentricity_median: number | null;
  transparency_score: number | null;
  streak_detected: boolean;
  accept: boolean;
  reject_reason: string | null;
  user_override: boolean;
}

export interface GradeReason {
  metric: string;
  label: string;
  value: number;
  typical: number;
  z: number;
}

export interface GradeRecommendation {
  frame_id: number;
  name: string;
  reasons: GradeReason[];
}

export interface GradeReport {
  sensitivity: string;
  n_accepted: number;
  n_considered: number;
  recommendations: GradeRecommendation[];
  metrics_used: string[];
  metrics_skipped: Record<string, string>;
  capped: boolean;
  changed_ids: number[] | null;
}

export interface StackRun {
  id: number;
  timestamp_utc: string;
  output_basename: string;
  n_frames_used: number;
  canvas_w: number;
  canvas_h: number;
  coverage_min: number;
  coverage_max: number;
  has_fits: boolean;
  has_tiff: boolean;
  has_preview: boolean;
  is_cover?: boolean;
  notes: string | null;
  total_exposure_s?: number | null;
  reusable?: boolean;
  transparency_ratio?: number | null;
  noise_sigma?: number | null;
  calstat?: string | null;
  options?: Record<string, unknown>;
  engine_version?: string | null;
}

export interface StackInfoCard {
  key: string;
  value: string | number | boolean;
  comment: string | null;
}

export interface ReprocessStatus {
  current_version: string;
  outdated: number;      // targets whose current image was made by an older version
  up_to_date: number;    // targets already stacked on the running version
  total_targets: number;
}

export interface AutoCastSummary {
  measured: number;                  // auto-edited runs with a usable sky-cast reading
  neutral: number;                   // of those, how many landed background-neutral
  cast: number;                      // of those, how many carried a residual colour cast
  by_cast: Record<string, number>;   // dominant-tint counts among the cast runs
  median_deviation: number | null;   // median largest per-channel departure from grey
}

export interface StackWeightingSummary {
  mode: string;
  n_downweighted?: number;
  min?: number;
  max?: number;
  median?: number;
}

export interface StackPhotometricSummary {
  mode: string;
  n_adjusted?: number;
  min?: number;
  max?: number;
  median?: number;
}

export interface StackDarkScalingSummary {
  mode: string;
  dark_exposure?: number;
  light_exposure?: number;
}

export interface StackRejectionSummary {
  mode: string;
  n_rejected?: number;
  n_contributed?: number;
  fraction?: number;
}

export interface StackFrameAccounting {
  // Subs the stacker attempted to combine (after lucky/mosaic-outlier filtering).
  n_offered: number;
  // Of those, how many couldn't be aligned (load failure or a footprint that
  // missed the canvas — usually a stray sub or a bad plate-solve).
  n_align_failed?: number;
}

export interface StackProcessingStep {
  op: string;
  label: string;
}

/** One catalog deep-sky object that falls inside a stack's field. */
export interface FieldObject {
  catalog_id: string;   // catalog designation, e.g. "M31" / "NGC 891"
  name: string;         // friendly name when the catalog has one, else ""
  type: string;         // "galaxy" / "nebula" / …
  ra_deg: number;
  dec_deg: number;
  x_px: number;         // 0-based pixel x on the FITS grid (width_px below)
  y_px: number;         // 0-based pixel y on the FITS grid (height_px below)
}

/** "What's in this picture?" — objects + the grid their pixel coords live on. */
export interface StackAnnotations {
  width: number;        // the run's FITS pixel width (x_px domain)
  height: number;       // the run's FITS pixel height (y_px domain)
  objects: FieldObject[];
}

export interface StackRunInfo {
  run_id: number;
  integration_s: number | null;
  n_frames: number | null;
  weighting: StackWeightingSummary | null;
  photometric?: StackPhotometricSummary | null;
  dark_scaling?: StackDarkScalingSummary | null;
  rejection?: StackRejectionSummary | null;
  // Honest per-run frame accounting — how many subs the stacker attempted to
  // combine and how many couldn't be aligned. Absent on older masters.
  frame_accounting?: StackFrameAccounting | null;
  // Plain-language "what the unattended auto-edit did (and why)" note, present
  // only on runs an autonomous job auto-edited (Process-target / reprocess /
  // watcher auto-stack). Absent on manual/un-edited runs.
  auto_edit?: string | null;
  // The finished picture's residual sky-background colour cast (r/g/b sky medians
  // + a neutral/colour verdict), measured on the auto-edited render an unattended
  // job produced. Present only on auto-edited runs; lets History show whether the
  // hands-off Auto path landed the background neutral. Absent on older runs.
  sky_cast?: SkyCast | null;
  // Which colour-calibration (white-balance) path the auto-edit's Auto recipe
  // actually ran and on how many stars — the star-based gray-star/Gaia solve, the
  // background-neutral fallback (too few stars), or a no-op. Present only on
  // auto-edited runs; lets History tell the user whether their hands-off image was
  // really white-balanced (and by which route). Absent on older/manual runs.
  color_cal?: AutoColorCal | null;
  // A specific, actionable hint for *why* a stack that carries provenance came out
  // uncalibrated (e.g. "you have a master dark at a different exposure — build a
  // master bias and it'll be reused automatically"). Present only when the library
  // holds a master that's usable but for one concrete, fixable thing; the generic
  // "build or pick a master" copy is used otherwise.
  calibration_advice?: string | null;
  processing?: StackProcessingStep[];
  cards: StackInfoCard[];
}

export interface StackEstimate {
  n_frames: number;
  canvas_w: number;
  canvas_h: number;
  output_w: number;
  output_h: number;
  is_mosaic: boolean;
  peak_bytes: number;
  peak_gb: number;
  budget_bytes: number;
  budget_gb: number;
  would_exceed: boolean;
  suggested_drizzle_scale: number | null;
  suggested_reference_canvas: boolean;
}

export interface GalleryItem {
  safe: string;
  target_name: string;
  run_id: number;
  output_basename: string;
  timestamp_utc: string;
  n_frames_used: number;
  canvas_w: number;
  canvas_h: number;
  total_exposure_s: number | null;
  notes?: string | null;
  has_preview: boolean;
  has_fits: boolean;
  has_tiff: boolean;
  preview_url: string;
  options: Record<string, unknown>;
  reusable?: boolean;
  transparency_ratio?: number | null;
  noise_sigma?: number | null;
  calstat?: string | null;
}

export interface BestPicture {
  safe: string;
  target_name: string;
  run_id: number;
  output_basename: string;
  timestamp_utc: string;
  n_frames_used: number;
  canvas_w: number;
  canvas_h: number;
  total_exposure_s: number | null;
  noise_sigma: number | null;
  has_preview: boolean;
  has_fits: boolean;
  has_tiff: boolean;
  preview_url: string;
  // Quality-blend score in [0, 1], relative to this Library's own collection.
  score: number;
}

export interface LogEntry {
  seq: number;
  ts: string;
  level: string;
  levelno: number;
  logger: string;
  message: string;
}

export interface Job {
  id: string;
  kind: string;
  target: string | null;
  state: string;
  phase: string;
  done: number;
  total: number;
  detail: string;
  created_utc: string | null;
  started_utc: string | null;
  finished_utc: string | null;
  error: string | null;
  /** Stable canonical failure category set server-side (webapp/jobs.py), preferred
   * over string-matching the raw `error`. Absent on an older backend. */
  error_kind?: string | null;
  result: Record<string, unknown> | null;
}

export interface StackOptionField {
  key: string;
  label: string;
  type: "bool" | "int" | "float" | "str" | "enum" | "curve";
  group: "simple" | "advanced";
  default: unknown;
  min: number | null;
  max: number | null;
  step: number | null;
  options: string[] | null;
  option_labels?: Record<string, string> | null;
  help: string | null;
  depends_on: string | null;
}

export interface SystemInfo {
  version: string;
  data_root: string;
  cpu_count: number | null;
  cpu_workers: number | null;
  gpu_available: boolean;
  astap: {
    found: boolean;
    path: string | null;
    star_db_found?: boolean;
    star_db_dir?: string | null;
    star_db_count?: number;
    runs?: boolean;
    version?: string | null;
    hint?: string;
    error?: string;
  };
  disk: { total_gb?: number; used_gb?: number; free_gb?: number };
  memory: { total_gb?: number; available_gb?: number };
  folders?: {
    incoming: { path: string; exists: boolean; writable: boolean };
    library: { path: string; exists: boolean; writable: boolean };
  };
  watcher_enabled: boolean;
}

export type Settings = Record<string, unknown> & {
  resolved_incoming_dir: string;
  resolved_library_root: string;
};

// --- editor ---------------------------------------------------------------

export interface EditOp {
  id: string;
  label: string;
  group: string;
  stage: string;
  proxy_safe: boolean;
  is_stretch: boolean;
  heavy?: boolean;
  help: string | null;
  params: StackOptionField[];
}

export interface OpInstance {
  uid: string;
  id: string;
  enabled: boolean;
  params: Record<string, unknown>;
}

export interface Recipe {
  version?: number;
  base_run_id?: number | null;
  updated_utc?: string | null;
  ops: OpInstance[];
}

/** The most recent *other* run's saved editor recipe, offered for one-click
 * carry-over onto a re-stacked run. `run_id` is null when none exists. */
export interface PreviousRecipe {
  run_id: number | null;
  ops: OpInstance[];
  count: number;
}

/** The user's library-wide default editor recipe ("my house style"), offered as
 * a one-click seed on any run with no saved edit. `count` is 0 when unset. */
export interface DefaultRecipe {
  ops: OpInstance[];
  count: number;
}

export interface Preset {
  id: string;
  label: string;
  group: string;
  ops: { id: string; params: Record<string, unknown>; enabled?: boolean; uid?: string }[];
}

/** The library's Adaptive-Auto "taste" profile: the active per-parameter `biases`
 * the owner built up by giving Auto plain-language feedback, a plain-language
 * `note` explaining how Auto shifted (`null` when neutral), and a `neutral` flag.
 * An unset profile reads as neutral — Auto then behaves exactly as its data-driven
 * default. Served by `…/editor/auto-preferences`. */
export interface AutoPreferences {
  biases: Record<string, number>;
  note: string | null;
  neutral: boolean;
}

/** The measured cues Auto-process read from a run's own data to build its recipe
 * (the *causal inputs* behind the ops), served by `…/editor/auto-analysis`. Every
 * field is nullable so it degrades gracefully: sky/noise are null when the proxy
 * can't be measured, `median_fwhm`/`sharpen_radius` are null with no solved stars,
 * and `trim_fraction` is null on a single-field (non-trimmed) stack. */
export interface AutoAnalysis {
  sky: number | null;            // measured normalized sky level (0..1)
  sky_sigma: number | null;      // robust background noise σ
  noisy: boolean | null;         // coarse noisy verdict
  noise_fraction: number | null; // 0..1 denoise/sharpen crossfade weight
  median_fwhm: number | null;    // target's median star FWHM (px)
  sharpen_radius: number | null; // unsharp radius Auto sized from the stars (px)
  is_mosaic: boolean;
  trim_fraction: number | null;  // fraction of frame trimmed as ragged mosaic edge
}

/** A coarse content-classification hint served by `…/editor/preset-suggestion`:
 * "this looks like a star cluster / nebula / galaxy — try the matching preset?".
 * `preset_id` is null when nothing is clearly one archetype (no chip shown). */
export interface PresetSuggestion {
  preset_id: string | null;  // a BUILTIN_PRESETS id, or null when unsure
  label: string | null;      // that preset's display label
  reason: string | null;     // short plain-language "why" (e.g. "mostly point-like stars…")
  confidence: number;        // 0..1 (0 when declined)
}

export interface Histogram {
  bins: number;
  edges: number[];
  r: number[];
  g: number[];
  b: number[];
  empty?: boolean;
  errors?: string[];
  // Live preview runs on a downscaled proxy of the (possibly huge) master.
  // proxy_scale = full_width / proxy_width (>=1); proxy_width is the proxy's
  // pixel width. Surfaced so the editor can tell the user the preview is
  // downscaled and set expectations vs the full-res export.
  proxy_scale?: number;
  proxy_width?: number;
  proxy_height?: number;
  // Dims of the *rendered* preview after the recipe's geometry ops (crop/rotate/
  // resize) reshape the frame — what the preview PNG actually measures. The editor
  // sizes its image box from these so a cropped preview fills the box instead of
  // letterboxing inside the un-cropped aspect (which mis-aligns overlays). Equal to
  // proxy_width/height when the recipe has no reshaping geometry op; absent on an
  // older backend (fall back to the proxy dims).
  render_width?: number;
  render_height?: number;
  // True when this run is a mosaic (uneven panel overlap → coverage spans a
  // range). The "Coverage leveling" op only does something on a mosaic, so the
  // editor uses this to tell the user when the control is a no-op here.
  is_mosaic?: boolean;
  // True when an enabled Deconvolution op's PSF collapses on the decimated
  // preview proxy, so the live preview understates the effect the full-res
  // export applies. Surfaced as an honest advisory (the sub-pixel blur simply
  // isn't representable on the proxy grid — see deconvUnderstatesCaption).
  deconv_preview_understates?: boolean;
  // True when an enabled Star-reduction op's star size collapses below one proxy
  // pixel on the decimated preview, so its erosion footprint clamps up and the
  // live preview *over*-reduces the stars relative to the full-res export.
  // Surfaced as an honest advisory (see starReduceOverstatesCaption).
  star_reduce_preview_overstates?: boolean;
  // Robust per-channel sky-background medians + colour-cast verdict over the
  // finished display image (sky population only, so stars/target don't pull it),
  // so the editor can show whether the background ended up neutral (see
  // skyCastCaption). Absent on an older backend.
  sky_cast?: SkyCast;
  // True when this run is already in display space (a re-opened editor export, so
  // no default stretch runs). The one-click "Neutralize background" fix only lands
  // in display space — where the cast is measured — when an explicit stretch is
  // enabled OR the run is already display-space, so the editor only offers it then.
  // Absent on an older backend (treated as false).
  already_display?: boolean;
  // Which white-balance path an enabled colour-calibration op ran on this live
  // preview (the one-click Auto recipe includes one), so the editor can show the
  // same read-out the History Info panel shows for the autonomous auto-edit (see
  // autoColorCalCaption). null/absent when no colour-cal op ran or on an older
  // backend. On the decimated proxy Gaia falls back to gray-star, so mode_used
  // here reflects what the preview actually applied.
  color_cal?: AutoColorCal | null;
}

export interface SkyCast {
  r: number | null;
  g: number | null;
  b: number | null;
  neutral: boolean;
  cast: string;
  deviation: number;
}

// Which white-balance path the unattended auto-edit ran. `mode_used` is one of
// "gray_star" | "gaia" (star-based), "background_neutral" (the too-few-stars
// fallback), or "none" (couldn't balance at all).
export interface AutoColorCal {
  mode_used: string;
  n_stars_used: number;
  notes?: string;
}

export interface PsfSuggestion {
  fwhm_px: number | null;
  psf_sigma: number | null;
}

export interface DenoiseSuggestion {
  noise_sigma: number | null;
  strength: number | null;
}

export interface SharpenSuggestion {
  fwhm_px: number | null;
  radius: number | null;
}

export interface StarSizeSuggestion {
  fwhm_px: number | null;
  size: number | null;
}

export interface LevelsSuggestion {
  /** Data-driven black/white points for the Levels op, or null when there's no
   * useful suggestion (too few finite pixels / a near-empty range). */
  black: number | null;
  white: number | null;
  /** Optional midtone (gamma) lift that lands the typical tone at a pleasant grey
   * after the black/white points; null when no meaningful lift exists. */
  gamma?: number | null;
  /** The display-space grey (0..1) the gamma lift aims for, so the UI can name the
   * goal the number solves for; null when there's no gamma suggestion. */
  gamma_target?: number | null;
}

export interface StretchSuggestion {
  /** Data-driven asinh Strength + Black point for the tone.stretch op, or null
   * when there's no useful suggestion (too few finite pixels / no dynamic range). */
  stretch: number | null;
  black: number | null;
  /** The display-space grey (0..1) the strength lands the sky median at, so the UI
   * can name the goal the number solves for; null when there's no suggestion. */
  target_bg?: number | null;
}

export interface CurveSuggestion {
  /** Ordered [x, y] control points for a gentle starting tone curve, or null when
   * there's no useful suggestion (too few finite pixels / degenerate range /
   * typical tone already at or above the target grey). */
  points: [number, number][] | null;
  /** The display-space grey (0..1) the midtone lift aims for, so the UI can name
   * the goal the curve solves for; null when there's no suggestion. */
  target_bg?: number | null;
}

export interface TrimSuggestion {
  is_mosaic: boolean;
  /** Fractional (0..1) crop rectangle for the largest well-covered area, or null
   * when there's nothing worth trimming (single-field / uniform / full-frame). */
  crop: { x0: number; y0: number; x1: number; y1: number } | null;
}

export interface CalibrationMaster {
  id: number;
  name: string;
  kind: "dark" | "flat" | "bias";
  filename: string;
  n_frames: number;
  method: string;
  exposure_s: number | null;
  gain: number | null;
  sensor_temp_c: number | null;
  bayer_pattern: string | null;
  width_px: number;
  height_px: number;
  created_utc: string;
  exists: boolean;
}

export interface CalibrationSuggestions {
  params: { exposure_s: number | null; gain: number | null; sensor_temp_c: number | null };
  dark_master_id: number | null;
  flat_master_id: number | null;
  flat_dark_master_id: number | null;
  bias_master_id: number | null;
  scores: Record<string, number>;
  n_frames: number;
}

export interface UploadResult {
  target: string;   // folder the files landed in ("" = Unsorted)
  saved: { name: string; bytes: number }[];
  skipped: { name: string; bytes: number }[];   // already present
  rejected: { name: string; reason: string }[]; // not FITS / unsafe / no room
  bytes_written: number;
  job_id: string | null;
}

function encodeRecipe(recipe: Recipe): string {
  const bytes = new TextEncoder().encode(JSON.stringify(recipe));
  let bin = "";
  bytes.forEach((b) => (bin += String.fromCharCode(b)));
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_");
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  // targets
  listTargets: () => req<Target[]>("/api/targets"),
  getTarget: (safe: string) => req<Target>(`/api/targets/${safe}`),
  createTarget: (name: string) =>
    req<Target>("/api/targets", { method: "POST", body: JSON.stringify({ name }) }),
  patchTarget: (safe: string, body: { notes?: string | null; tags?: string[] }) =>
    req<Target>(`/api/targets/${safe}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteTarget: (safe: string, removeFiles: boolean) =>
    req(`/api/targets/${safe}?remove_files=${removeFiles}`, { method: "DELETE" }),
  mergeTargets: (into: string, sources: string[]) =>
    req("/api/targets/merge", { method: "POST", body: JSON.stringify({ into, sources }) }),
  mergeSuggestions: () =>
    req<MergeSuggestion[]>("/api/targets/merge-suggestions"),
  targetThumbnailUrl: (safe: string) => `/api/targets/${safe}/thumbnail`,
  identifyTarget: (safe: string) =>
    req<ObjectInfo | null>(`/api/targets/${safe}/identify`),
  sessionRecap: (safe: string) =>
    req<SessionRecap | null>(`/api/targets/${safe}/session-recap`),
  stackHealth: (safe: string, runId?: number) =>
    req<StackHealth | null>(
      `/api/targets/${safe}/stack-health` +
        (runId != null ? `?run_id=${runId}` : ""),
    ),
  bestFrame: (safe: string) =>
    req<BestFrame>(`/api/targets/${safe}/best-frame`),
  targetNights: (safe: string) =>
    req<NightSummary[]>(`/api/targets/${safe}/nights`),
  focusTrend: (safe: string) =>
    req<FocusTrend | null>(`/api/targets/${safe}/focus-trend`),
  transparencyTrend: (safe: string) =>
    req<TransparencyTrend | null>(`/api/targets/${safe}/transparency-trend`),
  nextSession: (safe: string) =>
    req<NextSession>(`/api/plan/next-session/${safe}`),
  // Download URL for the next-session windows as a .ics calendar file (one-tap
  // "Add to calendar"). A plain href/download, not a fetch — the browser hands
  // the file to the OS calendar.
  nextSessionIcsUrl: (safe: string) =>
    `/api/plan/next-session/${safe}/calendar.ics`,
  // "Try something new tonight" — famous showpieces the user hasn't captured
  // that are well-placed tonight (empty list ⇒ the card self-hides).
  suggestTargets: () => req<SuggestResponse>(`/api/plan/suggest`),
  // Download URL for a *suggested* (not-yet-captured) showpiece's next windows as
  // a .ics calendar file. Catalog ids can contain spaces ("NGC 7000"), so encode.
  suggestIcsUrl: (catalogId: string) =>
    `/api/plan/suggest/${encodeURIComponent(catalogId)}/calendar.ics`,
  getIntegrationGoal: (safe: string) =>
    req<{ goal_s: number | null }>(`/api/targets/${safe}/integration-goal`),
  setIntegrationGoal: (safe: string, goalS: number | null) =>
    req<{ goal_s: number | null }>(`/api/targets/${safe}/integration-goal`, {
      method: "PUT",
      body: JSON.stringify({ goal_s: goalS }),
    }),

  // frames
  listFrames: (safe: string, sort = "id", order = "asc") =>
    req<Frame[]>(`/api/targets/${safe}/frames?sort=${sort}&order=${order}&limit=2000`),
  patchFrame: (safe: string, id: number, body: Record<string, unknown>) =>
    req<Frame>(`/api/targets/${safe}/frames/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  bulkFrames: (safe: string, body: Record<string, unknown>) =>
    req<{ changed: number; changed_ids: number[] }>(`/api/targets/${safe}/frames/bulk`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  // Opt-in "set this night aside": reject the accepted subs of one capture night
  // (bounded by a NightSummary's start/end). Returns the touched ids for undo.
  setAsideNight: (safe: string, start_utc: string, end_utc: string) =>
    req<{ changed: number; changed_ids: number[] }>(
      `/api/targets/${safe}/frames/set-aside-night`,
      { method: "POST", body: JSON.stringify({ start_utc, end_utc }) },
    ),
  rejectSummary: (safe: string) =>
    req<{
      counts: Record<string, number>;
      total: number;
      // Server-side plate-solve *setup* classification (v0.84.1+). Reliable for
      // the star-database case too; older backends omit it and the frontend
      // falls back to detecting it from `counts`.
      solve_setup_problem?: { kind: "astap" | "database"; frames: number } | null;
      // Plain-language grouped "why were some frames left out?" breakdown
      // (v0.159.2+). Older backends omit it, so it's optional.
      summary?: RejectionSummary;
    }>(
      `/api/targets/${safe}/frames/reject-summary`,
    ),
  autoGradePreview: (safe: string, sensitivity?: string) =>
    req<GradeReport>(
      `/api/targets/${safe}/frames/auto-grade${sensitivity ? `?sensitivity=${sensitivity}` : ""}`,
    ),
  autoGradeApply: (safe: string, sensitivity?: string) =>
    req<GradeReport>(
      `/api/targets/${safe}/frames/auto-grade/apply${sensitivity ? `?sensitivity=${sensitivity}` : ""}`,
      { method: "POST" },
    ),
  framePreviewUrl: (safe: string, id: number, size = 640, bayer?: string) =>
    `/api/targets/${safe}/frames/${id}/preview?size=${size}${bayer ? `&bayer=${bayer}` : ""}`,

  // stack
  optionsSchema: () => req<StackOptionField[]>("/api/stack/options/schema"),
  getStackDefaults: (safe: string) =>
    req<Record<string, unknown>>(`/api/targets/${safe}/stack-defaults`),
  putStackDefaults: (safe: string, body: Record<string, unknown>) =>
    req<Record<string, unknown>>(`/api/targets/${safe}/stack-defaults`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  triggerStack: (safe: string, options: Record<string, unknown>) =>
    req<{ job_id: string }>(`/api/targets/${safe}/stack`, {
      method: "POST",
      body: JSON.stringify(options),
    }),
  listStackRuns: (safe: string) => req<StackRun[]>(`/api/targets/${safe}/stack-runs`),
  deleteStackRun: (safe: string, id: number) =>
    req(`/api/targets/${safe}/stack-runs/${id}`, { method: "DELETE" }),
  // Pin a run as the target's showcase "cover" (or clear with run_id null).
  setTargetCover: (safe: string, run_id: number | null) =>
    req<Target>(`/api/targets/${safe}/cover`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id }),
    }),
  updateStackRunNotes: (safe: string, id: number, notes: string) =>
    req<{ id: number; notes: string | null }>(
      `/api/targets/${safe}/stack-runs/${id}`,
      { method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes }) }),
  stackRunInfo: (safe: string, id: number) =>
    req<StackRunInfo>(`/api/targets/${safe}/stack-runs/${id}/info`),
  stackRunOptions: (safe: string, id: number) =>
    req<{ run_id: number; options: Record<string, unknown> }>(
      `/api/targets/${safe}/stack-runs/${id}/options`),
  stackEstimate: (
    safe: string,
    opts: { drizzle?: boolean; drizzle_scale?: number; drizzle_reject?: boolean; mosaic_canvas?: string },
  ) => {
    const p = new URLSearchParams();
    if (opts.drizzle) p.set("drizzle", "true");
    if (opts.drizzle_scale != null) p.set("drizzle_scale", String(opts.drizzle_scale));
    if (opts.drizzle_reject) p.set("drizzle_reject", "true");
    if (opts.mosaic_canvas) p.set("mosaic_canvas", opts.mosaic_canvas);
    return req<StackEstimate>(`/api/targets/${safe}/stack-estimate?${p.toString()}`);
  },
  stackArtifactUrl: (
    safe: string, id: number, kind: "preview" | "jpeg" | "fits" | "tiff",
    northUp = false, nameplate = false,
  ) => {
    const base = `/api/targets/${safe}/stack-runs/${id}/${kind}`;
    if (kind !== "jpeg") return base;
    // Only the share-friendly JPEG honours north_up (rotate so North is up) and
    // nameplate (bake the acquisition-data caption footer).
    const params: string[] = [];
    if (northUp) params.push("north_up=true");
    if (nameplate) params.push("nameplate=true");
    return params.length ? `${base}?${params.join("&")}` : base;
  },
  // "Make it your wallpaper" — the finished preview cropped to a device aspect
  // (phone/desktop/square), auto-centred on the target, downloaded as a JPEG.
  stackWallpaperUrl: (
    safe: string, id: number, aspect: "phone" | "desktop" | "square",
    northUp = false,
  ) => `/api/targets/${safe}/stack-runs/${id}/wallpaper?aspect=${aspect}` +
    (northUp ? "&north_up=true" : ""),
  // "What's in this picture?" — catalog objects that fall inside a run's field.
  stackAnnotations: (safe: string, id: number) =>
    req<StackAnnotations>(`/api/targets/${safe}/stack-runs/${id}/annotations`),
  stackRenderUrl: (
    safe: string, id: number, stretch: number, black: number, northUp = false,
  ) =>
    `/api/targets/${safe}/stack-runs/${id}/render?stretch=${stretch}&black=${black}` +
    (northUp ? "&north_up=true" : ""),
  stackRenderSuggestion: (safe: string, id: number) =>
    req<{
      stretch: number | null; black: number | null; target_bg?: number;
      // The rotation (deg) that puts celestial North up, or null when the run has
      // no usable WCS / the correction is trivial (so no "North up" toggle).
      north_up_deg?: number | null;
    }>(`/api/targets/${safe}/stack-runs/${id}/render-suggestion`),
  // "One frame vs your stack" reveal — a single raw sub next to the finished
  // stack, so a beginner sees what stacking bought them.
  oneSubVsStack: (safe: string, id: number) =>
    req<{
      available: boolean;
      n_frames: number | null;
      sub_exposure_s: number | null;
      integration_s: number | null;
    }>(`/api/targets/${safe}/stack-runs/${id}/one-sub-vs-stack`),
  // The concrete "stacking cut your noise ~N×" number (lazy, best-effort — null
  // for an edited/older run or an unmeasurable image).
  oneSubVsStackNoise: (safe: string, id: number) =>
    req<{ ratio: number | null }>(
      `/api/targets/${safe}/stack-runs/${id}/one-sub-vs-stack/noise`),
  stackReferenceSubUrl: (safe: string, id: number) =>
    `/api/targets/${safe}/stack-runs/${id}/reference-sub`,
  // "Watch your picture come together" progress reel (opt-in save_progress).
  stackProgressInfo: (safe: string, id: number) =>
    req<{ available: boolean; frames: number; format?: string }>(
      `/api/targets/${safe}/stack-runs/${id}/progress-info`),
  stackProgressUrl: (safe: string, id: number) =>
    `/api/targets/${safe}/stack-runs/${id}/progress`,
  // "Night after night" cross-run deepening reel (per target, ≥2 stacks).
  deepeningReelInfo: (safe: string) =>
    req<{
      available: boolean;
      n_stacks: number;
      first_subs?: number;
      last_subs?: number;
      first_utc?: string | null;
      last_utc?: string | null;
      format?: string;
    }>(`/api/targets/${safe}/deepening-reel/info`),
  deepeningReelUrl: (safe: string) => `/api/targets/${safe}/deepening-reel`,
  saveStackPreview: (safe: string, id: number, stretch: number, black: number) =>
    req<{ ok: boolean }>(`/api/targets/${safe}/stack-runs/${id}/preview`, {
      method: "POST", body: JSON.stringify({ stretch, black }),
    }),

  // pipeline
  scan: () => req<{ job_id: string }>("/api/scan", { method: "POST", body: "{}" }),
  uploadFits: (
    fileList: File[],
    target: string,
    onProgress?: (loaded: number, total: number) => void,
  ) => {
    // Multipart upload via XHR (not fetch) so we can report *upload* progress —
    // fetch exposes no upload-progress event, and a beginner sending several GB
    // over the browser needs to see it moving. The browser still sets the
    // multipart boundary Content-Type from the FormData body.
    const form = new FormData();
    if (target.trim()) form.append("target", target.trim());
    // Send the file's folder-relative path when we have one (a folder drop bakes
    // it into ``name``; a ``webkitdirectory`` input exposes ``webkitRelativePath``)
    // so the server can keep two same-named subs from different session folders
    // distinct instead of dropping one as a duplicate.
    for (const f of fileList) form.append("files", f, f.webkitRelativePath || f.name);
    return new Promise<UploadResult>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/upload");
      if (onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) onProgress(e.loaded, e.total);
        };
      }
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText) as UploadResult);
          } catch {
            reject(new Error("The server sent back a response we couldn't read."));
          }
          return;
        }
        let detail = xhr.statusText;
        try {
          detail = JSON.parse(xhr.responseText).detail ?? detail;
        } catch {
          /* ignore — keep the status text */
        }
        reject(new Error(`${xhr.status}: ${detail}`));
      };
      xhr.onerror = () =>
        reject(new Error("Upload failed — check your connection and try again."));
      xhr.send(form);
    });
  },
  qcSolve: (safe: string) =>
    req<{ job_id: string }>(`/api/targets/${safe}/qc-solve`, { method: "POST" }),
  processTarget: (safe: string) =>
    req<{ job_id: string }>(`/api/targets/${safe}/process`, { method: "POST" }),

  // jobs
  listJobs: () => req<Job[]>("/api/jobs"),
  clearJobs: () => req<{ removed: number }>("/api/jobs/clear", { method: "POST" }),
  getJob: (id: string) => req<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => req(`/api/jobs/${id}/cancel`, { method: "POST" }),

  // settings / system
  getSettings: () => req<Settings>("/api/settings"),
  putSettings: (patch: Record<string, unknown>) =>
    req<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(patch) }),
  settingsExportUrl: () => "/api/settings/export",
  importSettings: (config: Record<string, unknown>) =>
    req<Settings>("/api/settings/import", {
      method: "POST",
      body: JSON.stringify(config),
    }),
  getSystem: () => req<SystemInfo>("/api/system"),
  astapTest: () => req<{
    ok: boolean; detail?: string | null; solved?: boolean; target?: string;
    frame?: string; ra_deg?: number | null; dec_deg?: number | null; elapsed_s?: number;
  }>("/api/system/astap-test", { method: "POST" }),
  reprocessAll: (staleOnly = false, deepRescan = false, autoEdit = false) =>
    req<{ job_id: string; already_running: boolean }>("/api/reprocess-all", {
      method: "POST",
      body: JSON.stringify({
        stale_only: staleOnly, deep_rescan: deepRescan, auto_edit: autoEdit,
      }),
    }),
  reprocessStatus: () => req<ReprocessStatus>("/api/reprocess-status"),
  autoCastSummary: () => req<AutoCastSummary>("/api/auto-cast-summary"),

  // sky viewer
  getSky: () => req<SkyData>("/api/sky"),

  // tonight — night planner. `date` (YYYY-MM-DD) plans an upcoming night instead
  // of tonight; omit it for tonight.
  getTonight: (opts?: { minAlt?: number; date?: string }) => {
    const qs = new URLSearchParams();
    if (opts?.minAlt != null) qs.set("min_alt", String(opts.minAlt));
    if (opts?.date) qs.set("date", opts.date);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return req<NightPlan>(`/api/plan/tonight${suffix}`);
  },

  // gallery
  getGallery: () => req<{ items: GalleryItem[] }>("/api/gallery"),
  // "My best pictures": the newest finished stack of every target, auto-ranked
  // best-first. Self-hides (empty items) until there are ≥2 finished pictures.
  getGalleryBest: (limit?: number) =>
    req<{ items: BestPicture[] }>(
      `/api/gallery/best${limit != null ? `?limit=${limit}` : ""}`,
    ),

  // logs
  getLogs: (level?: string, limit = 1000) =>
    req<{ logs: LogEntry[]; last_seq: number }>(
      `/api/logs?limit=${limit}${level ? `&level=${level}` : ""}`,
    ),

  // dashboard
  getStats: () => req<DashboardStats>("/api/stats"),
  getLastNight: () => req<LibrarySessionRecap | null>("/api/last-night"),
  getLibraryProgress: () => req<TargetProgress[]>("/api/library-progress"),
  getLibrarySummary: () => req<LibrarySummary>("/api/library/summary"),

  // storage / housekeeping
  getStorage: () => req<StorageInfo>("/api/storage"),
  clearCache: (safe: string, stage: "stage1" | "stage2" | "thumbs" | "all") =>
    req<{ cleared: string[] }>(`/api/targets/${safe}/cache/clear?stage=${stage}`, {
      method: "POST",
    }),
  pruneStackRuns: (safe: string, body: { keep?: number; ids?: number[] }) =>
    req<{ deleted: number[] }>(`/api/targets/${safe}/stack-runs/prune`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // seestar telescope
  getSeestarDevices: () => req<SeestarDevices>("/api/seestar/devices"),
  seestarScan: () => req<{ scanning: boolean }>("/api/seestar/scan", { method: "POST" }),
  seestarConnect: (ip: string) =>
    req<{ connected: string }>(`/api/seestar/${ip}/connect`, { method: "POST" }),
  seestarDisconnect: (ip: string) =>
    req<{ disconnected: string }>(`/api/seestar/${ip}/disconnect`, { method: "POST" }),
  seestarGoto: (ip: string, body: { ra_hours: number; dec_deg: number; target_name?: string }) =>
    req(`/api/seestar/${ip}/goto`, { method: "POST", body: JSON.stringify(body) }),
  seestarStop: (ip: string) => req(`/api/seestar/${ip}/stop`, { method: "POST" }),
  seestarPark: (ip: string) => req(`/api/seestar/${ip}/park`, { method: "POST" }),

  // editor
  editorOps: () => req<EditOp[]>("/api/editor/ops/schema"),
  psfSuggestion: (safe: string) =>
    req<PsfSuggestion>(`/api/targets/${safe}/editor/psf-suggestion`),
  sharpenSuggestion: (safe: string) =>
    req<SharpenSuggestion>(`/api/targets/${safe}/editor/sharpen-suggestion`),
  starSizeSuggestion: (safe: string) =>
    req<StarSizeSuggestion>(`/api/targets/${safe}/editor/star-size-suggestion`),
  // With no recipe/uid the bare proxy is measured (the stack's inherent noise —
  // used by the "Your data" chip + bulk apply). Passing the selected denoise op's
  // recipe+uid measures the *linear image entering that op* (any prior linear ops
  // applied), so the per-op "From your image" button reflects an upstream
  // gradient/colour op instead of ignoring it — mirroring levels/stretch/curve.
  denoiseSuggestion: (safe: string, runId: number, recipe?: Recipe, uid?: string) =>
    req<DenoiseSuggestion>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/denoise-suggestion` +
      (recipe && uid
        ? `?recipe=${encodeRecipe(recipe)}&uid=${encodeURIComponent(uid)}`
        : ""),
    ),
  trimSuggestion: (safe: string, runId: number) =>
    req<TrimSuggestion>(`/api/targets/${safe}/stack-runs/${runId}/editor/trim-suggestion`),
  levelsSuggestion: (safe: string, runId: number, recipe: Recipe, uid: string) =>
    req<LevelsSuggestion>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/levels-suggestion` +
      `?recipe=${encodeRecipe(recipe)}&uid=${encodeURIComponent(uid)}`,
    ),
  stretchSuggestion: (safe: string, runId: number, recipe: Recipe, uid: string) =>
    req<StretchSuggestion>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/stretch-suggestion` +
      `?recipe=${encodeRecipe(recipe)}&uid=${encodeURIComponent(uid)}`,
    ),
  curveSuggestion: (safe: string, runId: number, recipe: Recipe, uid: string) =>
    req<CurveSuggestion>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/curve-suggestion` +
      `?recipe=${encodeRecipe(recipe)}&uid=${encodeURIComponent(uid)}`,
    ),
  getRecipe: (safe: string, runId: number) =>
    req<Recipe>(`/api/targets/${safe}/stack-runs/${runId}/editor/recipe`),
  previousRecipe: (safe: string, runId: number) =>
    req<PreviousRecipe>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/previous-recipe`),
  autoNote: (safe: string, runId: number) =>
    req<{ note: string | null }>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/auto-note`),
  putRecipe: (safe: string, runId: number, recipe: Recipe) =>
    req<Recipe>(`/api/targets/${safe}/stack-runs/${runId}/editor/recipe`, {
      method: "PUT", body: JSON.stringify(recipe),
    }),
  editPreviewUrl: (safe: string, runId: number, recipe: Recipe, bust = 0) =>
    `/api/targets/${safe}/stack-runs/${runId}/editor/preview?recipe=${encodeRecipe(recipe)}`
    + (bust ? `&v=${bust}` : ""),
  editStarMaskUrl: (safe: string, runId: number, sizePx?: number,
                    recipe?: Recipe, uid?: string) => {
    const q = new URLSearchParams();
    if (sizePx) q.set("size_px", String(sizePx));
    // The star ops gate on the display-space image at their pipeline position, so
    // pass the recipe + selected star op uid to mask that (not the linear proxy).
    if (recipe) q.set("recipe", encodeRecipe(recipe));
    if (uid) q.set("uid", uid);
    const s = q.toString();
    return `/api/targets/${safe}/stack-runs/${runId}/editor/star-mask${s ? `?${s}` : ""}`;
  },
  editCoverageMapUrl: (safe: string, runId: number, recipe?: Recipe) => {
    // Pass the recipe so the backend applies its enabled geometry ops
    // (crop/rotate/resize) to the coverage map — then the overlay tracks the
    // reshaped preview instead of the raw full frame.
    const s = recipe ? `?recipe=${encodeRecipe(recipe)}` : "";
    return `/api/targets/${safe}/stack-runs/${runId}/editor/coverage-map${s}`;
  },
  getHistogram: (safe: string, runId: number, recipe: Recipe, signal?: AbortSignal) =>
    req<Histogram>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/histogram?recipe=${encodeRecipe(recipe)}`,
      { signal }),
  autoProcess: (safe: string, runId: number) =>
    req<Recipe>(`/api/targets/${safe}/stack-runs/${runId}/editor/auto`, { method: "POST" }),
  autoAnalysis: (safe: string, runId: number) =>
    req<AutoAnalysis>(`/api/targets/${safe}/stack-runs/${runId}/editor/auto-analysis`,
      { method: "POST" }),
  presetSuggestion: (safe: string, runId: number) =>
    req<PresetSuggestion>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/preset-suggestion`,
      { method: "POST" }),
  exportPng: (safe: string, runId: number, recipe: Recipe) =>
    req<{ job_id: string }>(`/api/targets/${safe}/stack-runs/${runId}/editor/export-png`, {
      method: "POST", body: JSON.stringify({ recipe }),
    }),
  editPngUrl: (safe: string, runId: number, jobId: string) =>
    `/api/targets/${safe}/stack-runs/${runId}/editor/png/${jobId}`,
  exportShare: (safe: string, runId: number, recipe: Recipe, nameplate = false) =>
    req<{ job_id: string }>(`/api/targets/${safe}/stack-runs/${runId}/editor/share`, {
      method: "POST", body: JSON.stringify({ recipe, nameplate }),
    }),
  editShareUrl: (safe: string, runId: number, jobId: string) =>
    `/api/targets/${safe}/stack-runs/${runId}/editor/share/${jobId}`,
  exportRun: (safe: string, runId: number, recipe: Recipe, outputName: string, tiffMode: string) =>
    req<{ job_id: string }>(`/api/targets/${safe}/stack-runs/${runId}/editor/export`, {
      method: "POST",
      body: JSON.stringify({ recipe, output_name: outputName, tiff_mode: tiffMode }),
    }),
  getAutoPreferences: () => req<AutoPreferences>("/api/editor/auto-preferences"),
  /** The profile scoped to a run's archetype (galaxy/nebula/cluster), so the
   * editor's "why Auto shifted" note reflects the target being edited. */
  getRunAutoPreferences: (safe: string, runId: number) =>
    req<AutoPreferences>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/auto-preferences`),
  sendAutoFeedback: (cue: string, ctx?: { safe: string; runId: number }) =>
    req<AutoPreferences>("/api/editor/auto-preferences/feedback", {
      method: "POST",
      body: JSON.stringify(
        ctx ? { cue, safe: ctx.safe, run_id: ctx.runId } : { cue }),
    }),
  resetAutoPreferences: () =>
    req<AutoPreferences>("/api/editor/auto-preferences", { method: "DELETE" }),
  getDefaultRecipe: () => req<DefaultRecipe>("/api/editor/default-recipe"),
  putDefaultRecipe: (ops: OpInstance[]) =>
    req<DefaultRecipe>("/api/editor/default-recipe", {
      method: "PUT", body: JSON.stringify({ ops }),
    }),
  deleteDefaultRecipe: () =>
    req<DefaultRecipe>("/api/editor/default-recipe", { method: "DELETE" }),
  listPresets: () => req<{ builtin: Preset[]; user: Preset[] }>("/api/editor/presets"),
  createPreset: (label: string, ops: OpInstance[]) =>
    req<Preset>("/api/editor/presets", { method: "POST", body: JSON.stringify({ label, ops }) }),
  deletePreset: (id: string) => req(`/api/editor/presets/${id}`, { method: "DELETE" }),
  batchApply: (body: {
    items: { safe: string; run_id: number }[];
    recipe?: Recipe; preset_id?: string; output_name?: string;
  }) => req<{ job_id: string }>("/api/editor/batch", { method: "POST", body: JSON.stringify(body) }),

  // channel combine (LRGB / RGB from mono stacks)
  channelCombine: (safe: string, body: {
    items: { safe: string; run_id: number; channel: string }[];
    output_name?: string; weights?: Record<string, number>;
  }) => req<{ job_id: string }>(`/api/targets/${safe}/channel-combine`, {
    method: "POST", body: JSON.stringify(body),
  }),

  // access control (optional HTTP Basic auth)
  authStatus: () => req<{ enabled: boolean; username: string }>("/api/auth/status"),
  setAuthPassword: (body: { password: string; username?: string }) =>
    req<{ enabled: boolean; username: string }>("/api/auth/password", {
      method: "POST", body: JSON.stringify(body),
    }),

  // calibration masters (library-level dark/flat frames)
  listCalibrationMasters: () => req<CalibrationMaster[]>("/api/calibration/masters"),
  calibrationSuggestions: (safe: string) =>
    req<CalibrationSuggestions>(`/api/targets/${safe}/calibration-suggestions`),
  buildCalibrationMaster: (body: {
    kind: string; source_dir: string; name?: string; method?: string; sigma?: number;
  }) => req<{ job_id: string }>("/api/calibration/masters", {
    method: "POST", body: JSON.stringify(body),
  }),
  deleteCalibrationMaster: (id: number) =>
    req<{ deleted: number }>(`/api/calibration/masters/${id}`, { method: "DELETE" }),
};
