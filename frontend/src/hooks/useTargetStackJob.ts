/** Is a stack of *this* target already queued or running?
 *
 * The Target page's "Process target", "Ready to process?" and "Restack" buttons
 * (and the "Stack it again" notes) used to be busy only for the POST's few
 * milliseconds, while the card offering them stays up until the new stack
 * *finishes* — hours on a big target. A second click queued a second identical
 * whole-target stack. The server now hands back a still-queued one
 * (`already_queued`), and this hook lets the buttons say "Processing…" for as
 * long as the job is live, so the running case is covered too. Once it ends the
 * buttons come back: a deliberate restack after it is real work.
 *
 * Reads the app-wide ["jobs"] cache the header badge already polls, so it adds
 * no real load.
 */
import { useQuery } from "@tanstack/react-query";
import type { Job } from "../api/client";
import { api } from "../api/client";

/** Job kinds that (re)stack one target: the one-click process job and the
 * Stack form's own job. */
const STACK_KINDS = new Set(["process_target", "stack"]);

/** The live (queued/running) stack job of ``safe``, or ``null``. */
export function activeStackJobFor(
  jobs: readonly Job[] | null | undefined, safe: string,
): Job | null {
  return (jobs ?? []).find((j) => (
    j.target === safe && STACK_KINDS.has(j.kind)
    && (j.state === "queued" || j.state === "running")
  )) ?? null;
}

/** What a busy stack button reads, and its tooltip. */
export const STACK_BUSY_LABEL = "Processing…";
export const STACK_BUSY_TITLE =
  "This target is already being stacked — follow it on the Jobs page. "
  + "You can stack it again once it has finished.";

/** The toast after a Process/Restack click: a fresh job, or the one that was
 * already waiting its turn (a second click never queues a duplicate). */
export function processStartedMessage(
  alreadyQueued: boolean | undefined, fresh: string,
): string {
  return alreadyQueued
    ? "This target is already waiting its turn to be stacked — nothing new was "
      + "queued. Watch Jobs for progress."
    : fresh;
}

export function useTargetStackJob(safe: string): Job | null {
  const jobs = useQuery({
    queryKey: ["jobs"],
    // Wrap so the default limit applies (a bare `api.listJobs` would receive the
    // TanStack query context as its `limit` argument).
    queryFn: () => api.listJobs(),
    refetchInterval: 5_000,
    enabled: !!safe,
  });
  return activeStackJobFor(jobs.data, safe);
}
