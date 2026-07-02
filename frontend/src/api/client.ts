// Tiny typed fetch wrapper around the AstroStack API.

import type { SkyImage, SkyStar } from "../sky/projection";

export interface SkyData {
  stars: SkyStar[];
  images: SkyImage[];
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
  notes: string | null;
  total_exposure_s?: number | null;
  reusable?: boolean;
}

export interface StackInfoCard {
  key: string;
  value: string | number | boolean;
  comment: string | null;
}

export interface StackRunInfo {
  run_id: number;
  integration_s: number | null;
  n_frames: number | null;
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

export interface Preset {
  id: string;
  label: string;
  group: string;
  ops: { id: string; params: Record<string, unknown>; enabled?: boolean; uid?: string }[];
}

export interface Histogram {
  bins: number;
  edges: number[];
  r: number[];
  g: number[];
  b: number[];
  empty?: boolean;
  errors?: string[];
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
  scores: Record<string, number>;
  n_frames: number;
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
  targetThumbnailUrl: (safe: string) => `/api/targets/${safe}/thumbnail`,

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
  rejectSummary: (safe: string) =>
    req<{ counts: Record<string, number>; total: number }>(
      `/api/targets/${safe}/frames/reject-summary`,
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
  stackArtifactUrl: (safe: string, id: number, kind: "preview" | "fits" | "tiff") =>
    `/api/targets/${safe}/stack-runs/${id}/${kind}`,
  stackRenderUrl: (safe: string, id: number, stretch: number, black: number) =>
    `/api/targets/${safe}/stack-runs/${id}/render?stretch=${stretch}&black=${black}`,
  saveStackPreview: (safe: string, id: number, stretch: number, black: number) =>
    req<{ ok: boolean }>(`/api/targets/${safe}/stack-runs/${id}/preview`, {
      method: "POST", body: JSON.stringify({ stretch, black }),
    }),

  // pipeline
  scan: () => req<{ job_id: string }>("/api/scan", { method: "POST", body: "{}" }),
  qcSolve: (safe: string) =>
    req<{ job_id: string }>(`/api/targets/${safe}/qc-solve`, { method: "POST" }),

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

  // sky viewer
  getSky: () => req<SkyData>("/api/sky"),

  // gallery
  getGallery: () => req<{ items: GalleryItem[] }>("/api/gallery"),

  // logs
  getLogs: (level?: string, limit = 1000) =>
    req<{ logs: LogEntry[]; last_seq: number }>(
      `/api/logs?limit=${limit}${level ? `&level=${level}` : ""}`,
    ),

  // dashboard
  getStats: () => req<DashboardStats>("/api/stats"),

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
  getRecipe: (safe: string, runId: number) =>
    req<Recipe>(`/api/targets/${safe}/stack-runs/${runId}/editor/recipe`),
  putRecipe: (safe: string, runId: number, recipe: Recipe) =>
    req<Recipe>(`/api/targets/${safe}/stack-runs/${runId}/editor/recipe`, {
      method: "PUT", body: JSON.stringify(recipe),
    }),
  editPreviewUrl: (safe: string, runId: number, recipe: Recipe, bust = 0) =>
    `/api/targets/${safe}/stack-runs/${runId}/editor/preview?recipe=${encodeRecipe(recipe)}`
    + (bust ? `&v=${bust}` : ""),
  getHistogram: (safe: string, runId: number, recipe: Recipe) =>
    req<Histogram>(
      `/api/targets/${safe}/stack-runs/${runId}/editor/histogram?recipe=${encodeRecipe(recipe)}`),
  autoProcess: (safe: string, runId: number) =>
    req<Recipe>(`/api/targets/${safe}/stack-runs/${runId}/editor/auto`, { method: "POST" }),
  exportPng: (safe: string, runId: number, recipe: Recipe) =>
    req<{ job_id: string }>(`/api/targets/${safe}/stack-runs/${runId}/editor/export-png`, {
      method: "POST", body: JSON.stringify({ recipe }),
    }),
  editPngUrl: (safe: string, runId: number, jobId: string) =>
    `/api/targets/${safe}/stack-runs/${runId}/editor/png/${jobId}`,
  exportRun: (safe: string, runId: number, recipe: Recipe, outputName: string, tiffMode: string) =>
    req<{ job_id: string }>(`/api/targets/${safe}/stack-runs/${runId}/editor/export`, {
      method: "POST",
      body: JSON.stringify({ recipe, output_name: outputName, tiff_mode: tiffMode }),
    }),
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
