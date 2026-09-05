import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ContinueTonightCard } from "./ContinueTonightCard";
import type {
  BestTonight, NightPlan, PlannedTarget, TargetProgress,
} from "../api/client";
import * as client from "../api/client";

function owned(over: Partial<PlannedTarget> = {}): PlannedTarget {
  return {
    id: over.target_safe ?? "t",
    name: "M31",
    ra_deg: 10,
    dec_deg: 41,
    type: "Galaxy",
    con: "And",
    already_targeted: true,
    max_altitude_deg: 70,
    transit_utc: "2026-07-24T03:00:00+00:00",
    minutes_above_min_alt: 300,
    moon_separation_deg: 90,
    moon_up_fraction: 0,
    usable_start_utc: "2026-07-24T01:00:00+00:00",
    usable_end_utc: "2026-07-24T05:00:00+00:00",
    score: 60,
    target_safe: "m31",
    frames_accepted: 200,
    total_exposure_s: 4.5 * 3600,
    ...over,
  } as PlannedTarget;
}

function plan(targets: PlannedTarget[]): NightPlan {
  return {
    location_source: "settings",
    observer: { lat_deg: 51.5, lon_deg: -0.13, elevation_m: 30 },
    generated_utc: "2026-07-24T00:00:00Z",
    dark_window: {
      start_utc: "2026-07-24T21:30:00Z",
      end_utc: "2026-07-25T03:30:00Z",
      duration_minutes: 360,
      sun_alt_threshold_deg: -18,
    },
    moon_illumination: 0.2,
    moon_waxing: true,
    min_altitude_deg: 30,
    horizon_active: false,
    targets,
  } as unknown as NightPlan;
}

// The adjacent "Point here right now" card's answer. The card under test reads
// the same `/best-tonight` response so it never repeats a target that card has
// already named; an empty `picks` list is the ordinary "nothing to exclude".
function bestTonight(safes: string[] = []): BestTonight {
  return {
    location_source: "settings",
    observer: { lat_deg: 51.5, lon_deg: -0.13, elevation_m: 30 },
    generated_utc: "2026-07-24T00:00:00Z",
    dark_now: true,
    dark_minutes_left: 300,
    min_altitude_deg: 30,
    picks: safes.map((safe) => ({
      safe,
      name: safe.toUpperCase(),
      ra_deg: 0,
      dec_deg: 0,
      altitude_now_deg: 60,
      minutes_usable_left: 200,
      hours_captured: 1,
      frames_accepted: 100,
      noise_gain: 0.3,
      score: 50,
      reason: "reason",
    })),
  } as unknown as BestTonight;
}

