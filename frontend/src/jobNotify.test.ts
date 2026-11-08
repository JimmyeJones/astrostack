import { afterEach, describe, expect, it, vi } from "vitest";
import type { Job } from "./api/client";
import {
  isJobNotifyEnabled, jobNotificationText, justFinishedJobs, notificationPermission,
  requestNotificationPermission, setJobNotifyEnabled, showJobNotification,
} from "./jobNotify";

function mkJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1", kind: "stack", target: "M 42", state: "running", phase: "",
    done: 0, total: 0, detail: "", created_utc: null, started_utc: null,
    finished_utc: null, error: null, result: null,
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  try { localStorage.clear(); } catch { /* ignore */ }
});

describe("justFinishedJobs", () => {
  it("fires when a job goes from in-progress to done or error", () => {
    const prev = [mkJob({ id: "a", state: "running" }), mkJob({ id: "b", state: "queued" })];
    const curr = [mkJob({ id: "a", state: "done" }), mkJob({ id: "b", state: "error" })];
    expect(justFinishedJobs(prev, curr).map((j) => j.id)).toEqual(["a", "b"]);
  });

  it("does not fire for a job first seen already finished (fresh page load)", () => {
    // No prior state for this job → never bursts on the first poll.
    expect(justFinishedJobs([], [mkJob({ id: "a", state: "done" })])).toEqual([]);
  });

  it("does not fire while still running, nor twice for an already-done job", () => {
    expect(justFinishedJobs(
      [mkJob({ id: "a", state: "running" })],
      [mkJob({ id: "a", state: "running" })],
    )).toEqual([]);
    expect(justFinishedJobs(
      [mkJob({ id: "a", state: "done" })],
      [mkJob({ id: "a", state: "done" })],
    )).toEqual([]);
  });

  it("fires for a job a restart cut off, running or still queued", () => {
    // The walk-away case: an overnight stack the NAS's out-of-memory restart
    // killed, and the queued job behind it that never got its turn.
    const prev = [mkJob({ id: "a", state: "running" }), mkJob({ id: "b", state: "queued" })];
    const curr = [
      mkJob({ id: "a", state: "interrupted", error_kind: "restarted" }),
      mkJob({ id: "b", state: "interrupted", error_kind: "not_started" }),
    ];
    expect(justFinishedJobs(prev, curr).map((j) => j.id)).toEqual(["a", "b"]);
    // ...but never for one first seen already interrupted (a fresh page load).
    expect(justFinishedJobs([], curr)).toEqual([]);
  });

  it("does not fire for a user-cancelled job", () => {
    expect(justFinishedJobs(
      [mkJob({ id: "a", state: "running" })],
      [mkJob({ id: "a", state: "cancelled" })],
    )).toEqual([]);
  });
});

describe("jobNotificationText", () => {
  it("phrases a successful finish with the kind label and target", () => {
    const t = jobNotificationText(mkJob({ state: "done", target: "M 42" }), "Stacking");
    expect(t.title).toMatch(/finished/i);
    expect(t.body).toBe("Stacking — M 42 finished.");
  });

  it("phrases a failure distinctly and points at the app", () => {
    const t = jobNotificationText(mkJob({ state: "error", target: null }), "Processing target");
    expect(t.title).toMatch(/failed/i);
    expect(t.body).toContain("Processing target failed");
    expect(t.body).not.toContain(" — "); // no target segment when target is null
  });
});

