import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  JobRow, JobsView, autoRegradedBackCount, autoRegradedBackNote, bootstrapRescueNote,
  bootstrapRescuedCount, buildMasterSummary, friendlyJobError, jobKindLabel,
  calibrationMismatchNote, missingSubsNote, readErrorsNote, storageTroubleAlert,
  pipelineSummary, processTargetSummary, qcSolveNudge, qcSolveSummary, reprocessSummary,
  skippedFolders, videoFoldersNote,
} from "./Jobs";
import * as client from "../api/client";
import type { Job } from "../api/client";

function mkJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1", kind: "stack", target: "M 42", state: "running", phase: "aligning",
    done: 3, total: 10, detail: "", created_utc: null, started_utc: null,
    finished_utc: null, error: null, result: null,
    ...overrides,
  };
}

function renderJobs() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={qc}>
        <MemoryRouter><JobsView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("JobsView", () => {
  it("shows an error notification when cancelling a job fails", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([mkJob()]);
    vi.spyOn(client.api, "cancelJob").mockRejectedValue(new Error("job already finished"));

    renderJobs();
    await waitFor(() => expect(screen.getByText("Stacking")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Cancel job" }));

    await waitFor(() => expect(screen.getByText("job already finished")).toBeInTheDocument());
  });

  it("offers a 'notify me when done' toggle that requests permission when supported", async () => {
    // jsdom has no Notification API by default; stub it as supported.
    const requestPermission = vi.fn().mockResolvedValue("granted");
    vi.stubGlobal("Notification", Object.assign(vi.fn(), { permission: "default", requestPermission }));
    try {
      vi.spyOn(client.api, "listJobs").mockResolvedValue([mkJob()]);
      renderJobs();
      await waitFor(() => expect(screen.getByText("Stacking")).toBeInTheDocument());

      const toggle = screen.getByLabelText("Notify me when done");
      expect(toggle).toBeInTheDocument();
      fireEvent.click(toggle);
      await waitFor(() => expect(requestPermission).toHaveBeenCalledOnce());
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("hides the notify toggle where the browser has no Notification API", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([mkJob()]);
    renderJobs();
    await waitFor(() => expect(screen.getByText("Stacking")).toBeInTheDocument());
    expect(screen.queryByLabelText("Notify me when done")).not.toBeInTheDocument();
  });

  it("summarises a reprocess-all batch, listing failed targets", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "rp-1", kind: "reprocess_all", target: null, state: "done",
        result: { total: 3, stacked: 2, failed: [{ target: "NGC_7000" }], cancelled: false },
      }),
    ]);
    renderJobs();
    await waitFor(() =>
      expect(screen.getByText("Restacked 2/3 targets — 1 failed.")).toBeInTheDocument());
    expect(screen.getByText("Failed: NGC_7000")).toBeInTheDocument();
  });

  it("shows a plain-language name (not the raw engine kind) for the first job a beginner sees", async () => {
    // "Scan incoming" submits a `pipeline` job and lands the user here — it must
    // never read as the raw identifier `pipeline`.
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({ kind: "pipeline", target: null }),
    ]);
    renderJobs();
    await waitFor(() =>
      expect(screen.getByText("Importing & processing new frames")).toBeInTheDocument());
    expect(screen.queryByText("pipeline")).not.toBeInTheDocument();
  });

  it("shows a plain-language failure (not the raw Python exception) for a known fatal error", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "err-1", kind: "stack", state: "error",
        error: "MemoryError: stack output canvas 8000×6000 ×2 drizzle needs ~7.2 GB "
          + "of working memory, over the ~4.0 GB budget. Reduce drizzle scale, …",
      }),
    ]);
    renderJobs();
    await waitFor(() =>
      expect(screen.getByText(/needs more memory than the budget allows/)).toBeInTheDocument());
    // The raw Python "MemoryError:" prefix is never surfaced to the user.
    expect(screen.queryByText(/MemoryError:/)).not.toBeInTheDocument();
    expect(screen.getByText(/Lower the drizzle scale/)).toBeInTheDocument();
    // The setting the advice names is reachable from the failure itself.
    expect(screen.getByRole("link", { name: /Settings/ }))
      .toHaveAttribute("href", "/settings/stacking");
  });

  it("uses the backend's error_kind even when the raw text is unrecognisable", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "err-kind", kind: "stack", state: "error",
        // Raw text a string matcher wouldn't catch; the canonical kind still does.
        error: "SomeReworded: allocation over the configured ceiling",
        error_kind: "memory_budget",
      }),
    ]);
    renderJobs();
    await waitFor(() =>
      expect(screen.getByText(/needs more memory than the budget allows/)).toBeInTheDocument());
    expect(screen.queryByText(/SomeReworded:/)).not.toBeInTheDocument();
  });

  it("falls back to the raw text for an unrecognised error", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({ id: "err-2", state: "error", error: "OSError: disk is full" }),
    ]);
    renderJobs();
    await waitFor(() =>
      expect(screen.getByText("OSError: disk is full")).toBeInTheDocument());
  });

  it("guides the user to Scan incoming when there are no jobs", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([]);
    renderJobs();
    await waitFor(() => expect(screen.getByText("No jobs running.")).toBeInTheDocument());
    expect(screen.getByText(/Scan incoming/)).toBeInTheDocument();
    // Also point the no-NAS beginner at the Library upload on-ramp.
    const uploadLink = screen.getByRole("link", { name: "Upload FITS files" });
    expect(uploadLink).toHaveAttribute("href", "/library");
  });

  it("cancels a job and refreshes the list on success", async () => {
    vi.spyOn(client.api, "listJobs")
      .mockResolvedValueOnce([mkJob()])
      .mockResolvedValueOnce([mkJob({ state: "cancelled" })]);
    const cancel = vi.spyOn(client.api, "cancelJob").mockResolvedValue(undefined as never);

    renderJobs();
    await waitFor(() => expect(screen.getByText("Stacking")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Cancel job" }));

    await waitFor(() => expect(cancel).toHaveBeenCalledWith("job-1"));
    await waitFor(() => expect(screen.getByText("cancelled")).toBeInTheDocument());
  });
});

