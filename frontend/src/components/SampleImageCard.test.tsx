import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SampleImageCard } from "./SampleImageCard";
import type { DashboardStats, SampleStatus } from "../api/client";
import * as client from "../api/client";

function stats(nTargets: number): DashboardStats {
  return {
    n_targets: nTargets,
    n_frames: 0,
    n_frames_accepted: 0,
    total_exposure_s: 0,
    integration_hours: 0,
    acceptance_rate: null,
    n_stack_runs: 0,
    n_targets_with_stacks: 0,
    active_jobs: 0,
    recent_stacks: [],
    disk: {},
  };
}

function sample(over: Partial<SampleStatus> = {}): SampleStatus {
  return { loaded: false, safe: null, n_frames: 0, ...over };
}

function renderCard() {
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <SampleImageCard />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("SampleImageCard", () => {
  it("offers the sample on an empty library and loads it on click", async () => {
    vi.spyOn(client.api, "getSampleStatus").mockResolvedValue(sample());
    vi.spyOn(client.api, "getStats").mockResolvedValue(stats(0));
    const load = vi.spyOn(client.api, "loadSample").mockResolvedValue(
      sample({ loaded: true, safe: "sample_orion", n_frames: 6 }),
    );
    renderCard();

    await waitFor(() =>
      expect(screen.getByText(/Try it with a sample image/i)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Try it/i }));
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
  });

  it("shows a ready + remove state once the sample is loaded", async () => {
    vi.spyOn(client.api, "getSampleStatus").mockResolvedValue(
      sample({ loaded: true, safe: "sample_orion", n_frames: 6 }),
    );
    vi.spyOn(client.api, "getStats").mockResolvedValue(stats(1));
    const remove = vi.spyOn(client.api, "removeSample").mockResolvedValue(sample());
    renderCard();

    await waitFor(() =>
      expect(screen.getByText(/Your sample target is ready/i)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Remove/i }));
    await waitFor(() => expect(remove).toHaveBeenCalledTimes(1));
  });

  it("hides entirely when there's real data and no sample", async () => {
    vi.spyOn(client.api, "getSampleStatus").mockResolvedValue(sample());
    vi.spyOn(client.api, "getStats").mockResolvedValue(stats(3));
    const { container } = renderCard();

    // Give the queries a tick to resolve, then assert nothing rendered.
    await waitFor(() => expect(client.api.getSampleStatus).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByText(/sample image/i)).not.toBeInTheDocument(),
    );
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
