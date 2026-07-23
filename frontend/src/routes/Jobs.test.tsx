import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  JobRow, JobsView, buildMasterSummary, friendlyJobError, jobKindLabel, processTargetSummary,
  reprocessSummary,
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
      cleaned: null,
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
        cleaned: null,
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
  it("explains a skip with nothing plate-solved to stack", () => {
    expect(processTargetSummary({
      stacked: false, stack_skipped_reason: "no_solved_frames",
    })).toEqual({
      line: "Checked and solved, but no frames could be plate-solved yet — "
        + "so there was nothing to stack.",
      stacked: false,
      thin: null,
      cleaned: null,
    });
  });
  it("explains a cancellation and an unknown non-stacked outcome", () => {
    expect(processTargetSummary({ stacked: false, stack_skipped_reason: "cancelled" }))
      .toEqual({ line: "Cancelled before stacking.", stacked: false, thin: null, cleaned: null });
    expect(processTargetSummary({ stacked: false }))
      .toEqual({
        line: "Finished, but no stack was produced.", stacked: false, thin: null,
        cleaned: null,
      });
  });
});