describe("JobsView process_target result actions", () => {
  function renderJobsRouted() {
    const qc = new QueryClient();
    return render(
      <MantineProvider>
        <Notifications />
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <JobsView />
          </MemoryRouter>
        </QueryClientProvider>
      </MantineProvider>,
    );
  }

  it("deep-links 'View result' to the finished run's editor when a run id is known", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pt-1", kind: "process_target", target: "M_42", state: "done",
        result: { stacked: true, solved_accepted: 8, stack: { n_frames_used: 8, run_id: 7 } },
      }),
    ]);
    renderJobsRouted();
    const link = await screen.findByRole("link", { name: "View result" });
    expect(link).toHaveAttribute("href", "/targets/M_42/edit/7");
    expect(screen.getByText("Stacked 8 frames into a new master.")).toBeInTheDocument();
  });

  it("falls back to History when the backend didn't report a run id", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pt-2", kind: "process_target", target: "M_42", state: "done",
        result: { stacked: true, solved_accepted: 5, stack: { n_frames_used: 5 } },
      }),
    ]);
    renderJobsRouted();
    const link = await screen.findByRole("link", { name: "View result" });
    expect(link).toHaveAttribute("href", "/targets/M_42/history");
  });

  it("says when auto-grade put subs back, beside the count it dropped", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pt-back", kind: "process_target", target: "M_42", state: "done",
        result: {
          stacked: true, solved_accepted: 8, auto_graded: 2, auto_regraded_back: 1,
          stack: { n_frames_used: 8, run_id: 7 },
        },
      }),
    ]);
    renderJobsRouted();
    await screen.findByRole("link", { name: "View result" });
    expect(screen.getByText("Stacked 8 frames into a new master (auto-grade dropped 2)."))
      .toBeInTheDocument();
    expect(screen.getByText(
      "Put 1 sub back: with more of your night to compare against, it's "
      + "no longer an outlier.",
    )).toBeInTheDocument();
  });

  it("shows the 'cut your noise ~N×' payoff on a healthy finished stack", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pt-noise", kind: "process_target", target: "M_42", state: "done",
        result: { stacked: true, solved_accepted: 300, stack: { n_frames_used: 300, run_id: 9 } },
      }),
    ]);
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue({ ratio: 17.1 });
    renderJobsRouted();
    await screen.findByRole("link", { name: "View result" });
    await waitFor(() =>
      expect(client.api.oneSubVsStackNoise).toHaveBeenCalledWith("M_42", 9));
    expect(
      screen.getByText("Stacking your 300 subs cut the background noise about 17×."),
    ).toBeInTheDocument();
  });

  it("omits the noise payoff when the measurement is unavailable", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pt-null", kind: "process_target", target: "M_42", state: "done",
        result: { stacked: true, solved_accepted: 8, stack: { n_frames_used: 8, run_id: 7 } },
      }),
    ]);
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue({ ratio: null });
    renderJobsRouted();
    await screen.findByRole("link", { name: "View result" });
    await waitFor(() => expect(client.api.oneSubVsStackNoise).toHaveBeenCalled());
    expect(screen.queryByTestId("stack-noise-badge")).not.toBeInTheDocument();
  });

  it("says here — not only in History's Info panel — that a saved master was skipped", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pt-skip", kind: "process_target", target: "M_42", state: "done",
        result: { stacked: true, solved_accepted: 40, stack: { n_frames_used: 40, run_id: 12 } },
      }),
    ]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 12, integration_s: 400, n_frames: 40, cards: [],
      calibration_skipped: [
        "Your saved master dark wasn't used: it's no longer in your calibration library.",
      ],
    } as never);
    renderJobsRouted();
    await screen.findByRole("link", { name: "View result" });
    await waitFor(() =>
      expect(
        screen.getByText(/Your saved master dark wasn't used/),
      ).toBeInTheDocument());
  });

  it("offers 'Open target' (not a result link) when nothing was stacked", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pt-3", kind: "process_target", target: "M_42", state: "done",
        result: { stacked: false, stack_skipped_reason: "no_solved_frames" },
      }),
    ]);
    renderJobsRouted();
    const link = await screen.findByRole("link", { name: "Open target" });
    expect(link).toHaveAttribute("href", "/targets/M_42");
    expect(
      screen.getByText(/no frames could be plate-solved yet/),
    ).toBeInTheDocument();
  });
});

describe("buildMasterSummary", () => {
  it("reports the frame count on a clean build", () => {
    expect(buildMasterSummary({ kind: "dark", n_frames: 15, n_skipped: 0 }))
      .toBe("Built a master dark from 15 frames.");
  });

  it("singularises a one-frame build", () => {
    expect(buildMasterSummary({ kind: "bias", n_frames: 1, n_skipped: 0 }))
      .toBe("Built a master bias from 1 frame.");
  });

  it("names how many frames were set aside and why", () => {
    expect(buildMasterSummary({
      kind: "flat", n_frames: 15, n_skipped: 5,
      skipped_buckets: { "wrong size": 3, unreadable: 2 },
    })).toBe(
      "Built a master flat from 15 frames · 5 frames set aside (3 wrong size, 2 unreadable).",
    );
  });

  it("still counts set-aside frames when the buckets are absent", () => {
    expect(buildMasterSummary({ kind: "dark", n_frames: 8, n_skipped: 1 }))
      .toBe("Built a master dark from 8 frames · 1 frame set aside.");
  });

  it("falls back to 'master' when the kind is missing", () => {
    expect(buildMasterSummary({ n_frames: 4 })).toBe("Built a master master from 4 frames.");
  });

  it("explains a large set that was evenly sampled, as sufficiency not loss", () => {
    // 200 darks in, 64 combined: the beginner must not be left thinking 136
    // files failed. Says what happened and that it was enough.
    expect(buildMasterSummary({
      kind: "dark", n_frames: 64, n_skipped: 0, n_supplied: 200,
    })).toBe(
      "Built a master dark from 64 of the 200 frames you gave (evenly sampled "
      + "across the whole set — plenty for a clean master).",
    );
  });

  it("keeps the set-aside detail alongside the sampling note", () => {
    expect(buildMasterSummary({
      kind: "flat", n_frames: 64, n_skipped: 2, n_supplied: 200,
      skipped_buckets: { unreadable: 2 },
    })).toBe(
      "Built a master flat from 64 of the 200 frames you gave (evenly sampled "
      + "across the whole set — plenty for a clean master) · 2 frames set aside "
      + "(2 unreadable).",
    );
  });

  it("says nothing about sampling when nothing was sampled", () => {
    // Supplied == combined + set aside → the whole set was used; and an older
    // backend that doesn't report the supplied count reads exactly as before.
    expect(buildMasterSummary({
      kind: "dark", n_frames: 18, n_skipped: 2, n_supplied: 20,
    })).toBe("Built a master dark from 18 frames · 2 frames set aside.");
    expect(buildMasterSummary({ kind: "dark", n_frames: 15, n_skipped: 0 }))
      .toBe("Built a master dark from 15 frames.");
  });
});

