import { describe, expect, it, vi } from "vitest";

import type { Job } from "../../api/client";
import {
  isJobPollAbort, jobFailureMessage, JobPollAbort, POLL_LOST_CONTACT_MESSAGE,
  POLL_MAX_CONSECUTIVE_CLIENT_ERRORS, POLL_MAX_CONSECUTIVE_ERRORS, POLL_MAX_ERROR_BACKOFF_MS,
  pollErrorBackoffMs, pollJobUntilDone, RENDER_NOT_STARTED_MESSAGE, RENDER_RESTARTED_MESSAGE,
} from "./pollJob";

function job(state: string, extra: Partial<Job> = {}): Job {
  return {
    id: "j1", kind: "edit_png", target: "m31", state, phase: "Rendering",
    done: 1, total: 10, detail: "", created_utc: null, started_utc: null,
    finished_utc: null, error: null, result: null, ...extra,
  };
}

const noSleep = () => Promise.resolve();

describe("pollJobUntilDone", () => {
  it("returns the finished job", async () => {
    const getJob = vi.fn()
      .mockResolvedValueOnce(job("running"))
      .mockResolvedValueOnce(job("done", { result: { ok: true } }));
    const seen: number[] = [];
    const done = await pollJobUntilDone("j1", {
      getJob, sleep: noSleep, onProgress: (j) => seen.push(j.done),
    });
    expect(done.state).toBe("done");
    expect(done.result).toEqual({ ok: true });
    expect(seen).toEqual([1]);        // progress only for the non-terminal poll
  });

  it("rides out a transient status-fetch failure instead of failing the export", async () => {
    // The bug: one 5xx mid-render surfaced as "PNG render failed" and discarded a
    // render that was still running (and downloadable once finished).
    const getJob = vi.fn()
      .mockRejectedValueOnce(new Error("500 Internal Server Error"))
      .mockRejectedValueOnce(new Error("network error"))
      .mockResolvedValueOnce(job("running"))
      .mockResolvedValueOnce(job("done"));
    const done = await pollJobUntilDone("j1", { getJob, sleep: noSleep });
    expect(done.state).toBe("done");
    expect(getJob).toHaveBeenCalledTimes(4);
  });

  it("a successful poll resets the error budget", async () => {
    const getJob = vi.fn();
    for (let i = 0; i < POLL_MAX_CONSECUTIVE_ERRORS; i++) {
      getJob.mockRejectedValueOnce(new Error("blip"));
    }
    getJob.mockResolvedValueOnce(job("running"));
    for (let i = 0; i < POLL_MAX_CONSECUTIVE_ERRORS; i++) {
      getJob.mockRejectedValueOnce(new Error("blip"));
    }
    getJob.mockResolvedValueOnce(job("done"));
    await expect(pollJobUntilDone("j1", { getJob, sleep: noSleep })).resolves.toMatchObject({
      state: "done",
    });
  });

  it("gives up when the status endpoint keeps failing, saying contact was lost", async () => {
    // The browser's own "Failed to fetch" was the whole message before.
    const getJob = vi.fn().mockRejectedValue(new Error("Failed to fetch"));
    const err = await pollJobUntilDone("j1", { getJob, sleep: noSleep }).catch((e) => e);
    expect(err).toBeInstanceOf(Error);
    expect((err as Error).message).toBe(POLL_LOST_CONTACT_MESSAGE);
    expect(getJob).toHaveBeenCalledTimes(POLL_MAX_CONSECUTIVE_ERRORS + 1);
  });

  it("rides out a container restart and then names the job a restart cut off", async () => {
    // The bug: an out-of-memory kill mid-render took the app down for longer than
    // five 500 ms polls, so the editor showed "Failed to fetch"; and even when the
    // app came back in time, the restart note it read back advised rejecting
    // plate-solve frames — advice for a stack, not for saving a picture.
    const getJob = vi.fn().mockResolvedValueOnce(job("running"));
    for (let i = 0; i < 20; i++) getJob.mockRejectedValueOnce(new Error("502: Bad Gateway"));
    getJob.mockResolvedValueOnce(job("interrupted", {
      error: "Container restarted while this job was running — likely an out-of-memory "
        + "kill. If it's a big stack that keeps crashing, reject bad plate-solve frames.",
      error_kind: "restarted",
    }));
    const slept: number[] = [];
    const err = await pollJobUntilDone("j1", {
      getJob, sleep: (ms) => { slept.push(ms); return Promise.resolve(); },
      failureMessage: "PNG render failed",
    }).catch((e) => e);
    expect((err as Error).message).toBe(RENDER_RESTARTED_MESSAGE);
    expect((err as Error).message).not.toMatch(/plate-solve/);
    // Twenty failures at the 500 ms interval span well over a minute of outage —
    // the old five-poll budget spanned 2.5 s.
    expect(slept.reduce((a, b) => a + b, 0)).toBeGreaterThan(60_000);
    expect(Math.max(...slept)).toBeLessThanOrEqual(POLL_MAX_ERROR_BACKOFF_MS);
  });

  it("covers a couple of minutes of outage before giving up", () => {
    let total = 0;
    for (let n = 1; n <= POLL_MAX_CONSECUTIVE_ERRORS; n++) total += pollErrorBackoffMs(500, n);
    expect(total).toBeGreaterThan(120_000);
    expect(total).toBeLessThan(240_000);
  });

  it("backs off while failing and polls at the normal rate otherwise", () => {
    expect(pollErrorBackoffMs(500, 0)).toBe(500);
    expect(pollErrorBackoffMs(500, 1)).toBe(1000);
    expect(pollErrorBackoffMs(500, 2)).toBe(2000);
    expect(pollErrorBackoffMs(500, 10)).toBe(POLL_MAX_ERROR_BACKOFF_MS);
  });

  it("a server that keeps answering 4xx is shown as is, on the short budget", async () => {
    const getJob = vi.fn().mockRejectedValue(new Error("404: No such job"));
    await expect(pollJobUntilDone("j1", { getJob, sleep: noSleep })).rejects.toThrow(
      "404: No such job");
    expect(getJob).toHaveBeenCalledTimes(POLL_MAX_CONSECUTIVE_CLIENT_ERRORS + 1);
  });

  it("names a queued job a restart caught as one that never ran", async () => {
    const getJob = vi.fn().mockResolvedValue(job("interrupted", {
      error: "The app restarted before this job started, so it never ran and nothing "
        + "was changed. Run it again.",
      error_kind: "not_started",
    }));
    await expect(pollJobUntilDone("j1", { getJob, sleep: noSleep })).rejects.toThrow(
      RENDER_NOT_STARTED_MESSAGE);
  });

  it("recognises an older build's restart notes, which carry no kind", () => {
    expect(jobFailureMessage(job("interrupted", {
      error: "Container restarted while this job was running — likely an out-of-memory kill.",
    }), "x")).toBe(RENDER_RESTARTED_MESSAGE);
    expect(jobFailureMessage(job("interrupted", {
      error: "The app restarted before this job started, so it never ran.",
    }), "x")).toBe(RENDER_NOT_STARTED_MESSAGE);
    expect(jobFailureMessage(job("error", { error: "out of memory" }), "x")).toBe("out of memory");
    expect(jobFailureMessage(job("cancelled"), "Export failed")).toBe("Export failed");
  });

  it("surfaces a terminal job failure with the job's own error", async () => {
    const getJob = vi.fn().mockResolvedValue(job("error", { error: "out of memory" }));
    await expect(pollJobUntilDone("j1", { getJob, sleep: noSleep })).rejects.toThrow("out of memory");
  });

  it("falls back to the caller's message for a terminal failure with no error text", async () => {
    for (const state of ["error", "cancelled", "interrupted"]) {
      const getJob = vi.fn().mockResolvedValue(job(state));
      await expect(
        pollJobUntilDone("j1", { getJob, sleep: noSleep, failureMessage: "PNG render failed" }),
      ).rejects.toThrow("PNG render failed");
    }
  });

  it("abandons the poll when the caller has unmounted", async () => {
    // The bug: the loop outlived the page, so a late-finishing render still clicked
    // a hidden download link on whatever screen the user had navigated to.
    let gone = false;
    const getJob = vi.fn().mockImplementation(() => {
      gone = true;                    // user navigates away after the first poll
      return Promise.resolve(job("running"));
    });
    const err = await pollJobUntilDone("j1", {
      getJob, sleep: noSleep, isAbandoned: () => gone,
    }).catch((e) => e);
    expect(err).toBeInstanceOf(JobPollAbort);
    expect(isJobPollAbort(err)).toBe(true);
    expect(getJob).toHaveBeenCalledTimes(1);
  });

  it("does not even start once abandoned", async () => {
    const getJob = vi.fn();
    await expect(
      pollJobUntilDone("j1", { getJob, sleep: noSleep, isAbandoned: () => true }),
    ).rejects.toBeInstanceOf(JobPollAbort);
    expect(getJob).not.toHaveBeenCalled();
  });

  it("isJobPollAbort ignores ordinary errors", () => {
    expect(isJobPollAbort(new Error("nope"))).toBe(false);
    expect(isJobPollAbort(null)).toBe(false);
    expect(isJobPollAbort(undefined)).toBe(false);
  });
});