function renderCard() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <ContinueTonightCard />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("ContinueTonightCard", () => {
  it("recommends the started target closest to a finished picture", async () => {
    vi.spyOn(client.api, "getTonight").mockResolvedValue(
      plan([
        owned({ name: "M81", target_safe: "m81", total_exposure_s: 1 * 3600, score: 90 }),
        owned({ name: "M31", target_safe: "m31", total_exposure_s: 4.5 * 3600, score: 50 }),
      ]),
    );
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue([]);
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(bestTonight());
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Point here tonight")).toBeInTheDocument(),
    );
    // M31 (4.5 h of 6 h goal) wins over M81 (1 h) despite the lower score.
    expect(screen.getByText("M31")).toBeInTheDocument();
    expect(screen.getByText(/200 subs/)).toBeInTheDocument();
    // M81 appears as a dimmed runner-up.
    expect(screen.getByText("Or continue:")).toBeInTheDocument();
    expect(screen.getByText("M81")).toBeInTheDocument();
  });

  it("self-hides when no location / no started target is up tonight", async () => {
    vi.spyOn(client.api, "getTonight").mockResolvedValue(
      plan([owned({ target_safe: "m31", score: 0 })]), // never clears the floor
    );
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue([]);
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(bestTonight());
    const { container } = renderCard();
    await waitFor(() => expect(client.api.getTonight).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });

  it("carries the 'nudge it this way' chip onto the card you act on", async () => {
    // The framing advice from this target's newest picture, said on the screen a
    // beginner reads *before* pointing the scope rather than only on the finished
    // picture's card the morning after.
    vi.spyOn(client.api, "getTonight").mockResolvedValue(
      plan([
        owned({
          name: "M31", target_safe: "m31", total_exposure_s: 4.5 * 3600, score: 50,
          recentre_nudge: {
            direction: "south", degrees: 1.0, short: "1.0° south",
            text: "Next time, nudge your Seestar about 1.0° south before you start, "
              + "and it'll sit in the middle.",
          },
        } as Partial<PlannedTarget>),
      ]),
    );
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue([]);
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(bestTonight());
    renderCard();
    expect(await screen.findByText("Nudge 1.0° south")).toBeInTheDocument();
  });

  it("stays silent about framing when the newest picture was well framed", async () => {
    // Never a guessed direction: no nudge from the backend → no chip at all.
    vi.spyOn(client.api, "getTonight").mockResolvedValue(
      plan([owned({ name: "M31", target_safe: "m31", total_exposure_s: 4.5 * 3600 })]),
    );
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue([]);
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(bestTonight());
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Point here tonight")).toBeInTheDocument(),
    );
    expect(screen.queryByText(/Nudge /)).toBeNull();
  });

  it("honours a user-set integration goal from library-progress", async () => {
    // M31 at 4.5 h: default 6 h goal → improvable and it would be the pick. With
    // a user goal of 4 h it's already 'plenty' → excluded, leaving M81.
    vi.spyOn(client.api, "getTonight").mockResolvedValue(
      plan([
        owned({ name: "M31", target_safe: "m31", total_exposure_s: 4.5 * 3600, score: 50 }),
        owned({ name: "M81", target_safe: "m81", total_exposure_s: 1 * 3600, score: 90 }),
      ]),
    );
    const progress: TargetProgress[] = [
      { safe: "m31", name: "M31", total_exposure_s: 4.5 * 3600, object_type: "Galaxy", goal_s: 4 * 3600 },
    ];
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue(progress);
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(bestTonight());
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Point here tonight")).toBeInTheDocument(),
    );
    // Heading M81 is the pick; M31 must not be the headline (no runner-up here).
    expect(screen.getByText("M81")).toBeInTheDocument();
    expect(screen.queryByText("M31")).toBeNull();
  });
  it("doesn't repeat the target the 'Point here right now' card already named", async () => {
    // Both cards sit on the Dashboard one above the other and rank the same
    // owned library. Without this, a beginner with two started targets read the
    // same name twice under two headings.
    vi.spyOn(client.api, "getTonight").mockResolvedValue(
      plan([
        owned({ name: "M31", target_safe: "m31", total_exposure_s: 4.5 * 3600, score: 50 }),
        owned({ name: "M81", target_safe: "m81", total_exposure_s: 1 * 3600, score: 90 }),
      ]),
    );
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue([]);
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(bestTonight(["m31"]));
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Point here tonight")).toBeInTheDocument(),
    );
    // M31 would have been the pick; it's already recommended above, so this card
    // offers the next-best started target instead.
    expect(screen.getByText("M81")).toBeInTheDocument();
    expect(screen.queryByText("M31")).toBeNull();
  });

  it("self-hides when the only started target is already recommended above", async () => {
    vi.spyOn(client.api, "getTonight").mockResolvedValue(
      plan([owned({ name: "M31", target_safe: "m31", total_exposure_s: 4.5 * 3600 })]),
    );
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue([]);
    vi.spyOn(client.api, "getBestTonight").mockResolvedValue(bestTonight(["m31"]));
    const { container } = renderCard();
    await waitFor(() => expect(client.api.getBestTonight).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });

  it("still recommends when the backend is too old to know /best-tonight", async () => {
    // An older backend 404s the sibling endpoint. Nothing to exclude, so the
    // card must behave exactly as it did before this dedup existed.
    vi.spyOn(client.api, "getTonight").mockResolvedValue(
      plan([owned({ name: "M31", target_safe: "m31", total_exposure_s: 4.5 * 3600 })]),
    );
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue([]);
    vi.spyOn(client.api, "getBestTonight").mockRejectedValue(new Error("404"));
    renderCard();
    expect(await screen.findByText("Point here tonight")).toBeInTheDocument();
    expect(screen.getByText("M31")).toBeInTheDocument();
  });
});