describe("pipelineSummary", () => {
  it("summarises a scan that imported frames and auto-stacked some targets", () => {
    const { line, held } = pipelineSummary({
      scanned: 42, auto_stacked: ["M 42", "M 31"], auto_edited: 2,
    });
    expect(line).toBe("Imported 42 new frames · auto-stacked 2 targets · finished 2 into pictures.");
    expect(held).toEqual([]);
  });

  it("surfaces targets held back for more located subs (the invisible state)", () => {
    const { line, held } = pipelineSummary({
      scanned: 10, auto_stacked: [],
      auto_stack_held_thin: [
        { target: "M 42", frames: 2, min: 3 },
        { target: "NGC 7000", frames: 1, min: 3 },
      ],
    });
    expect(line).toBe("Imported 10 new frames · held 2 for more subs.");
    expect(held).toEqual([
      { target: "M 42", frames: 2, min: 3 },
      { target: "NGC 7000", frames: 1, min: 3 },
    ]);
  });

  it("reads 'No new frames' and singularises one target / one picture", () => {
    expect(pipelineSummary({ scanned: 0, auto_stacked: ["M 42"], auto_edited: 1 }).line)
      .toBe("No new frames · auto-stacked 1 target · finished 1 into a picture.");
  });

  it("counts failures across both unattended passes", () => {
    expect(pipelineSummary({
      scanned: 5, auto_stacked: ["A"],
      stack_errors: { B: "boom" }, qc_errors: { C: "bad" },
    }).line).toBe("Imported 5 new frames · auto-stacked 1 target · 2 couldn't finish.");
  });

  it("tolerates a bare/empty summary and malformed held entries", () => {
    expect(pipelineSummary({}).line).toBe("No new frames.");
    const { held } = pipelineSummary({ auto_stack_held_thin: [null, "junk", { target: "X" }] });
    expect(held).toEqual([{ target: "X", frames: 0, min: 0 }]);
  });

  it("surfaces targets held back because their subs aren't on disk", () => {
    // The walk-away path used to stack whatever it could read and publish the
    // thinner result silently — the owner's "my images turned out worse". Now
    // it holds off, and this is where a scan says so.
    const { line, heldFiles } = pipelineSummary({
      scanned: 0, auto_stacked: [],
      auto_stack_held_unreadable: [
        { target: "M 42", offered: 787, readable: 271, unreadable: 516,
          prior_best: 787, reason: "that would be a thinner stack…" },
      ],
    });
    expect(line).toBe("No new frames · held 1 — some subs aren't on disk.");
    expect(heldFiles).toEqual([
      { target: "M 42", offered: 787, readable: 271, unreadable: 516 },
    ]);
  });

  it("tolerates malformed unreadable-hold entries", () => {
    const { heldFiles } = pipelineSummary({
      auto_stack_held_unreadable: [null, "junk", { target: "X" }],
    });
    expect(heldFiles).toEqual([
      { target: "X", offered: 0, readable: 0, unreadable: 0 },
    ]);
  });

  it("says when a thin picture was re-made from the full set", () => {
    // The heal only fires when the same target already made a better picture
    // and every sub is readable again, so the scan re-stacked it once. Saying
    // so is what stops "why did it stack again with no new subs?".
    const { line, healed } = pipelineSummary({
      scanned: 0, auto_stacked: ["M 42"],
      auto_stack_healed: [{ target: "M 42", frames: 787, newest: 271, best: 787 }],
    });
    expect(line).toBe(
      "No new frames · auto-stacked 1 target · re-made 1 picture that came out thin.",
    );
    expect(healed).toEqual([
      { target: "M 42", frames: 787, newest: 271, best: 787 },
    ]);
  });

  it("tolerates malformed heal entries and says nothing when there are none", () => {
    expect(pipelineSummary({ auto_stack_healed: [null, "junk", { target: "X" }] }).healed)
      .toEqual([{ target: "X", frames: 0, newest: 0, best: 0 }]);
    const { line, healed } = pipelineSummary({ scanned: 3, auto_stacked: [] });
    expect(healed).toEqual([]);
    expect(line).not.toMatch(/came out thin/);
  });
});

describe("bootstrapRescueNote", () => {
  it("reads the single-target job's own propagated count", () => {
    expect(bootstrapRescuedCount({ bootstrap_engaged: true, bootstrap_propagated: 12 }))
      .toBe(12);
    expect(bootstrapRescueNote({ bootstrap_propagated: 12 })).toBe(
      "Located 12 more subs by combining your un-located frames into a deeper "
      + "image — they're in your stack now.",
    );
  });

  it("sums the scan's per-target map", () => {
    expect(bootstrapRescuedCount({ bootstrap_rescued: { "M 42": 8, "NGC 7000": 3 } }))
      .toBe(11);
    expect(bootstrapRescueNote({ bootstrap_rescued: { "M 42": 8, "NGC 7000": 3 } }))
      ?.toContain("Located 11 more subs");
  });

  it("singularises one rescued sub", () => {
    expect(bootstrapRescueNote({ bootstrap_propagated: 1 })).toBe(
      "Located 1 more sub by combining your un-located frames into a deeper "
      + "image — it's in your stack now.",
    );
  });

  it("stays silent when the bootstrap never engaged or rescued nothing", () => {
    expect(bootstrapRescueNote({})).toBeNull();
    expect(bootstrapRescueNote({ bootstrap_engaged: true, bootstrap_propagated: 0 }))
      .toBeNull();
    expect(bootstrapRescueNote({ bootstrap_rescued: {} })).toBeNull();
  });

  it("tolerates junk values rather than printing NaN", () => {
    expect(bootstrapRescuedCount({ bootstrap_propagated: "lots" })).toBe(0);
    expect(bootstrapRescuedCount({ bootstrap_rescued: "nope" })).toBe(0);
    expect(bootstrapRescuedCount({ bootstrap_rescued: { "M 42": "x", "M 31": 2 } }))
      .toBe(2);
  });
});

describe("qcSolveSummary", () => {
  it("states what the job checked and what it located", () => {
    expect(qcSolveSummary({
      qc_total: 42, qc_done: 42, solve_total: 42, solve_done: 42, solve_ok: 40,
    })).toBe("Checked 42 subs. Located 40 of 42 in the sky — 2 couldn't be placed.");
  });

  it("celebrates a clean sweep", () => {
    expect(qcSolveSummary({
      qc_total: 12, qc_done: 12, solve_total: 12, solve_done: 12, solve_ok: 12,
    })).toBe("Checked 12 subs. Located all 12 of them in the sky.");
  });

  it("never passes off 'attempted' as 'located'", () => {
    // solve_done reaches solve_total even when every solve failed — the honest
    // figure is solve_ok, and this is the case the whole helper exists for.
    expect(qcSolveSummary({
      qc_total: 30, qc_done: 30, solve_total: 30, solve_done: 30, solve_ok: 0,
    })).toBe("Checked 30 subs. None of the 30 could be placed in the sky.");
  });

  it("omits the located clause entirely on an older backend with no solve_ok", () => {
    expect(qcSolveSummary({
      qc_total: 8, qc_done: 8, solve_total: 8, solve_done: 8,
    })).toBe("Checked 8 subs.");
  });

  it("says so when there was nothing left to do", () => {
    expect(qcSolveSummary({
      qc_total: 0, qc_done: 0, solve_total: 0, solve_done: 0, solve_ok: 0,
    })).toBe("Everything was already checked and located — nothing new to do.");
  });

  it("singularises one sub", () => {
    expect(qcSolveSummary({ qc_total: 1, solve_total: 1, solve_ok: 1 }))
      .toBe("Checked 1 sub. Located it in the sky.");
    expect(qcSolveSummary({ qc_total: 1, solve_total: 1, solve_ok: 0 }))
      .toBe("Checked 1 sub. It couldn't be placed in the sky.");
  });

  it("stays null on a result that carries none of the counts", () => {
    expect(qcSolveSummary({})).toBeNull();
    expect(qcSolveSummary({ qc_total: "lots" })).toBeNull();
  });
});

describe("qcSolveNudge", () => {
  it("points at the deep-image rescue when most subs couldn't be placed", () => {
    expect(qcSolveNudge({ solve_total: 40, solve_ok: 3 }))
      ?.toContain("Rescue faint fields with a deep-image solve");
  });

  it("doesn't lecture over a couple of stragglers on a good night", () => {
    expect(qcSolveNudge({ solve_total: 40, solve_ok: 38 })).toBeNull();
    expect(qcSolveNudge({ solve_total: 40, solve_ok: 40 })).toBeNull();
  });

  it("stays quiet when the bootstrap already rescued them", () => {
    expect(qcSolveNudge({
      solve_total: 40, solve_ok: 3, bootstrap_propagated: 35,
    })).toBeNull();
  });

  it("stays quiet with nothing to judge", () => {
    expect(qcSolveNudge({})).toBeNull();
    expect(qcSolveNudge({ solve_total: 40 })).toBeNull();  // older backend
  });
});

