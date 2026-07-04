import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JobsView, reprocessSummary } from "./Jobs";
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
        <JobsView />
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
    await waitFor(() => expect(screen.getByText("stack")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Cancel job" }));

    await waitFor(() => expect(screen.getByText("job already finished")).toBeInTheDocument());
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

  it("cancels a job and refreshes the list on success", async () => {
    vi.spyOn(client.api, "listJobs")
      .mockResolvedValueOnce([mkJob()])
      .mockResolvedValueOnce([mkJob({ state: "cancelled" })]);
    const cancel = vi.spyOn(client.api, "cancelJob").mockResolvedValue(undefined as never);

    renderJobs();
    await waitFor(() => expect(screen.getByText("stack")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Cancel job" }));

    await waitFor(() => expect(cancel).toHaveBeenCalledWith("job-1"));
    await waitFor(() => expect(screen.getByText("cancelled")).toBeInTheDocument());
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
});
