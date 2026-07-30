import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FirstImageCard } from "./FirstImageCard";
import type { DashboardStats, SystemInfo } from "../../api/client";
import * as client from "../../api/client";

function sys(over: Partial<SystemInfo["astap"]> = {}): SystemInfo {
  return {
    version: "0.0.0", data_root: "/data", cpu_count: 4, cpu_workers: 3,
    gpu_available: false, disk: {}, memory: {}, watcher_enabled: true,
    astap: { found: true, path: "/usr/bin/astap", star_db_found: true, ...over },
  };
}

function stats(over: Partial<DashboardStats> = {}): DashboardStats {
  return {
    n_targets: 0, n_frames: 0, n_frames_accepted: 0, total_exposure_s: 0,
    integration_hours: 0, acceptance_rate: null, n_stack_runs: 0,
    n_targets_with_stacks: 0, active_jobs: 0, recent_stacks: [], disk: {},
    ...over,
  };
}

function mount(s: SystemInfo, st: DashboardStats) {
  vi.spyOn(client.api, "getSystem").mockResolvedValue(s);
  vi.spyOn(client.api, "getStats").mockResolvedValue(st);
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <FirstImageCard />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("FirstImageCard", () => {
  it("maps the journey for a brand-new install, with somewhere to start", async () => {
    mount(sys({ found: false }), stats());

    expect(await screen.findByTestId("first-image-card")).toBeInTheDocument();
    expect(screen.getByText("Point AstroStack at your subs")).toBeInTheDocument();
    expect(screen.getByText("Stack them into your first picture")).toBeInTheDocument();
    expect(screen.getByText("0 of 4 done")).toBeInTheDocument();
    // It leads with the one thing to do next, not all four at once.
    expect(screen.getByText(/^Next: Drop your Seestar folders/)).toBeInTheDocument();
  });

  it("ticks off what's already done and drops that step's link", async () => {
    mount(sys(), stats({ n_frames: 40, n_frames_accepted: 32 }));

    await screen.findByTestId("first-image-card");
    expect(screen.getByText("3 of 4 done")).toBeInTheDocument();
    // Only the one open step offers an action link.
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("stays off an established install that never saw a step open", async () => {
    // The owner upgrading a box with 300 stacks must not be congratulated on
    // their "first" picture: nothing was ever pending, so nothing shows.
    mount(sys(), stats({ n_frames: 9000, n_frames_accepted: 8000, n_stack_runs: 12 }));

    await waitFor(() => expect(client.api.getStats).toHaveBeenCalled());
    expect(screen.queryByTestId("first-image-card")).not.toBeInTheDocument();
  });

  it("congratulates the user who actually walked the journey here", async () => {
    localStorage.setItem("astrostack.dashboard.firstImageStarted", "1");
    mount(sys(), stats({ n_frames: 40, n_frames_accepted: 32, n_stack_runs: 1 }));

    await screen.findByTestId("first-image-card");
    expect(screen.getByText(/you've made your first picture/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "See your pictures" }))
      .toHaveAttribute("href", "/gallery");
  });

  it("remembers a mid-journey install so the well-done can reach it later", async () => {
    mount(sys(), stats({ n_frames: 40 }));

    await screen.findByTestId("first-image-card");
    await waitFor(() =>
      expect(localStorage.getItem("astrostack.dashboard.firstImageStarted")).toBe("1"));
  });

  it("goes away for good when the user hides it", async () => {
    mount(sys(), stats({ n_frames: 40 }));

    await screen.findByTestId("first-image-card");
    fireEvent.click(screen.getByRole("button", { name: "Hide this" }));

    expect(screen.queryByTestId("first-image-card")).not.toBeInTheDocument();
    expect(localStorage.getItem("astrostack.dashboard.firstImageDismissed")).toBe("1");
  });

  it("stays hidden on a later visit once dismissed", async () => {
    localStorage.setItem("astrostack.dashboard.firstImageDismissed", "1");
    mount(sys({ found: false }), stats());

    await waitFor(() => expect(client.api.getStats).toHaveBeenCalled());
    expect(screen.queryByTestId("first-image-card")).not.toBeInTheDocument();
  });

  it("renders nothing while the Dashboard's data is still loading", () => {
    vi.spyOn(client.api, "getSystem").mockReturnValue(new Promise(() => {}));
    vi.spyOn(client.api, "getStats").mockReturnValue(new Promise(() => {}));
    render(
      <MantineProvider>
        <QueryClientProvider client={new QueryClient()}>
          <MemoryRouter><FirstImageCard /></MemoryRouter>
        </QueryClientProvider>
      </MantineProvider>,
    );
    expect(screen.queryByTestId("first-image-card")).not.toBeInTheDocument();
  });
});
