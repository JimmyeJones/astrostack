import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextSessionCard } from "./NextSessionCard";
import type { NextSession } from "../api/client";
import * as client from "../api/client";

function session(over: Partial<NextSession> = {}): NextSession {
  return {
    location_source: "settings",
    observer: { lat_deg: 51.5, lon_deg: -0.13, elevation_m: 30 },
    target_has_position: true,
    min_altitude_deg: 30,
    nights_scanned: 14,
    windows: [
      {
        dark_start_utc: "2026-01-15T22:00:00+00:00",
        dark_end_utc: "2026-01-16T06:00:00+00:00",
        usable_start_utc: "2026-01-15T22:40:00+00:00",
        usable_end_utc: "2026-01-16T02:10:00+00:00",
        max_altitude_deg: 34,
        minutes_above_min_alt: 210,
        moon_illumination: 0.12,
        moon_up_fraction: 0.0,
        score: 62,
      },
    ],
    ...over,
  };
}

function renderCard(props: {
  safe?: string;
  gapSeconds: number;
  subExposureSeconds: number | null;
}) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <NextSessionCard safe={props.safe ?? "M_42"}
          gapSeconds={props.gapSeconds}
          subExposureSeconds={props.subExposureSeconds} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("NextSessionCard", () => {
  it("joins the goal gap with the next dark window when work remains", async () => {
    vi.spyOn(client.api, "nextSession").mockResolvedValue(session());
    renderCard({ gapSeconds: 2 * 3600, subExposureSeconds: 10 });
    await waitFor(() =>
      expect(screen.getByText("Plan your next night")).toBeInTheDocument(),
    );
    expect(screen.getByText(/About 2 more clear hours.*720 more subs/)).toBeInTheDocument();
    expect(screen.getByText("Your next good window:")).toBeInTheDocument();
    expect(screen.getByText(/Thu 15 Jan.*22:40 → 02:10 UTC/)).toBeInTheDocument();
  });

  it("offers an 'Add to calendar' .ics download pointing at the target's endpoint", async () => {
    vi.spyOn(client.api, "nextSession").mockResolvedValue(session());
    renderCard({ safe: "M_42", gapSeconds: 2 * 3600, subExposureSeconds: 10 });
    const link = await screen.findByRole("link", { name: /Add to calendar/ });
    expect(link).toHaveAttribute("href", "/api/plan/next-session/M_42/calendar.ics");
    expect(link).toHaveAttribute("download");
  });

  it("self-hides when the goal is already met (no gap) — never fetches", () => {
    const spy = vi.spyOn(client.api, "nextSession").mockResolvedValue(session());
    const { container } = renderCard({ gapSeconds: 0, subExposureSeconds: 10 });
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
    // The query is disabled when there's no gap, so no request is made.
    expect(spy).not.toHaveBeenCalled();
  });

  it("self-hides when there's a gap but no upcoming window (no location/position)", async () => {
    vi.spyOn(client.api, "nextSession").mockResolvedValue(
      session({ location_source: "none", observer: null, windows: [] }),
    );
    const { container } = renderCard({ gapSeconds: 2 * 3600, subExposureSeconds: 10 });
    await waitFor(() => expect(client.api.nextSession).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });

  it("pluralises the intro and lists every window when the goal spans nights", async () => {
    const w = session().windows[0];
    vi.spyOn(client.api, "nextSession").mockResolvedValue(session({
      windows: [
        w,
        { ...w, dark_start_utc: "2026-01-17T22:00:00+00:00" },
        { ...w, dark_start_utc: "2026-01-19T22:00:00+00:00" },
      ],
    }));
    renderCard({ gapSeconds: 5 * 3600, subExposureSeconds: 10 });
    await waitFor(() =>
      expect(screen.getByText("Your next good windows:")).toBeInTheDocument(),
    );
  });
});
