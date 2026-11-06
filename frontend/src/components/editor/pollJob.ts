import type { Job } from "../../api/client";

/** Job states that mean "this job will never finish". */
const TERMINAL_FAILURES = ["error", "cancelled", "interrupted"];

/** How many *consecutive* failed status fetches to ride out before giving up.
 * The editor's export jobs are the slowest thing in the app, so a single 5xx or
 * dropped connection mid-render must not throw away a render that is still
 * running (and whose output is still downloadable when it finishes).
 *
 * It is also long enough to outlast a **container restart**, which is what a
 * full-size render of a big mosaic running the NAS out of memory looks like from
 * here: the status endpoint is unreachable (or the proxy answers 502) until the
 * app is back. Five fetches 500 ms apart gave up after ~2.5 s — well before the
 * app returned — so the editor said "Failed to fetch" instead of what happened.
 * With {@link pollErrorBackoffMs} between them, 30 failures ride out ~2.4 min,
 * after which the job reads back as `interrupted` with its restart note. */
export const POLL_MAX_CONSECUTIVE_ERRORS = 30;

/** A server that keeps *answering* 4xx (the job record is gone, the session
 * expired) is not down, and riding out a restart's worth of that is just a longer
 * spinner — those keep the short budget the ride-out always had. */
export const POLL_MAX_CONSECUTIVE_CLIENT_ERRORS = 5;

/** The longest wait between two polls while the status endpoint is failing. */
export const POLL_MAX_ERROR_BACKOFF_MS = 5000;

/** The wait before the next poll after `consecutiveErrors` failures in a row:
 * the normal interval doubled per failure, capped — a blip is retried at once,
 * a server that is down is not hammered twice a second. */
export function pollErrorBackoffMs(intervalMs: number, consecutiveErrors: number): number {
  if (consecutiveErrors <= 0) return intervalMs;
  return Math.min(intervalMs * 2 ** consecutiveErrors, Math.max(intervalMs, POLL_MAX_ERROR_BACKOFF_MS));
}

/** What a job a restart cut off (``JobManager._recover_interrupted``) means for an
 * export or render. The backend's own note is written for a stack — it advises
 * rejecting bad plate-solve frames — which is no help to someone saving a picture. */
export const RENDER_RESTARTED_MESSAGE =
  "The app restarted while this was being made, so it didn't finish — usually the NAS "
  + "running out of memory on a very large picture, or an update. Try again.";
export const RENDER_NOT_STARTED_MESSAGE =
  "The app restarted before this got its turn, so it never ran. Try again.";
/** The status endpoint stayed unreachable for the whole ride-out. */
export const POLL_LOST_CONTACT_MESSAGE =
  "Lost touch with the app while this was being made — it may be restarting. "
  + "Give it a minute, then try again.";

/** The sentence for a job that ended without finishing. Prefers the backend's
 * stable `error_kind`, then the opening words of the restart notes (an older
 * build stamped no kind), then the job's own error, then the caller's fallback. */
export function jobFailureMessage(job: Job, fallback: string): string {
  const kind = job.error_kind ?? null;
  const text = (job.error ?? "").toLowerCase();
  if (kind === "restarted" || text.startsWith("container restarted while this job was running")) {
    return RENDER_RESTARTED_MESSAGE;
  }
  if (kind === "not_started" || text.startsWith("the app restarted before this job started")) {
    return RENDER_NOT_STARTED_MESSAGE;
  }
  return job.error || fallback;
}

/** A status fetch the server *answered* with a 4xx (`req` throws "404: …") is a
 * real answer — no such job, not signed in — not an outage, so it is shown as is. */
function isClientError(e: unknown): boolean {
  return e instanceof Error && /^4\d\d: /.test(e.message);
}

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
 *  - **A restart read as "Failed to fetch".** An out-of-memory kill mid-render
 *    takes the app down for longer than the ride-out lasted, so the browser's own
 *    network error was the whole message; and when the app *was* back in time, the
 *    restart note it read back advised rejecting plate-solve frames. The ride-out
 *    now backs off long enough to see the app return, a cut-off job is named as a
 *    restart ({@link jobFailureMessage}), and a ride-out that runs dry says contact
 *    was lost rather than quoting the browser.
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
      if (isClientError(e)) {
        if (consecutiveErrors > Math.min(maxConsecutiveErrors, POLL_MAX_CONSECUTIVE_CLIENT_ERRORS)) {
          throw e as Error;
        }
      } else if (consecutiveErrors > maxConsecutiveErrors) {
        throw new Error(POLL_LOST_CONTACT_MESSAGE);
      }
    }
    if (job) {
      if (job.state === "done") return job;
      if (TERMINAL_FAILURES.includes(job.state)) {
        throw new Error(jobFailureMessage(job, failureMessage));
      }
      onProgress?.(job);
    }
    await sleep(pollErrorBackoffMs(intervalMs, consecutiveErrors));
  }
}

/** True for the abandon sentinel, so a caller can stay silent instead of showing
 * an error notification for a poll it deliberately gave up on. */
export function isJobPollAbort(e: unknown): boolean {
  return e instanceof JobPollAbort || (e as { name?: string } | null)?.name === "JobPollAbort";
}
