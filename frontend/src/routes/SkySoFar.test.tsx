import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SkySoFarView } from "./SkySoFar";
import * as client from "../api/client";
import type { LibrarySummary, SummaryTarget } from "../api/client";

function summaryTarget(over: Partial<SummaryTarget>): SummaryTarget {
  return {
    safe: "M42", name: "Orion Nebula", total_exposure_s: 3600,
    integration_hours: 1, n_frames_accepted: 60,
    thumbnail_url: "/api/targets/M42/thumbnail", ...over,
  };
}

function summary(over: Partial<LibrarySummary>): LibrarySummary {
  return {
    n_targets_imaged: 0, n_subs_kept: 0, total_integration_s: 0,
    integration_hours: 0, first_light_utc: null,
    longest_target: null, most_imaged_target: null, heroes: [], ...over,
  };
}

function renderPage() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><SkySoFarView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("SkySoFarView", () => {
  it("names your best night above the standouts", async () => {
    // The one thing on this page that ranks a night rather than adding it up.
    // It rides on the activity calendar the Dashboard already fetches.
    vi.spyOn(client.api, "getLibrarySummary").mockResolvedValue(summary({
      n_targets_imaged: 1, n_subs_kept: 60, total_integration_s: 3600,
      integration_hours: 1, first_light_utc: "2026-01-15T00:00:00Z",
    }));
    vi.spyOn(client.api, "getActivityCalendar").mockResolvedValue({
      start_date: "2025-08-18", end_date: "2026-08-18", months: 12,
      nights: [], n_nights: 12, total_exposure_s: 30000,
      nights_this_month: 2, best_streak_nights: 3,
      sharpest_night: {
        date: "2026-01-12", exposure_s: 5400, n_frames: 180,
        targets: ["M 42"], median_fwhm_px: 2.44, n_measured: 180,
      },
    });
    renderPage();
    expect(await screen.findByText(/Your best night · 12 Jan 2026/))
      .toBeInTheDocument();
    expect(screen.getByText("2.4 px stars")).toBeInTheDocument();
  });

  it("shows a friendly empty state when nothing has been imaged", async () => {
    vi.spyOn(client.api, "getLibrarySummary").mockResolvedValue(summary({}));
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/Nothing here yet/i)).toBeInTheDocument());
  });

  it("renders the tallies, standouts and hero grid", async () => {
    vi.spyOn(client.api, "getLibrarySummary").mockResolvedValue(summary({
      n_targets_imaged: 3,
      n_subs_kept: 180,
      total_integration_s: 7200,
      integration_hours: 2,
      first_light_utc: "2026-01-15T00:00:00Z",
      longest_target: summaryTarget({ safe: "NGC7000", name: "North America", total_exposure_s: 6000 }),
      most_imaged_target: summaryTarget({ safe: "M42", name: "Orion Nebula", n_frames_accepted: 120 }),
      heroes: [
        summaryTarget({ safe: "NGC7000", name: "North America" }),
        summaryTarget({ safe: "M42", name: "Orion Nebula" }),
      ],
    }));
    renderPage();

    await waitFor(() =>
      expect(screen.getByText("Targets imaged")).toBeInTheDocument());
    // Tallies.
    expect(screen.getByText("3")).toBeInTheDocument();  // targets imaged
    expect(screen.getByText("180")).toBeInTheDocument();  // subs kept
    expect(screen.getByText("January 2026")).toBeInTheDocument();  // first light
    // Standouts + hero grid.
    expect(screen.getByText("Your biggest project")).toBeInTheDocument();
    expect(screen.getByText("Most-imaged target")).toBeInTheDocument();
    // The hero grid links each picture to its target page.
    const heroLinks = screen.getAllByRole("link", { name: /North America/i });
    expect(heroLinks.some((a) => a.getAttribute("href") === "/targets/NGC7000")).toBe(true);
  });

  it("shows one standout card when both superlatives are the same target", async () => {
    // The one-target library — and, on a Seestar, most libraries: fixed-length
    // subs make "most integration" and "most subs kept" nearly one question, so
    // the page used to render the same picture and name twice, side by side.
    vi.spyOn(client.api, "getLibrarySummary").mockResolvedValue(summary({
      n_targets_imaged: 1, n_subs_kept: 60, total_integration_s: 3600,
      integration_hours: 1, first_light_utc: "2026-01-15T00:00:00Z",
      longest_target: summaryTarget({ safe: "M42", name: "Orion Nebula" }),
      most_imaged_target: summaryTarget({ safe: "M42", name: "Orion Nebula" }),
      heroes: [summaryTarget({ safe: "M42", name: "Orion Nebula" })],
    }));
    renderPage();

    await waitFor(() => expect(
      screen.getByText("Your biggest project — and most-imaged")).toBeInTheDocument());
    // …and only one card: the separate titles are gone, not both rendered.
    expect(screen.queryByText("Your biggest project")).not.toBeInTheDocument();
    expect(screen.queryByText("Most-imaged target")).not.toBeInTheDocument();
    // Neither figure was lost in the merge.
    expect(screen.getByText("1.0 h of integration · 60 subs kept")).toBeInTheDocument();
  });

  it("shows a no-pictures note when there are tallies but no finished stacks", async () => {
    vi.spyOn(client.api, "getLibrarySummary").mockResolvedValue(summary({
      n_targets_imaged: 1, n_subs_kept: 40, total_integration_s: 1200,
      longest_target: summaryTarget({ thumbnail_url: null }),
      heroes: [],
    }));
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/No finished pictures yet/i)).toBeInTheDocument());
  });
});
