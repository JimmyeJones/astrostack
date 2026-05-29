// Tiny typed fetch wrapper around the AstroStack API.

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
  fwhm_px: number | null;
  star_count: number | null;
  sky_adu_median: number | null;
  eccentricity_median: number | null;
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
  type: "bool" | "int" | "float" | "str" | "enum";
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
  astap: { found: boolean; path: string | null };
  disk: { total_gb?: number; used_gb?: number; free_gb?: number };
  watcher_enabled: boolean;
}

export type Settings = Record<string, unknown> & {
  resolved_incoming_dir: string;
  resolved_library_root: string;
};

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
    req<{ changed: number }>(`/api/targets/${safe}/frames/bulk`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
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
  stackArtifactUrl: (safe: string, id: number, kind: "preview" | "fits" | "tiff") =>
    `/api/targets/${safe}/stack-runs/${id}/${kind}`,

  // pipeline
  scan: () => req<{ job_id: string }>("/api/scan", { method: "POST", body: "{}" }),
  qcSolve: (safe: string) =>
    req<{ job_id: string }>(`/api/targets/${safe}/qc-solve`, { method: "POST" }),

  // jobs
  listJobs: () => req<Job[]>("/api/jobs"),
  getJob: (id: string) => req<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => req(`/api/jobs/${id}/cancel`, { method: "POST" }),

  // settings / system
  getSettings: () => req<Settings>("/api/settings"),
  putSettings: (patch: Record<string, unknown>) =>
    req<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(patch) }),
  getSystem: () => req<SystemInfo>("/api/system"),
};