describe("autoRegradedBackNote", () => {
  it("reads the single-target job's own count", () => {
    expect(autoRegradedBackCount({ auto_regraded_back: 3 })).toBe(3);
    expect(autoRegradedBackNote({ auto_regraded_back: 3 })).toBe(
      "Put 3 subs back: with more of your night to compare against, they're "
      + "no longer outliers.",
    );
  });

  it("sums the scan's per-target map", () => {
    expect(autoRegradedBackCount({ auto_regraded_back: { "M 42": 2, "M 31": 4 } }))
      .toBe(6);
    expect(autoRegradedBackNote({ auto_regraded_back: { "M 42": 2, "M 31": 4 } }))
      ?.toContain("Put 6 subs back");
  });

  it("singularises one restored sub", () => {
    expect(autoRegradedBackNote({ auto_regraded_back: 1 })).toBe(
      "Put 1 sub back: with more of your night to compare against, it's "
      + "no longer an outlier.",
    );
  });

  it("stays silent when auto-grade gave nothing back", () => {
    expect(autoRegradedBackNote({})).toBeNull();
    expect(autoRegradedBackNote({ auto_regraded_back: 0 })).toBeNull();
    expect(autoRegradedBackNote({ auto_regraded_back: {} })).toBeNull();
    // An older backend that only reports rejections says nothing either.
    expect(autoRegradedBackNote({ auto_graded: 4 })).toBeNull();
  });

  it("tolerates junk values rather than printing NaN", () => {
    expect(autoRegradedBackCount({ auto_regraded_back: "some" })).toBe(0);
    expect(autoRegradedBackCount({ auto_regraded_back: { "M 42": "x", "M 31": 2 } }))
      .toBe(2);
  });
});

describe("JobsView pipeline result actions", () => {
  function renderJobsRouted() {
    const qc = new QueryClient();
    return render(
      <MantineProvider>
        <Notifications />
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <JobsView />
          </MemoryRouter>
        </QueryClientProvider>
      </MantineProvider>,
    );
  }

  it("renders the held-for-more-subs alert with a link to the waiting target", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pl-1", kind: "pipeline", target: null, state: "done",
        result: {
          scanned: 12, auto_stacked: [],
          auto_stack_held_thin: [{ target: "M 42", frames: 2, min: 3 }],
        },
      }),
    ]);
    renderJobsRouted();
    expect(await screen.findByText(
      "Imported 12 new frames · held 1 for more subs.",
    )).toBeInTheDocument();
    expect(screen.getByText("Waiting for more of your subs to be located")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "M 42" });
    expect(link).toHaveAttribute("href", "/targets/M 42");
  });

  it("renders the subs-not-on-disk alert with the real numbers", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pl-1u", kind: "pipeline", target: null, state: "done",
        result: {
          scanned: 0, auto_stacked: [],
          auto_stack_held_unreadable: [
            { target: "M 42", offered: 787, readable: 271, unreadable: 516 },
          ],
        },
      }),
    ]);
    renderJobsRouted();
    expect(await screen.findByText(
      "Some of your subs aren't on disk right now",
    )).toBeInTheDocument();
    expect(screen.getByText(
      /516 of 787 subs couldn't be read \(271 still readable\)\./,
    )).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "M 42" }))
      .toHaveAttribute("href", "/targets/M 42");
  });

  it("renders the re-made-a-thin-picture alert with the real numbers", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pl-1h", kind: "pipeline", target: null, state: "done",
        result: {
          scanned: 0, auto_stacked: ["M 42"],
          auto_stack_healed: [
            { target: "M 42", frames: 787, newest: 271, best: 787 },
          ],
        },
      }),
    ]);
    renderJobsRouted();
    expect(await screen.findByText(
      "Re-made a picture that had come out thin",
    )).toBeInTheDocument();
    expect(screen.getByText(
      /last picture used 271 subs, this one used all 787 \(its best before was 787\)\./,
    )).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "M 42" }))
      .toHaveAttribute("href", "/targets/M 42");
  });

  it("credits the stack-then-solve rescue on a finished scan", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pl-2", kind: "pipeline", target: null, state: "done",
        result: { scanned: 40, auto_stacked: ["M 42"], bootstrap_rescued: { "M 42": 12 } },
      }),
    ]);
    renderJobsRouted();
    expect(await screen.findByText(
      "Located 12 more subs by combining your un-located frames into a deeper "
      + "image — they're in your stack now.",
    )).toBeInTheDocument();
  });

  it("says when auto-grade handed subs back on a finished scan", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pl-3", kind: "pipeline", target: null, state: "done",
        result: { scanned: 40, auto_regraded_back: { "M 42": 3 } },
      }),
    ]);
    renderJobsRouted();
    expect(await screen.findByText(
      "Put 3 subs back: with more of your night to compare against, they're "
      + "no longer outliers.",
    )).toBeInTheDocument();
  });

  it("credits the rescue on a Check & locate job that otherwise says nothing", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "qs-1", kind: "qc_solve", target: "M 42", state: "done",
        result: { qc_done: 40, bootstrap_engaged: true, bootstrap_propagated: 12 },
      }),
    ]);
    renderJobsRouted();
    expect(await screen.findByText(/Located 12 more subs/)).toBeInTheDocument();
  });

  it("says nothing about a rescue on a Check & locate job the bootstrap didn't touch", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "qs-2", kind: "qc_solve", target: "M 42", state: "done",
        result: { qc_done: 40, solve_done: 40 },
      }),
    ]);
    renderJobsRouted();
    await screen.findByText("M 42");
    expect(screen.queryByText(/Located .* more sub/)).not.toBeInTheDocument();
  });

  it("gives a Check & locate job a real outcome instead of a bare 'done'", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "qs-3", kind: "qc_solve", target: "M 42", state: "done",
        result: {
          qc_total: 42, qc_done: 42, solve_total: 42, solve_done: 42, solve_ok: 40,
        },
      }),
    ]);
    renderJobsRouted();
    expect(await screen.findByText(
      "Checked 42 subs. Located 40 of 42 in the sky — 2 couldn't be placed.",
    )).toBeInTheDocument();
    // Two stragglers out of 42 is a normal night — no lecture.
    expect(screen.queryByText(/Rescue faint fields/)).not.toBeInTheDocument();
  });

  it("nudges the deep-image rescue when a star-poor field mostly failed", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "qs-4", kind: "qc_solve", target: "M 42", state: "done",
        result: {
          qc_total: 40, qc_done: 40, solve_total: 40, solve_done: 40, solve_ok: 2,
        },
      }),
    ]);
    renderJobsRouted();
    expect(await screen.findByText(
      "Checked 40 subs. Located 2 of 40 in the sky — 38 couldn't be placed.",
    )).toBeInTheDocument();
    expect(screen.getByText(/Rescue faint fields with a deep-image solve/))
      .toBeInTheDocument();
    // ...and the switch it names is a tap away, not a hunt.
    expect(screen.getByRole("link", { name: /Plate solving/ }))
      .toHaveAttribute("href", "/settings/plate-solving");
  });

  it("adds no Settings link to a job that needs no setting changed", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "qs-5", kind: "qc_solve", target: "M 42", state: "done",
        result: {
          qc_total: 42, qc_done: 42, solve_total: 42, solve_done: 42, solve_ok: 40,
        },
      }),
    ]);
    renderJobsRouted();
    await screen.findByText(/Checked 42 subs/);
    expect(screen.queryByRole("link", { name: /Plate solving/ })).not.toBeInTheDocument();
  });
});

