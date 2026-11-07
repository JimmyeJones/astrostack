import type { Job } from "../../api/client";

/** What the progress line says while the render is still **queued**. The app runs
 * one job at a time (`webapp/jobs.py::JobManager`, deliberately — two at once on a
 * RAM-capped NAS is an out-of-memory kill), so an export clicked while a stack of
 * thousands of subs is running waits for it — for hours, on this owner's library.
 * A queued job has no phase yet, and the line used to fall back to "Rendering",
 * which read as a render that had stalled rather than one that had not started. */
export const QUEUED_PROGRESS_LABEL =
  "Waiting for another job to finish first (see Jobs) — it starts right after.";

/** Plain-language progress line for the full-res PNG render job, shown under the
 * "Download full-res PNG" button while it polls (the editor's slowest action, so
 * a spinning button alone reads as "stuck" on a large mosaic). Returns null when
 * there's nothing meaningful to show yet. Pure. */
export function pngProgressLabel(
  job: (Pick<Job, "phase" | "done" | "total" | "detail"> & { state?: string | null }) | null | undefined,
): string | null {
  if (!job) return "Rendering…";
  if (job.state === "queued") return QUEUED_PROGRESS_LABEL;
  const phase = (job.phase || "Rendering").trim();
  const total = Number(job.total) || 0;
  const done = Number(job.done) || 0;
  if (total > 0) {
    const pct = Math.max(0, Math.min(100, Math.round((done / total) * 100)));
    return `${phase} — ${pct}%`;
  }
  return phase;
}
