import type { Job } from "../../api/client";

/** Job states that mean "this job will never finish". */
const TERMINAL_FAILURES = ["error", "cancelled", "interrupted"];

/** How many *consecutive* failed status fetches to ride out before giving up.
 * The editor's export jobs are the slowest thing in the app, so a single 5xx or
 * dropped connection mid-render must not throw away a render that is still
 * running (and whose output is still downloadable when it finishes). */
export const POLL_MAX_CONSECUTIVE_ERRORS = 5;

export class JobPollAbort extends Error {
  constructor() {
    super("job polling abandoned");
    this.name = "JobPollAbort";
  }
}

export interface PollJobOptions {
  /** Fetch the job's current status. */
  getJob: (jobId: string) => Promise<Job>;
  /** Progress callback, invoked with each non-terminal poll. */
  onProgress?: (job: Job) => void;
  /** Return true to abandon the poll — wired to the component's unmount flag so a
   * finished render can't fire a surprise download on whatever page the user
   * navigated to. Rejects with {@link JobPollAbort}, which callers ignore. */
  isAbandoned?: () => boolean;
  /** Sleep between polls (injected so tests don't wait). */
  sleep?: (ms: number) => Promise<void>;
  intervalMs?: number;
  /** Message for a job that ends in a terminal failure without its own `error`. */
  failureMessage?: string;
  maxConsecutiveErrors?: number;
}

/**
 * Poll an export/render job until it finishes, and return the finished job.
 *
 * Two things the inline loops this replaces got wrong:
 *
 *  - **A transient status-fetch failure killed the whole export.** One 5xx, one
 *    dropped connection, or a concurrent "Clear finished jobs" wiping the job
 *    record made `getJob` throw, which surfaced as "PNG render failed" and
 *    discarded a render that was still running or already downloadable. Now up to
 *    `maxConsecutiveErrors` failures in a row are ridden out (a *success* resets
 *    the count), and only a persistent failure gives up.
 *  - **The loop outlived the page.** Nothing stopped it on unmount, so a poll that
 *    resolved later still ran the success handler and clicked a hidden download
 *    link — a surprise download on an unrelated screen. `isAbandoned` lets the
 *    caller cut it short, rejecting with {@link JobPollAbort} so no handler runs.
 */
export async function pollJobUntilDone(
  jobId: string,
  {
    getJob,
    onProgress,
    isAbandoned,
    sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms)),
    intervalMs = 500,
    failureMessage = "Job failed",
    maxConsecutiveErrors = POLL_MAX_CONSECUTIVE_ERRORS,
  }: PollJobOptions,
): Promise<Job> {
  let consecutiveErrors = 0;
  for (;;) {
    if (isAbandoned?.()) throw new JobPollAbort();
    let job: Job | null = null;
    try {
      job = await getJob(jobId);
      consecutiveErrors = 0;
    } catch (e) {
      consecutiveErrors += 1;
      if (consecutiveErrors > maxConsecutiveErrors) {
        throw e instanceof Error ? e : new Error(String(e));
      }
    }
    if (job) {
      if (job.state === "done") return job;
      if (TERMINAL_FAILURES.includes(job.state)) {
        throw new Error(job.error || failureMessage);
      }
      onProgress?.(job);
    }
    await sleep(intervalMs);
  }
}

/** True for the abandon sentinel, so a caller can stay silent instead of showing
 * an error notification for a poll it deliberately gave up on. */
export function isJobPollAbort(e: unknown): boolean {
  return e instanceof JobPollAbort || (e as { name?: string } | null)?.name === "JobPollAbort";
}