describe("JobsView build_master result actions", () => {
  function renderJobsRouted() {
    const qc = new QueryClient();
    return render(
      <MantineProvider>
        <Notifications />
        <QueryClientProvider client={qc}>
          <MemoryRouter>
            <JobsView />
          </MemoryRouter>
        </QueryClientProvider>
      </MantineProvider>,
    );
  }

  it("shows the plain-language build outcome with skip accounting and a masters link", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "bm-1", kind: "build_master", state: "done",
        result: {
          id: 1, name: "My Dark", kind: "dark", n_frames: 15,
          n_skipped: 2, skipped_buckets: { "wrong size": 2 },
        },
      }),
    ]);
    renderJobsRouted();
    expect(await screen.findByText(
      "Built a master dark from 15 frames · 2 frames set aside (2 wrong size).",
    )).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "View masters" });
    expect(link).toHaveAttribute("href", "/calibration");
  });
});

describe("JobRow time-left estimate", () => {
  function renderRow(job: Job, eta?: string | null) {
    return render(
      <MantineProvider>
        <MemoryRouter>
          <JobRow job={job} onCancel={() => {}} eta={eta} />
        </MemoryRouter>
      </MantineProvider>,
    );
  }

  it("shows the per-step estimate next to a running step's count", () => {
    renderRow(mkJob({ state: "running", phase: "aligning", done: 40, total: 100 }), "~2 min left");
    expect(screen.getByText(/aligning 40\/100 · ~2 min left/)).toBeInTheDocument();
  });

  it("omits the estimate when none is available yet", () => {
    renderRow(mkJob({ state: "running", phase: "aligning", done: 0, total: 100 }), null);
    expect(screen.queryByText(/left/)).not.toBeInTheDocument();
  });

  it("never shows an estimate on a queued (not-yet-started) job", () => {
    // A stale eta must not leak onto a job that isn't running.
    renderRow(mkJob({ state: "queued", phase: "", done: 0, total: 0 }), "~5 min left");
    expect(screen.queryByText(/left/)).not.toBeInTheDocument();
  });
});

describe("jobKindLabel", () => {
  it("translates every known engine job kind to plain language", () => {
    expect(jobKindLabel("pipeline")).toBe("Importing & processing new frames");
    expect(jobKindLabel("qc_solve")).toBe("Quality check & plate-solve");
    expect(jobKindLabel("process_target")).toBe("Processing target (check, solve & stack)");
    expect(jobKindLabel("stack")).toBe("Stacking");
    expect(jobKindLabel("reprocess_all")).toBe("Reprocessing all targets");
    expect(jobKindLabel("editor_png")).toBe("Rendering full-resolution PNG");
    expect(jobKindLabel("editor_export")).toBe("Exporting edited image");
    expect(jobKindLabel("editor_batch")).toBe("Batch export");
    expect(jobKindLabel("build_master")).toBe("Building calibration master");
    expect(jobKindLabel("channel_combine")).toBe("Channel combine");
  });
  it("falls back to the raw kind for an unknown job type", () => {
    expect(jobKindLabel("some_future_kind")).toBe("some_future_kind");
  });
});

describe("friendlyJobError", () => {
  it("translates the memory-budget refusal", () => {
    const r = friendlyJobError("MemoryError: stack output canvas needs ~7 GB of working memory");
    expect(r.message).toMatch(/more memory than the budget allows/);
    expect(r.next).toMatch(/drizzle scale/);
    // "raise the memory limit in Settings" names one of seven sections; carry
    // the way there rather than leaving the reader to find it.
    expect(r.action?.href).toBe("/settings/stacking");
  });

  it("offers no Settings link for an error that doesn't send you there", () => {
    expect(friendlyJobError("OSError: disk is full").action).toBeUndefined();
    expect(friendlyJobError("ValueError: no frames could be aligned").action).toBeUndefined();
  });
  it("translates 'nothing plate-solved to stack'", () => {
    expect(friendlyJobError("ValueError: no accepted, plate-solved frames to stack").message)
      .toMatch(/no accepted, plate-solved frames/);
    expect(friendlyJobError(
      "ValueError: No accepted frames are plate-solved yet. Run Plate Solve first.").next)
      .toMatch(/Quality check & plate-solve/);
  });
  it("translates an empty-alignment failure", () => {
    expect(friendlyJobError("ValueError: no frames could be aligned").message)
      .toMatch(/None of the frames could be aligned/);
    expect(friendlyJobError("ValueError: drizzle: no usable frames").message)
      .toMatch(/None of the frames could be aligned/);
  });
  it("translates a missing-WCS reference failure", () => {
    expect(friendlyJobError("ValueError: reference frame is missing WCS or dimensions").message)
      .toMatch(/reference frame isn/);
  });
  it("translates a Build-master empty-folder failure", () => {
    const r = friendlyJobError("FileNotFoundError: No FITS files found in /mnt/darks");
    expect(r.message).toMatch(/No FITS frames were found/);
    expect(r.next).toMatch(/calibration frames/);
    // Also reachable via the canonical kind.
    expect(friendlyJobError("whatever", "no_fits_in_folder").message)
      .toMatch(/No FITS frames were found/);
  });
  it("returns the raw text verbatim for anything unrecognised", () => {
    expect(friendlyJobError("OSError: disk is full")).toEqual({ message: "OSError: disk is full" });
  });
  it("prefers the backend's canonical error_kind over string matching", () => {
    // Even when the raw text is unrecognisable (e.g. reworded upstream), a known
    // kind still yields the plain-language message — reword-proof.
    const r = friendlyJobError("SomeReworded: allocation exceeded", "memory_budget");
    expect(r.message).toMatch(/more memory than the budget allows/);
    expect(r.next).toMatch(/drizzle scale/);
    expect(friendlyJobError("whatever", "no_solved_frames").message)
      .toMatch(/no accepted, plate-solved frames/);
  });
  it("falls back to string matching when error_kind is absent or unknown", () => {
    // Older backend: no kind → match the raw text.
    expect(friendlyJobError("MemoryError: needs working memory", null).message)
      .toMatch(/more memory than the budget allows/);
    // Unknown kind → still fall back to the raw text.
    expect(friendlyJobError("OSError: disk is full", "future_kind"))
      .toEqual({ message: "OSError: disk is full" });
  });
});

