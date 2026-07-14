import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "./Dashboard";
import * as client from "../api/client";
import type { DashboardStats, SystemInfo } from "../api/client";

function mkStats(): DashboardStats {
  return {
    n_targets: 0, n_frames: 0, n_frames_accepted: 0, total_exposure_s: 0,
    integration_hours: 0, acceptance_rate: null, n_stack_runs: 0,
    n_targets_with_stacks: 0, active_jobs: 0, recent_stacks: [],
    disk: { free_gb: 100, total_gb: 500 },
  };
}

function mkSystem(astap: Partial<SystemInfo["astap"]>): SystemInfo {
  return {
    version: "0.0.0", data_root: "/data", cpu_count: 4, cpu_workers: 3,
    gpu_available: false,
    astap: { found: true, path: "/usr/bin/astap", star_db_found: true, ...astap },
    disk: {}, memory: {}, watcher_enabled: false,
  };
}

function renderDashboard() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("Dashboard plate-solving readiness banner", () => {
  it("warns and links to Settings when ASTAP isn't found", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({ found: false }));

    renderDashboard();

    await waitFor(() =>
      expect(screen.getByText("Plate-solving isn't set up yet")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Fix in Settings" }))
      .toHaveAttribute("href", "/settings");
  });

  it("warns about a missing star database when ASTAP is found", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem")
      .mockResolvedValue(mkSystem({ found: true, star_db_found: false }));

    renderDashboard();

    await waitFor(() =>
      expect(screen.getByText("Plate-solving needs a star database")).toBeInTheDocument());
  });

  it("shows no banner when plate-solving is set up", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));

    renderDashboard();

    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());
    expect(screen.queryByText(/Plate-solving/)).not.toBeInTheDocument();
  });

  it("stays dismissed after the user closes it", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({ found: false }));

    const { container, unmount } = renderDashboard();
    await waitFor(() =>
      expect(screen.getByText("Plate-solving isn't set up yet")).toBeInTheDocument());

    const closeBtn = container.querySelector(".mantine-Alert-closeButton");
    expect(closeBtn).not.toBeNull();
    fireEvent.click(closeBtn as Element);
    await waitFor(() =>
      expect(screen.queryByText("Plate-solving isn't set up yet")).not.toBeInTheDocument());

    // Re-mounting (a fresh visit) keeps it dismissed via localStorage.
    unmount();
    renderDashboard();
    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());
    expect(screen.queryByText("Plate-solving isn't set up yet")).not.toBeInTheDocument();
  });
});

describe("Dashboard integration stat", () => {
  it("shows an em-dash, not \"0.0h\", on a fresh empty library", async () => {
    // A first-time user lands on the Dashboard with zero integration. The card
    // must read "—" like its sibling stat cards, not a bare "0.0h" — and use the
    // shared formatIntegration units the rest of the app uses.
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));

    renderDashboard();

    await waitFor(() => expect(screen.getByText("Integration")).toBeInTheDocument());
    expect(screen.queryByText("0.0h")).not.toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("formats a real integration total with shared friendly units", async () => {
    vi.spyOn(client.api, "getStats")
      .mockResolvedValue({ ...mkStats(), integration_hours: 2.3 });
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));

    renderDashboard();

    // 2.3 h, spaced like formatIntegration everywhere else (not "2.3h").
    await waitFor(() => expect(screen.getByText("2.3 h")).toBeInTheDocument());
  });
});
