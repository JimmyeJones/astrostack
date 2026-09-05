import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WorthMoreTimeList } from "./WorthMoreTimeList";
import * as client from "../../api/client";
import { mosaicMap } from "../../test/mosaicMapFixture";
import type { BestTonight, TonightPick } from "../../api/client";

function pick(overrides: Partial<TonightPick> = {}): TonightPick {
  return {
    safe: "M_31", name: "M 31", ra_deg: 10.68, dec_deg: 41.27,
    // The depth-only fallback never fabricates an altitude.
    altitude_now_deg: null,
    minutes_usable_left: 0, hours_captured: 0.75, frames_accepted: 90,
    noise_gain: 0.345, score: 34.5,
    // The depth-only path names no target — the row prints the name right
    // above this line, so the server leaves it out (`_have_phrase`).
    reason: "You've got 45 min so far — another hour would cut its noise about 35%.",
    ...overrides,
  };
}

function payload(overrides: Partial<BestTonight> = {}): BestTonight {
  return {
    location_source: "none",
    observer: null,
    generated_utc: "2026-01-15T22:00:00+00:00",
    dark_now: false,
    dark_minutes_left: 0,
    min_altitude_deg: 30,
    note: "Set your location in Settings and this can also tell you whether "
      + "it's up right now.",
    picks: [pick()],
    ...overrides,
  };
}

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><WorthMoreTimeList /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

// Every render asks for the lead pick's mosaic map; a single-field target is the
// `null` answer, which is what most of these tests want.
beforeEach(() => {
  vi.spyOn(client.api, "mosaicMap").mockResolvedValue(null);
});

afterEach(() => vi.restoreAllMocks());

describe("WorthMoreTimeList", () => {
  it("ranks the targets you've started, each linked and with its reason", async () => {
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(payload({
      picks: [pick(), pick({ safe: "M_42", name: "M 42", reason: "Second best." })],
    }));
    renderList();
    await waitFor(() =>
      expect(screen.getByTestId("worth-more-time")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "M 31" }))
      .toHaveAttribute("href", "/targets/M_31");
    expect(screen.getByRole("link", { name: "M 42" }))
      .toHaveAttribute("href", "/targets/M_42");
    expect(screen.getByText(/another hour would cut its noise about 35%/))
      .toBeInTheDocument();
    expect(screen.getByText("Second best.")).toBeInTheDocument();
    // The page's own alert directly above already says why nothing can be
    // placed, so the list must not repeat the backend's note under each pick.
    expect(screen.queryByText(/Set your location in Settings/)).toBeNull();
  });

  it("shows nothing at all when there's nothing to rank", async () => {
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(payload({ picks: [] }));
    renderList();
    await waitFor(() => expect(client.api.getBestTonight).toHaveBeenCalled());
    expect(screen.queryByTestId("worth-more-time")).not.toBeInTheDocument();
    expect(screen.queryByText("Worth more time")).not.toBeInTheDocument();
  });

  it("stays silent on a backend too old to know the endpoint", async () => {
    vi.spyOn(client.api, "getBestTonight").mockRejectedValue(new Error("404"));
    renderList();
    await waitFor(() => expect(client.api.getBestTonight).toHaveBeenCalled());
    expect(screen.queryByTestId("worth-more-time")).not.toBeInTheDocument();
  });

  it("tells the owner which corner of the top mosaic is thin", async () => {
    // This is the page a beginner opens to decide where to point, so "which
    // target" is only half the answer for a mosaic that fills unevenly.
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(payload({
      picks: [pick(), pick({ safe: "M_42", name: "M 42", reason: "Second best." })],
    }));
    vi.spyOn(client.api, "mosaicMap").mockResolvedValue(mosaicMap());
    renderList();
    await waitFor(() =>
      expect(screen.getByTestId("worth-more-time-aim")).toBeInTheDocument());
    expect(screen.getByTestId("worth-more-time-aim"))
      .toHaveTextContent(/Thinnest at the bottom-right/);
    // The list runs to eight rows; only the one being recommended first is
    // looked up, and only it is annotated.
    expect(screen.getAllByTestId("worth-more-time-aim")).toHaveLength(1);
    expect(client.api.mosaicMap).toHaveBeenCalledTimes(1);
    expect(client.api.mosaicMap).toHaveBeenCalledWith("M_31");
  });

  it("says nothing extra for a single-field target", async () => {
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(payload());
    renderList();
    await waitFor(() =>
      expect(screen.getByTestId("worth-more-time")).toBeInTheDocument());
    await waitFor(() => expect(client.api.mosaicMap).toHaveBeenCalled());
    expect(screen.queryByTestId("worth-more-time-aim")).toBeNull();
  });

  it("still ranks the targets when the map request fails", async () => {
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(payload());
    vi.spyOn(client.api, "mosaicMap").mockRejectedValue(new Error("404"));
    renderList();
    await waitFor(() =>
      expect(screen.getByTestId("worth-more-time")).toBeInTheDocument());
    await waitFor(() => expect(client.api.mosaicMap).toHaveBeenCalled());
    expect(screen.queryByTestId("worth-more-time-aim")).toBeNull();
    expect(screen.getByRole("link", { name: "M 31" })).toBeInTheDocument();
  });

  it("asks for no map at all when there is nothing to rank", async () => {
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(payload({ picks: [] }));
    renderList();
    await waitFor(() => expect(client.api.getBestTonight).toHaveBeenCalled());
    expect(client.api.mosaicMap).not.toHaveBeenCalled();
  });
});
