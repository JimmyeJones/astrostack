import type { Job } from "../../api/client";

/** What the "Create a report for Claude" card says about its job (pure, tested). */
export function reportStatusLine(job: Job | null | undefined): string {
  if (!job) {
    return "Runs a set of read-only checks on your library and your NAS (a few minutes), "
      + "then gives you one file to send to Claude. Numbers only: no location, file "
      + "names or addresses, and nothing in your raw subs is touched.";
  }
  if (job.state === "queued") return "Waiting for the job in front of it to finish…";
  if (job.state === "running") {
    const step = job.detail || job.phase || "working";
    return `Checking your library — ${step}`;
  }
  if (job.state === "done") return "Your report is ready. Download it and drop the file into your chat with Claude.";
  if (job.state === "cancelled") return "The checks were cancelled. Whatever finished is still in the report.";
  return "Something went wrong while checking. You can still download what finished, or try again.";
}

/** Whether the download button should be offered. */
export function reportDownloadable(job: Job | null | undefined): boolean {
  return Boolean(job && ["done", "cancelled", "error", "interrupted"].includes(job.state));
}
