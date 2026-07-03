import type { Job } from "../../api/client";

/** Plain-language progress line for the full-res PNG render job, shown under the
 * "Download full-res PNG" button while it polls (the editor's slowest action, so
 * a spinning button alone reads as "stuck" on a large mosaic). Returns null when
 * there's nothing meaningful to show yet. Pure. */
export function pngProgressLabel(job: Pick<Job, "phase" | "done" | "total" | "detail"> | null | undefined): string | null {
  if (!job) return "Rendering…";
  const phase = (job.phase || "Rendering").trim();
  const total = Number(job.total) || 0;
  const done = Number(job.done) || 0;
  if (total > 0) {
    const pct = Math.max(0, Math.min(100, Math.round((done / total) * 100)));
    return `${phase} — ${pct}%`;
  }
  return phase;
}
