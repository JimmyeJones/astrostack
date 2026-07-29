import { describe, expect, it, vi } from "vitest";

import type { Job } from "../../api/client";
import { isJobPollAbort, JobPollAbort, POLL_MAX_CONSECUTIVE_ERRORS, pollJobUntilDone } from "./pollJob";

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

  it("gives up when the status endpoint keeps failing", async () => {
    const getJob = vi.fn().mockRejectedValue(new Error("gone"));
    await expect(pollJobUntilDone("j1", { getJob, sleep: noSleep })).rejects.toThrow("gone");
    expect(getJob).toHaveBeenCalledTimes(POLL_MAX_CONSECUTIVE_ERRORS + 1);
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