describe("jobNotificationText for a job a restart cut off", () => {
  it("says a running job didn't finish, not that it finished", () => {
    const t = jobNotificationText(
      mkJob({ state: "interrupted", error_kind: "restarted", target: "M 42" }), "Stacking");
    expect(t.title).toMatch(/didn't finish/i);
    expect(t.body).toContain("Stacking — M 42 didn't finish");
    expect(t.body).not.toMatch(/ finished\./);
  });

  it("says a queued job never ran", () => {
    const t = jobNotificationText(
      mkJob({ state: "interrupted", error_kind: "not_started", target: null }), "Stacking");
    expect(t.title).toMatch(/never started/i);
    expect(t.body).toContain("Stacking never ran");
  });

  it("reads an older build's kind-less interrupted job as cut off", () => {
    const t = jobNotificationText(mkJob({ state: "interrupted" }), "Stacking");
    expect(t.title).toMatch(/didn't finish/i);
  });
});

describe("preference + permission helpers", () => {
  it("persists and reads the opt-in flag", () => {
    expect(isJobNotifyEnabled()).toBe(false);
    setJobNotifyEnabled(true);
    expect(isJobNotifyEnabled()).toBe(true);
    setJobNotifyEnabled(false);
    expect(isJobNotifyEnabled()).toBe(false);
  });

  it("reports 'unsupported' when the Notification API is absent", () => {
    vi.stubGlobal("window", {}); // no Notification on window
    expect(notificationPermission()).toBe("unsupported");
  });

  it("requests permission through the browser API when present", async () => {
    const requestPermission = vi.fn().mockResolvedValue("granted");
    vi.stubGlobal("window", { Notification: { permission: "default", requestPermission } });
    vi.stubGlobal("Notification", { permission: "default", requestPermission });
    await expect(requestNotificationPermission()).resolves.toBe("granted");
    expect(requestPermission).toHaveBeenCalledOnce();
  });
});

describe("showJobNotification", () => {
  it("constructs a Notification when permission is granted", () => {
    const ctor = vi.fn();
    vi.stubGlobal("window", { Notification: ctor });
    vi.stubGlobal("Notification", Object.assign(ctor, { permission: "granted" }));
    showJobNotification(mkJob({ state: "done" }), "Stacking");
    expect(ctor).toHaveBeenCalledOnce();
    expect(ctor.mock.calls[0][0]).toMatch(/finished/i);
  });

  // The ping is for the owner who walked off to another tab, and every body ends
  // "Open AstroStack to …" — so a click on it must bring the app forward and land
  // on the job, not just dismiss the notification.
  it("clicking the notification focuses the app, opens the job and closes the ping", () => {
    const close = vi.fn();
    const ctor = vi.fn(function (this: { close: () => void }) {
      this.close = close;
    });
    const focus = vi.fn();
    vi.stubGlobal("window", { Notification: ctor, focus });
    vi.stubGlobal("Notification", Object.assign(ctor, { permission: "granted" }));
    const onOpen = vi.fn();
    showJobNotification(mkJob({ state: "done" }), "Stacking", onOpen);

    const n = ctor.mock.instances[0] as unknown as { onclick: (ev?: Event) => void };
    expect(typeof n.onclick).toBe("function");
    const preventDefault = vi.fn();
    n.onclick({ preventDefault } as unknown as Event);
    expect(preventDefault).toHaveBeenCalledOnce();
    expect(focus).toHaveBeenCalledOnce();
    expect(onOpen).toHaveBeenCalledOnce();
    expect(close).toHaveBeenCalledOnce();
  });

  it("a click still opens the job when the browser refuses focus", () => {
    const ctor = vi.fn(function (this: { close: () => void }) {
      this.close = vi.fn();
    });
    const focus = vi.fn(() => { throw new Error("focus refused"); });
    vi.stubGlobal("window", { Notification: ctor, focus });
    vi.stubGlobal("Notification", Object.assign(ctor, { permission: "granted" }));
    const onOpen = vi.fn();
    showJobNotification(mkJob({ state: "error" }), "Stacking", onOpen);
    const n = ctor.mock.instances[0] as unknown as { onclick: (ev?: Event) => void };
    expect(() => n.onclick()).not.toThrow();
    expect(onOpen).toHaveBeenCalledOnce();
  });

  it("does nothing when permission is not granted", () => {
    const ctor = vi.fn();
    vi.stubGlobal("window", { Notification: ctor });
    vi.stubGlobal("Notification", Object.assign(ctor, { permission: "denied" }));
    showJobNotification(mkJob({ state: "done" }), "Stacking");
    expect(ctor).not.toHaveBeenCalled();
  });
});
