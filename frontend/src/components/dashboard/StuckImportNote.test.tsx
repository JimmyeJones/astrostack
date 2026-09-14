import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StuckImportNote } from "./StuckImportNote";
import * as client from "../../api/client";
import type { ImportWaiting, JobQueueHealth } from "../../api/client";

function health(waiting: Partial<ImportWaiting> | null): JobQueueHealth {
  if (waiting === null) return { waiting: null };
  return {
    waiting: {
      job_id: "imp", queued_utc: "2026-09-11T01:04:48Z", waiting_hours: 70,
      n_waiting: 1, holder_id: "rep", holder_kind: "reprocess_all",
      holder_target: null, holder_hours: 96, ...waiting,
    },
  };
}

function renderNote() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><StuckImportNote /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("StuckImportNote", () => {
  it("says nothing on a healthy queue", async () => {
    vi.spyOn(client.api, "jobQueueHealth").mockResolvedValue(health(null));
    renderNote();
    await waitFor(() => expect(client.api.jobQueueHealth).toHaveBeenCalled());
    expect(screen.queryByTestId("stuck-import-note")).not.toBeInTheDocument();
  });

  it("names the holder and points at the Jobs page", async () => {
    vi.spyOn(client.api, "jobQueueHealth").mockResolvedValue(health({}));
    renderNote();
    expect(await screen.findByText("New frames are waiting to be imported"))
      .toBeInTheDocument();
    expect(screen.getByText(/Reprocessing all targets/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Jobs" }))
      .toHaveAttribute("href", "/jobs");
  });

  it("renders nothing against a backend that has no such endpoint", async () => {
    // An older backend 404s. A missing answer is not a stalled queue.
    vi.spyOn(client.api, "jobQueueHealth").mockRejectedValue(new Error("404"));
    renderNote();
    await waitFor(() => expect(client.api.jobQueueHealth).toHaveBeenCalled());
    expect(screen.queryByTestId("stuck-import-note")).not.toBeInTheDocument();
  });
});
