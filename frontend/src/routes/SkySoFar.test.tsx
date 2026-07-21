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
