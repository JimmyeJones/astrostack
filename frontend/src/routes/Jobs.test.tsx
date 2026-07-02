import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { JobsView } from "./Jobs";
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
