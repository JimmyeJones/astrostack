/** Opt-in "your job finished" browser notifications.
 *
 * The north-star flow: a beginner clicks "Process target" / "Stack", lands on
 * the Jobs page, switches to another browser tab (or away from the computer)
 * while it runs, and wants to be told when their picture is ready instead of
 * having to sit and watch the progress bar. This module holds the pure logic —
 * which jobs *just* finished, and the plain-language notification text — plus
 * thin wrappers over the browser Notification API and localStorage, so the UI
 * stays tiny and the interesting bits stay unit-testable.
 *
 * Off by default: nothing fires until the user turns it on *and* the browser
 * grants notification permission. It never changes any processing behaviour —
 * it only mirrors a job's finish as a desktop notification.
 */
import type { Job } from "./api/client";

// A job the user is still waiting on.
const IN_PROGRESS = new Set(["running", "queued"]);
// Terminal states worth pinging about. A user-initiated `cancelled` isn't a
// surprise (they asked for it), and `interrupted` is an app-restart artefact —
// so we only notify on a genuine finish or failure.
const NOTIFY_ON_FINISH = new Set(["done", "error"]);

const STORAGE_KEY = "astrostack.notifyOnJobFinish";

/**
 * The jobs that transitioned from in-progress to a notify-worthy terminal state
 * between two polls. Pure.
 *
 * A job only counts if it was **seen unfinished** in ``prev`` and is now
 * ``done``/``error`` in ``curr`` — so a fresh page load (no prior state) never
 * bursts a notification for jobs that were already finished when the page
 * opened, and a job that was cancelled or is still running never fires.
 */
export function justFinishedJobs(prev: Job[], curr: Job[]): Job[] {
  const prevState = new Map(prev.map((j) => [j.id, j.state]));
  return curr.filter((j) => {
    const before = prevState.get(j.id);
    return before !== undefined
      && IN_PROGRESS.has(before)
      && NOTIFY_ON_FINISH.has(j.state);
  });
}

/** Plain-language notification title + body for a just-finished job. Pure.
 *
 * ``kindLabel`` is the caller's already-humanised job-kind name (e.g.
 * "Stacking") so this module needn't import the route's label map. */
export function jobNotificationText(
  job: Job,
  kindLabel: string,
): { title: string; body: string } {
  const what = kindLabel || "A job";
  const target = job.target ? ` — ${job.target}` : "";
  if (job.state === "error") {
    return {
      title: "AstroStack: a job failed",
      body: `${what}${target} failed. Open AstroStack to see what went wrong.`,
    };
  }
  return {
    title: "AstroStack: your job finished",
    body: `${what}${target} finished.`,
  };
}

/** Whether this browser exposes the Notification API at all. */
export function notificationsSupported(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

/** Current permission, or ``"unsupported"`` where the API is absent. */
export function notificationPermission(): NotificationPermission | "unsupported" {
  return notificationsSupported() ? Notification.permission : "unsupported";
}

/** Whether the user has opted in (persisted across sessions in localStorage). */
export function isJobNotifyEnabled(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

/** Persist the opt-in preference. */
export function setJobNotifyEnabled(on: boolean): void {
  try {
    if (on) localStorage.setItem(STORAGE_KEY, "1");
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private-mode / disabled storage — the preference just won't persist. */
  }
}

/** Ask the browser for notification permission (a no-op where unsupported). */
export async function requestNotificationPermission(): Promise<
  NotificationPermission | "unsupported"
> {
  if (!notificationsSupported()) return "unsupported";
  try {
    return await Notification.requestPermission();
  } catch {
    return Notification.permission;
  }
}

/** Fire one desktop notification for a finished job, if permission is granted.
 * Best-effort: silently no-ops when unsupported or not granted, and swallows a
 * constructor throw so it can never break the polling render. */
export function showJobNotification(job: Job, kindLabel: string): void {
  if (!notificationsSupported() || Notification.permission !== "granted") return;
  const { title, body } = jobNotificationText(job, kindLabel);
  try {
    // `tag` de-dupes if the same job somehow notifies twice.
    new Notification(title, { body, tag: `astrostack-job-${job.id}` });
  } catch {
    /* some browsers throw for notifications outside a user gesture — ignore. */
  }
}