describe("reprocessSummary", () => {
  it("reports a clean full run", () => {
    expect(reprocessSummary({ total: 5, stacked: 5, failed: [], cancelled: false }))
      .toEqual({ line: "Restacked 5/5 targets.", failed: [] });
  });
  it("notes cancellation and failures", () => {
    expect(reprocessSummary({
      total: 4, stacked: 2, failed: [{ target: "A" }, { target: "B" }], cancelled: true,
    })).toEqual({ line: "Restacked 2/4 targets (cancelled early) — 2 failed.", failed: ["A", "B"] });
  });
  it("singularises one target and tolerates missing/garbage fields", () => {
    expect(reprocessSummary({ total: 1, stacked: 1 }))
      .toEqual({ line: "Restacked 1/1 target.", failed: [] });
    expect(reprocessSummary({}))
      .toEqual({ line: "Restacked 0/0 targets.", failed: [] });
    expect(reprocessSummary({ total: 2, stacked: 1, failed: [{ target: "X" }, {}, "junk"] }))
      .toEqual({ line: "Restacked 1/2 targets — 1 failed.", failed: ["X"] });
  });
  it("reports how many targets were skipped as already up to date", () => {
    expect(reprocessSummary({ total: 5, stacked: 2, skipped: 3, failed: [] }))
      .toEqual({ line: "Restacked 2/5 targets — 3 already up to date.", failed: [] });
    // Zero skipped is omitted; failures still appended after the skip note.
    expect(reprocessSummary({ total: 3, stacked: 1, skipped: 1, failed: [{ target: "Z" }] }))
      .toEqual({ line: "Restacked 1/3 targets — 1 already up to date — 1 failed.", failed: ["Z"] });
  });
  it("reports how many targets were deep-rescanned (QC/solve/grade) when the option was used", () => {
    expect(reprocessSummary({ total: 3, stacked: 3, rescanned: 3, failed: [] }))
      .toEqual({ line: "Restacked 3/3 targets — re-ran QC/solve/grade on 3.", failed: [] });
    // Zero rescanned (the default plain restack) omits the clause entirely.
    expect(reprocessSummary({ total: 3, stacked: 3, rescanned: 0, failed: [] }))
      .toEqual({ line: "Restacked 3/3 targets.", failed: [] });
    // Ordering: rescan note before the skip note before failures.
    expect(reprocessSummary({
      total: 4, stacked: 2, rescanned: 2, skipped: 1, failed: [{ target: "Q" }],
    })).toEqual({
      line: "Restacked 2/4 targets — re-ran QC/solve/grade on 2 — 1 already up to date — 1 failed.",
      failed: ["Q"],
    });
  });
  it("reports how many results were auto-edited when the option was used", () => {
    expect(reprocessSummary({ total: 3, stacked: 3, auto_edited: 3, failed: [] }))
      .toEqual({ line: "Restacked 3/3 targets — auto-edited 3.", failed: [] });
    // Zero auto-edited (the default) omits the clause entirely.
    expect(reprocessSummary({ total: 3, stacked: 3, auto_edited: 0, failed: [] }))
      .toEqual({ line: "Restacked 3/3 targets.", failed: [] });
    // Ordering: rescan note before auto-edit note before the skip note.
    expect(reprocessSummary({
      total: 4, stacked: 3, rescanned: 3, auto_edited: 3, skipped: 1, failed: [],
    })).toEqual({
      line: "Restacked 3/4 targets — re-ran QC/solve/grade on 3 — auto-edited 3 — 1 already up to date.",
      failed: [],
    });
  });
});

describe("processTargetSummary", () => {
  it("summarises a successful one-click process into a new master", () => {
    expect(processTargetSummary({
      stacked: true, solved_accepted: 8, stack: { n_frames_used: 8 },
    })).toEqual({
      line: "Stacked 8 frames into a new master.", stacked: true, thin: null,
      cleaned: null, storage: null, calMismatch: null,
    });
  });
  it("names the outlier clean-up a small auto-stack made with min/max", () => {
    const { cleaned } = processTargetSummary({
      stacked: true, solved_accepted: 8,
      stack: { n_frames_used: 8, rejection_mode: "min-max-reject", rejection_fraction: null },
    });
    expect(cleaned).toMatch(/only 8 subs stacked/);
    expect(cleaned).toMatch(/brightest and darkest/);
  });
  it("names a κ-σ clean-up as a percentage on a healthy stack", () => {
    const { cleaned } = processTargetSummary({
      stacked: true, solved_accepted: 40,
      stack: { n_frames_used: 40, rejection_mode: "sigma-clip", rejection_fraction: 0.012 },
    });
    expect(cleaned).toMatch(/Cleaned ~1\.2% of pixels/);
  });
  it("suppresses the clean-up note on a thin stack (the warning wins)", () => {
    const { thin, cleaned } = processTargetSummary({
      stacked: true, solved_accepted: 2,
      stack: { n_frames_used: 2, rejection_mode: "min-max-reject", rejection_fraction: null },
    });
    expect(thin?.level).toBe("thin");
    expect(cleaned).toBeNull();
  });
  it("notes auto-graded drops and singularises one frame", () => {
    const { line, stacked, thin } = processTargetSummary({
      stacked: true, solved_accepted: 1, auto_graded: 2, stack: { n_frames_used: 1 },
    });
    expect(line).toBe("Stacked 1 frame into a new master (auto-grade dropped 2).");
    expect(stacked).toBe(true);
    // A 1-frame auto-stack is the owner's "gibberish" case — flag it.
    expect(thin?.level).toBe("single");
  });
  it("falls back to solved_accepted when the stack count is missing", () => {
    expect(processTargetSummary({ stacked: true, solved_accepted: 5 }))
      .toEqual({
        line: "Stacked 5 frames into a new master.", stacked: true, thin: null,
        cleaned: null, storage: null, calMismatch: null,
      });
  });
  it("flags a thin stack (very few frames combined) so it isn't shown as a clean result", () => {
    const { line, thin } = processTargetSummary({
      stacked: true, solved_accepted: 3, stack: { n_frames_used: 3 },
    });
    expect(line).toBe("Stacked 3 frames into a new master.");
    expect(thin?.level).toBe("thin");
    expect(thin?.frames).toBe(3);
  });
  it("does not flag a healthy stack as thin", () => {
    expect(processTargetSummary({
      stacked: true, solved_accepted: 20, stack: { n_frames_used: 20 },
    }).thin).toBeNull();
  });
  it("names subs that couldn't be read at all, and how to get them back", () => {
    const { storage } = processTargetSummary({
      stacked: true, solved_accepted: 358,
      stack: { n_frames_used: 358, n_offered: 500, n_unreadable: 142 },
    });
    expect(storage?.title).toBe("Some subs couldn't be read");
    expect(storage?.message).toContain("142 of 500 subs couldn't be read");
    expect(storage?.message).toContain("connected");
  });
  it("says nothing about missing subs when every file was there", () => {
    expect(processTargetSummary({
      stacked: true, solved_accepted: 20,
      stack: { n_frames_used: 20, n_offered: 20, n_unreadable: 0 },
    }).storage).toBeNull();
    // ...or when the backend is too old to report it at all.
    expect(processTargetSummary({
      stacked: true, solved_accepted: 20, stack: { n_frames_used: 20 },
    }).storage).toBeNull();
  });
  it("explains a skip with nothing plate-solved to stack", () => {
    expect(processTargetSummary({
      stacked: false, stack_skipped_reason: "no_solved_frames",
    })).toEqual({
      line: "Checked and solved, but no frames could be plate-solved yet — "
        + "so there was nothing to stack.",
      stacked: false,
      thin: null,
      cleaned: null,
      storage: null,
      calMismatch: null,
    });
  });
  it("explains a cancellation and an unknown non-stacked outcome", () => {
    expect(processTargetSummary({ stacked: false, stack_skipped_reason: "cancelled" }))
      .toEqual({
        line: "Cancelled before stacking.", stacked: false, thin: null,
        cleaned: null, storage: null, calMismatch: null,
      });
    expect(processTargetSummary({ stacked: false }))
      .toEqual({
        line: "Finished, but no stack was produced.", stacked: false, thin: null,
        cleaned: null, storage: null, calMismatch: null,
      });
  });
});

