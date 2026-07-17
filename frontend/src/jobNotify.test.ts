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

  it("does nothing when permission is not granted", () => {
    const ctor = vi.fn();
    vi.stubGlobal("window", { Notification: ctor });
    vi.stubGlobal("Notification", Object.assign(ctor, { permission: "denied" }));
    showJobNotification(mkJob({ state: "done" }), "Stacking");
    expect(ctor).not.toHaveBeenCalled();
  });
});
