import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PointHereTonightCard, pointHereSubtitle, pointHereTitle } from "./PointHereTonightCard";
import * as client from "../../api/client";
import type { BestTonight, TonightPick } from "../../api/client";

function pick(overrides: Partial<TonightPick> = {}): TonightPick {
  return {
    safe: "M_31", name: "M 31", ra_deg: 10.68, dec_deg: 41.27,
    altitude_now_deg: 62.4, minutes_usable_left: 200, hours_captured: 0.75,
    frames_accepted: 90, noise_gain: 0.345, score: 61.2,
    reason: "M 31 is 62° up right now and stays shootable for another 3 h 20 m. "
      + "So far you've got 45 min on it — another hour would cut its noise about 35%.",
    ...overrides,
  };
}

function payload(overrides: Partial<BestTonight> = {}): BestTonight {
  return {
    location_source: "settings",
    observer: { lat_deg: 51.5, lon_deg: -0.13, elevation_m: 30 },
    generated_utc: "2026-01-15T22:00:00+00:00",
    dark_now: true,
    dark_minutes_left: 215,
    min_altitude_deg: 30,
    picks: [pick()],
    ...overrides,
  };
}

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><PointHereTonightCard /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("pointHereTitle", () => {
  it("says nothing when there's nothing to recommend", () => {
    expect(pointHereTitle(undefined)).toBeNull();
    expect(pointHereTitle(payload({ picks: [] }))).toBeNull();
  });
  it("only claims 'right now' when it's actually dark now", () => {
    expect(pointHereTitle(payload())).toBe("Point here right now");
    expect(pointHereTitle(payload({ dark_now: false }))).toBe("Worth more time");
  });
});

describe("pointHereSubtitle", () => {
  it("names how much dark sky is left, so 'right now' carries a deadline", () => {
    expect(pointHereSubtitle(payload({ dark_minutes_left: 215 })))
      .toBe("About 3 h 35 m of dark sky left tonight.");
    expect(pointHereSubtitle(payload({ dark_minutes_left: 120 })))
      .toBe("About 2 h of dark sky left tonight.");
    expect(pointHereSubtitle(payload({ dark_minutes_left: 40 })))
      .toBe("About 40 min of dark sky left tonight.");
  });
  it("admits it doesn't know the placement when no location is set", () => {
    const sub = pointHereSubtitle(payload({ observer: null, dark_now: false }))!;
    expect(sub).toContain("another hour would help");
    expect(sub).toContain("Set your location in Settings");
  });
  it("doesn't quote a countdown before darkness has started", () => {
    expect(pointHereSubtitle(payload({ dark_now: false })))
      .toBe("Tonight's best use of your scope.");
  });
  it("doesn't promise a night that isn't coming (high-latitude summer)", () => {
    expect(pointHereSubtitle(payload({ dark_now: false, dark_minutes_left: 0 })))
      .toBe("Ranked by how much another hour would help.");
  });
  it("carries the backend's own reason for not placing anything", () => {
    // A high-latitude summer used to get no explanation at all here — the
    // sentence existed, but it was buried in each pick's reason instead.
    expect(pointHereSubtitle(payload({
      dark_now: false, dark_minutes_left: 0,
      note: "There's no astronomical darkness where you are tonight, so this "
        + "can't say what's well-placed.",
    }))).toBe("Ranked by how much another hour would help. There's no "
      + "astronomical darkness where you are tonight, so this can't say what's "
      + "well-placed.");
  });
});

describe("PointHereTonightCard", () => {
  it("leads with one target, its altitude and the plain-language why", async () => {
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(payload());
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Point here right now")).toBeInTheDocument());
    expect(screen.getByText("M 31")).toBeInTheDocument();
    expect(screen.getByText("62° up")).toBeInTheDocument();
    expect(screen.getByText(/cut its noise about 35%/)).toBeInTheDocument();
    const open = screen.getByRole("link", { name: "Open M 31" });
    expect(open).toHaveAttribute("href", "/targets/M_31");
  });

  it("offers the runners-up without a second call to action", async () => {
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(payload({
      picks: [pick(), pick({ safe: "NGC_7000", name: "NGC 7000", score: 40 })],
    }));
    renderCard();
    await waitFor(() => expect(screen.getByText("NGC 7000")).toBeInTheDocument());
    // Only the leader gets the buttons — the point is one clear recommendation.
    expect(screen.getAllByRole("link", { name: /^Open / })).toHaveLength(1);
  });

  it("renders nothing when there's nothing worth pointing at", async () => {
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(payload({ picks: [] }));
    const { container } = renderCard();
    await waitFor(() => expect(client.api.getBestTonight).toHaveBeenCalled());
    expect(container.querySelector("[data-testid=point-here-tonight-card]")).toBeNull();
  });

  it("stays silent on an older backend that doesn't know the endpoint", async () => {
    vi.spyOn(client.api, "getBestTonight").mockRejectedValue(new Error("404"));
    const { container } = renderCard();
    await waitFor(() => expect(client.api.getBestTonight).toHaveBeenCalled());
    expect(container.querySelector("[data-testid=point-here-tonight-card]")).toBeNull();
  });

  it("still helps when no location is known, without claiming the target is up", async () => {
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(payload({
      location_source: "none", observer: null, dark_now: false,
      dark_minutes_left: 0,
      note: "Set your location in Settings and this can also tell you whether "
        + "it's up right now.",
      picks: [
        pick({
          altitude_now_deg: null,
          reason: "You've got 45 min on M 31 — another hour would cut its noise "
            + "about 35%.",
        }),
        pick({
          safe: "NGC_7000", name: "NGC 7000", altitude_now_deg: null, score: 30,
          reason: "You've got 2 h on NGC 7000 — another hour would cut its noise "
            + "about 22%.",
        }),
      ],
    }));
    renderCard();
    await waitFor(() => expect(screen.getByText("Worth more time")).toBeInTheDocument());
    expect(screen.queryByText(/° up$/)).toBeNull();
    // Said exactly once, in the subtitle — not once per pick underneath it.
    expect(screen.getAllByText(/Set your location in Settings/)).toHaveLength(1);
  });
});