describe("calibrationMismatchNote", () => {
  it("passes the engine's sentence through and joins several", () => {
    const exposure = "Master dark is 30s but your subs are 10s — its pedestal "
      + "will be over-subtracted on every frame.";
    const temp = "Master dark was shot at -10°C but your subs are at 5°C.";
    expect(calibrationMismatchNote([exposure])).toBe(exposure);
    expect(calibrationMismatchNote([exposure, temp])).toBe(`${exposure} ${temp}`);
  });
  it("stays silent on a healthy run, an older backend, and junk", () => {
    expect(calibrationMismatchNote([])).toBeNull();
    // An older backend omits the field entirely.
    expect(calibrationMismatchNote(undefined)).toBeNull();
    expect(calibrationMismatchNote(null)).toBeNull();
    expect(calibrationMismatchNote("not a list")).toBeNull();
    // Blanks and non-strings are dropped, not rendered as an empty warning.
    expect(calibrationMismatchNote(["  ", 7, null])).toBeNull();
  });
});

describe("processTargetSummary — calibration mismatch", () => {
  it("surfaces a master that was applied but doesn't match these subs", () => {
    const { calMismatch } = processTargetSummary({
      stacked: true, solved_accepted: 20,
      stack: {
        n_frames_used: 20,
        calibration_warnings: ["Master dark is 30s but your subs are 10s — "
          + "its pedestal will be over-subtracted on every frame."],
      },
    });
    // The line above says the stack succeeded; this is the only cue that it was
    // calibrated *wrongly* rather than not at all.
    expect(calMismatch).toContain("30s but your subs are 10s");
  });
  it("says nothing when the masters matched or the backend is older", () => {
    expect(processTargetSummary({
      stacked: true, solved_accepted: 20,
      stack: { n_frames_used: 20, calibration_warnings: [] },
    }).calMismatch).toBeNull();
    expect(processTargetSummary({
      stacked: true, solved_accepted: 20, stack: { n_frames_used: 20 },
    }).calMismatch).toBeNull();
  });
});

describe("missingSubsNote", () => {
  it("stays silent when nothing was missing or nothing was reported", () => {
    expect(missingSubsNote(0, 500)).toBeNull();
    expect(missingSubsNote(5, 0)).toBeNull();
    expect(missingSubsNote(NaN, 500)).toBeNull();
    expect(missingSubsNote(5, NaN)).toBeNull();
  });
  it("names the count, the total and the fix", () => {
    const note = missingSubsNote(1420, 5000)!;
    expect(note).toContain("1,420 of 5,000 subs couldn't be read");
    expect(note).toContain("weren't on disk");
    expect(note).toContain("scan and stack again");
  });
  it("never claims more missing subs than were offered", () => {
    expect(missingSubsNote(99, 10)).toContain("10 of 10 subs");
  });
});

describe("readErrorsNote", () => {
  it("stays silent when nothing errored or nothing was reported", () => {
    expect(readErrorsNote(0, 0, 500)).toBeNull();
    expect(readErrorsNote(5, 0, 0)).toBeNull();
    expect(readErrorsNote(NaN, 0, 500)).toBeNull();
    expect(readErrorsNote(5, 0, NaN)).toBeNull();
  });
  it("names the count and points at the drive, not the subs", () => {
    const note = readErrorsNote(7, 0, 500)!;
    expect(note).toContain("7 subs hit a read error");
    expect(note).toContain("network share");
    expect(note).not.toContain("second try");
  });
  it("says so when every blip recovered, so nothing reads as lost", () => {
    const note = readErrorsNote(3, 3, 500)!;
    expect(note).toContain("all of them read fine on the second try");
    expect(note).toContain("in your picture");
  });
  it("counts the partial recovery", () => {
    expect(readErrorsNote(9, 4, 500)!).toContain(
      "4 of them read fine on the second try");
  });
  it("uses the singular for one sub", () => {
    expect(readErrorsNote(1, 0, 500)!).toContain("1 sub hit a read error");
  });
  it("never claims more errored or recovered subs than were offered", () => {
    const note = readErrorsNote(99, 99, 10)!;
    expect(note).toContain("10 subs hit a read error");
    expect(note).toContain("all of them");
  });
});

describe("processTargetSummary read errors", () => {
  it("carries the read-error note through the stack result", () => {
    const { storage } = processTargetSummary({
      stacked: true,
      stack: { n_frames_used: 495, n_offered: 500, n_read_errors: 5,
               n_read_recovered: 2 },
    });
    expect(storage?.title).toBe("Some subs didn't read cleanly");
    expect(storage?.message).toContain("5 subs hit a read error");
    expect(storage?.message).toContain("2 of them read fine");
  });
  it("stays null on a healthy run and on an older backend", () => {
    expect(processTargetSummary({
      stacked: true, stack: { n_frames_used: 500, n_offered: 500 },
    }).storage).toBeNull();
    expect(processTargetSummary({ stacked: false }).storage).toBeNull();
  });
});

describe("storageTroubleAlert", () => {
  it("says nothing when every sub read fine", () => {
    expect(storageTroubleAlert(0, 0, 0, 500)).toBeNull();
    // …and on an older backend that reports no totals at all.
    expect(storageTroubleAlert(0, 0, 0, 0)).toBeNull();
  });

  it("is the missing-files note alone when only files were absent", () => {
    const a = storageTroubleAlert(142, 0, 0, 500)!;
    expect(a.title).toBe("Some subs couldn't be read");
    expect(a.message).toBe(missingSubsNote(142, 500));
  });

  it("is the read-error note alone when only reads failed", () => {
    const a = storageTroubleAlert(0, 5, 2, 500)!;
    expect(a.title).toBe("Some subs didn't read cleanly");
    expect(a.message).toBe(readErrorsNote(5, 2, 500));
  });

  it("folds a flaking drive's two failures into one alert, said once", () => {
    // The regression: a share that unmounts mid-scan fires both notes, and two
    // stacked yellow alerts each ending in "go check the drive" read as two
    // problems. One alert, both counts kept distinct, one fix sentence.
    const a = storageTroubleAlert(142, 5, 3, 500)!;
    expect(a.title).toBe("Trouble reading your subs");
    // Both counts survive, and the two causes stay different diagnoses.
    expect(a.message).toContain("142 of 500 subs couldn't be read at all");
    expect(a.message).toContain("their files weren't on disk");
    expect(a.message).toContain("Another 5 subs were there but hit a read error");
    expect(a.message).toContain("3 of them read fine on the second try");
    // The fix is said exactly once — that's the whole point of composing them.
    expect(a.message.match(/check the drive/g)).toHaveLength(1);
    expect(a.message.match(/scan and stack again/g)).toHaveLength(1);
    // …and it's one alert, not two notes glued together.
    expect(a.message).not.toContain("worth checking");
  });

  it("reads naturally for a single errored sub, and when all of them recovered", () => {
    expect(storageTroubleAlert(9, 1, 0, 500)!.message)
      .toContain("Another 1 sub was there but hit a read error");
    expect(storageTroubleAlert(9, 4, 4, 500)!.message)
      .toContain("all of them read fine on the second try");
  });

  it("never claims more failures than subs were offered", () => {
    const a = storageTroubleAlert(9_000, 9_000, 9_000, 10)!;
    expect(a.message).toContain("10 of 10 subs couldn't be read at all");
    expect(a.message).toContain("Another 10 subs were there");
  });
});

