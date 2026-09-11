import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { IntegrationTrendBadge } from "./IntegrationTrendBadge";
import type { NextBestMoveKind } from "./nextBestMove";
import type { SuggestResponse, SuggestedTarget } from "../../api/client";
import * as client from "../../api/client";

// Two measured stacks spanning a real time increase whose noise barely fell —
// integrationTrend reads this as a plateau (sky-limited, exponent ≈ 0).
const PLATEAUED = [
  { total_exposure_s: 3600, noise_sigma: 0.1 },
  { total_exposure_s: 14400, noise_sigma: 0.098 },
];
// Noise halved as time quadrupled — tracking the ideal √t, so "improving".
const IMPROVING = [
  { total_exposure_s: 3600, noise_sigma: 0.2 },
  { total_exposure_s: 14400, noise_sigma: 0.1 },
];

function suggestion(over: Partial<SuggestedTarget> = {}): SuggestedTarget {
  return {
    id: "M27",
    name: "Dumbbell Nebula",
    ra_deg: 299.9,
    dec_deg: 22.7,
    type: "planetary nebula",
    con: "Vul",
    blurb: "A bright planetary nebula in Vulpecula.",
    max_altitude_deg: 64,
    transit_utc: "2026-07-22T23:00:00+00:00",
    minutes_above_min_alt: 420,
    moon_separation_deg: 80,
    moon_up_fraction: 0.0,
    usable_start_utc: "2026-07-22T22:00:00+00:00",
    usable_end_utc: "2026-07-23T05:00:00+00:00",
    score: 88,
    ...over,
  };
}

function response(over: Partial<SuggestResponse> = {}): SuggestResponse {
  return {
    location_source: "settings",
    observer: { lat_deg: 51.5, lon_deg: -0.13, elevation_m: 30 },
    min_altitude_deg: 30,
    suggestions: [suggestion()],
    ...over,
  };
}

function renderBadge(props: {
  runs?: { total_exposure_s?: number | null; noise_sigma?: number | null }[] | null;
  coachKind?: NextBestMoveKind | null;
}) {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <IntegrationTrendBadge runs={props.runs ?? null} coachKind={props.coachKind ?? null} />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("IntegrationTrendBadge", () => {
  it("shows the plateau verdict when the target has gone sky-limited", () => {
    renderBadge({ runs: PLATEAUED });
    expect(screen.getByText(/About as clean as your sky allows/)).toBeInTheDocument();
    expect(screen.getByText(/sky-limited/)).toBeInTheDocument();
  });

  it("is suppressed while the coaching is nudging to add more time (integration)", () => {
    renderBadge({ runs: PLATEAUED, coachKind: "integration" });
    expect(screen.queryByText(/sky allows/)).toBeNull();
  });

  it("is suppressed while the coaching shows the 'good, add time' note", () => {
    renderBadge({ runs: PLATEAUED, coachKind: "good" });
    expect(screen.queryByText(/sky allows/)).toBeNull();
  });

  it("still shows beside a non-add-time coaching tip (e.g. locate)", () => {
    renderBadge({ runs: PLATEAUED, coachKind: "locate" });
    expect(screen.getByText(/About as clean as your sky allows/)).toBeInTheDocument();
  });

  it("renders nothing for an improving target (that verdict stays History-only)", () => {
    renderBadge({ runs: IMPROVING });
    expect(screen.queryByText(/sky allows/)).toBeNull();
  });

  it("renders nothing without enough measured history to judge the trend", () => {
    renderBadge({ runs: [{ total_exposure_s: 3600, noise_sigma: 0.1 }] });
    expect(screen.queryByText(/sky allows/)).toBeNull();
  });

  describe("the fresh target to point at instead", () => {
    it("names the planner's own pick, with the line the Dashboard card prints", async () => {
      // The verdict has always ended on "a brighter target will do more than
      // extra time on this one" and left the beginner to work out which.
      vi.spyOn(client.api, "suggestTargets").mockResolvedValue(response());
      renderBadge({ runs: PLATEAUED });
      expect(await screen.findByText(/M27 · Dumbbell Nebula/)).toBeInTheDocument();
      expect(screen.getByText(/Climbs to 64°, up about 7 h tonight/)).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /up/ })).toHaveAttribute("href", "/tonight");
    });

    it("asks the planner nothing at all on a target that is not plateaued", async () => {
      // The request is gated on the verdict, not on the page: an ordinary
      // target must not pay for a suggestion nobody will be shown.
      const spy = vi.spyOn(client.api, "suggestTargets").mockResolvedValue(response());
      renderBadge({ runs: IMPROVING });
      await waitFor(() => expect(screen.queryByText(/sky allows/)).toBeNull());
      expect(spy).not.toHaveBeenCalled();
    });

    it("asks nothing while an add-time nudge is suppressing the verdict", async () => {
      const spy = vi.spyOn(client.api, "suggestTargets").mockResolvedValue(response());
      renderBadge({ runs: PLATEAUED, coachKind: "integration" });
      await waitFor(() => expect(screen.queryByText(/sky allows/)).toBeNull());
      expect(spy).not.toHaveBeenCalled();
    });

    it("leaves the verdict alone when the planner has nothing to suggest", async () => {
      // No location set, no dark window, or nothing new well-placed — all of
      // which are ordinary states, not errors.
      vi.spyOn(client.api, "suggestTargets")
        .mockResolvedValue(response({ location_source: "none", observer: null, suggestions: [] }));
      renderBadge({ runs: PLATEAUED });
      expect(await screen.findByText(/sky-limited/)).toBeInTheDocument();
      await waitFor(() => expect(screen.queryByRole("link")).toBeNull());
    });

    it("leaves the verdict alone when the planner call fails", async () => {
      vi.spyOn(client.api, "suggestTargets").mockRejectedValue(new Error("no planner"));
      renderBadge({ runs: PLATEAUED });
      expect(await screen.findByText(/sky-limited/)).toBeInTheDocument();
      await waitFor(() => expect(screen.queryByRole("link")).toBeNull());
    });
  });
});