// A bare "<T>/" beside "<T>_sub/" is skipped as the Seestar's own on-device
// picture. Right for a finished picture, wrong for a plainly-named folder of
// the user's own subs — and it used to happen without a word.
describe("skippedFolders", () => {
  it("lists a folder holding files the device's naming can't vouch for", () => {
    expect(skippedFolders({
      skipped_folders: [{ name: "NGC 6888", n_files: 4815, n_unrecognised: 4815 }],
    })).toEqual([{ name: "NGC 6888", nFiles: 4815, nUnrecognised: 4815 }]);
  });

  it("drops a folder the device's naming fully explains", () => {
    // The backend already filters these out; the UI must not resurrect one if
    // an older or chattier backend sends it.
    expect(skippedFolders({
      skipped_folders: [{ name: "M 42", n_files: 2, n_unrecognised: 0 }],
    })).toEqual([]);
  });

  it("says nothing on an ordinary scan", () => {
    expect(skippedFolders({ scanned: 40 })).toEqual([]);
    expect(skippedFolders({ skipped_folders: [] })).toEqual([]);
  });

  it("tolerates junk rather than printing NaN or a nameless row", () => {
    expect(skippedFolders({ skipped_folders: "nope" })).toEqual([]);
    expect(skippedFolders({ skipped_folders: [null, 7, { n_files: 3 }] })).toEqual([]);
    expect(skippedFolders({
      skipped_folders: [{ name: "M 13", n_files: "lots", n_unrecognised: 2 }],
    })).toEqual([{ name: "M 13", nFiles: 0, nUnrecognised: 2 }]);
  });
});

describe("the scan's skipped-folder note", () => {
  it("names the folder, the count, and says nothing was touched", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pl-skip", kind: "pipeline", target: null, state: "done",
        result: {
          scanned: 3110,
          skipped_folders: [{ name: "NGC 6888", n_files: 4815, n_unrecognised: 4815 }],
        },
      }),
    ]);
    renderJobs();
    expect(await screen.findByText(
      "Some folders were skipped as your Seestar's own pictures",
    )).toBeInTheDocument();
    expect(screen.getByText(/NGC 6888: 4,815 files skipped/)).toBeInTheDocument();
    expect(screen.getByText(/nothing was deleted, moved or renamed/))
      .toBeInTheDocument();
  });

  it("stays out of the way on an ordinary scan", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pl-noskip", kind: "pipeline", target: null, state: "done",
        result: { scanned: 40 },
      }),
    ]);
    renderJobs();
    await screen.findByText(/40/);
    expect(screen.queryByText(
      "Some folders were skipped as your Seestar's own pictures",
    )).not.toBeInTheDocument();
  });
});

// The scanner walks past "<T>_video/" as wordlessly as it walks past the
// device's own picture — but this one has somewhere to go.
describe("videoFoldersNote", () => {
  it("names a single capture and what kind it is", () => {
    expect(videoFoldersNote({
      video_folders: [{ name: "Lunar_video", label: "Moon" }],
    })).toEqual({
      lead: 'Skipped "Lunar_video" — that\'s a Moon video, not deep-sky subs.',
      plural: false,
    });
  });

  it("stays generic when the server isn't confident of the kind", () => {
    // `label` is null for a folder whose prefix doesn't say Moon or Sun, and
    // "that's a stuff video" would be worse than saying nothing specific.
    expect(videoFoldersNote({
      video_folders: [{ name: "stuff_video", label: null }],
    })?.lead).toBe(
      'Skipped "stuff_video" — that\'s a video capture, not deep-sky subs.');
  });

  it("counts a few and lists them", () => {
    expect(videoFoldersNote({
      video_folders: [{ name: "Lunar_video" }, { name: "Solar_video" }],
    })).toEqual({
      lead: 'Skipped 2 video folders ("Lunar_video", "Solar_video") — those are '
        + "video captures, not deep-sky subs.",
      plural: true,
    });
  });

  it("stops naming them once a whole archive lands at once", () => {
    // The count stays exact; only the list is capped, so one dropped-in archive
    // can't turn a signpost into a wall of folder names.
    const note = videoFoldersNote({
      video_folders: ["a", "b", "c", "d", "e"].map((name) => ({ name })),
    });
    expect(note?.lead).toBe(
      'Skipped 5 video folders ("a", "b", "c" and 2 more) — those are video '
      + "captures, not deep-sky subs.");
    expect(note?.plural).toBe(true);
  });

  it("says nothing on an ordinary scan, or once the captures are dealt with", () => {
    expect(videoFoldersNote({ scanned: 40 })).toBeNull();
    expect(videoFoldersNote({ video_folders: [] })).toBeNull();
  });

  it("tolerates junk rather than printing a nameless folder", () => {
    expect(videoFoldersNote({ video_folders: "nope" })).toBeNull();
    expect(videoFoldersNote({ video_folders: [null, 7, { label: "Moon" }] })).toBeNull();
    expect(videoFoldersNote({
      video_folders: [{ name: "" }, { name: "Lunar_video" }],
    })?.plural).toBe(false);
  });
});

describe("the scan's video-folder signpost", () => {
  it("points at the Moon & Sun page, as one line and not an alert", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pl-video", kind: "pipeline", target: null, state: "done",
        result: {
          scanned: 40,
          video_folders: [{ name: "Lunar_video", label: "Moon" }],
        },
      }),
    ]);
    renderJobs();
    const note = await screen.findByText(
      /Skipped "Lunar_video" — that's a Moon video/);
    const link = screen.getByRole("link", { name: "Moon & Sun" });
    expect(link).toHaveAttribute("href", "/moon-sun");
    // Nothing is wrong here, so it must not look like the skipped-subs warning
    // that sits beside it — one dimmed line, never a second alert.
    expect(note.closest('[class*="mantine-Alert"]')).toBeNull();
  });

  it("stays out of the way on a scan with no video folders", async () => {
    vi.spyOn(client.api, "listJobs").mockResolvedValue([
      mkJob({
        id: "pl-novideo", kind: "pipeline", target: null, state: "done",
        result: { scanned: 40 },
      }),
    ]);
    renderJobs();
    await screen.findByText(/40/);
    expect(screen.queryByRole("link", { name: "Moon & Sun" })).not.toBeInTheDocument();
  });
});
