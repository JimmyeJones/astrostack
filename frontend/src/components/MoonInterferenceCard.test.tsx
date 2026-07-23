import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MoonInterferenceCard,
  moonLevelColor,
  moonLevelLabel,
} from "./MoonInterferenceCard";
import type { MoonInterference, MoonInterferenceResponse } from "../api/client";
import * as client from "../api/client";

function moon(over: Partial<MoonInterference> = {}): MoonInterference {
  return {
    illumination: 0.92,
    waxing: false,
    phase_name: "Full Moon",
    moon_altitude_deg: 35,
    separation_deg: 22,
    level: "poor",
    text: "A bright 92%-lit Moon is only ~22° from this target — faint nebulae will wash out tonight.",
    at_utc: "2026-07-30T05:02:00+00:00",
    ...over,
  };
}

function resp(over: Partial<MoonInterferenceResponse> = {}): MoonInterferenceResponse {
  return {
    location_source: "settings",
    observer: { lat_deg: 40, lon_deg: -74, elevation_m: 0 },
    target_has_position: true,
    moon: moon(),
    ...over,
  };
}

function renderCard(safe = "M_42") {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MoonInterferenceCard safe={safe} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("moonLevelColor / moonLevelLabel", () => {
  it("maps each level to a gentle colour and a plain label", () => {
    expect(moonLevelColor("good")).toBe("teal");
    expect(moonLevelColor("ok")).toBe("yellow");
    expect(moonLevelColor("poor")).toBe("orange");
    expect(moonLevelLabel("good")).toBe("Good tonight");
    expect(moonLevelLabel("poor")).toBe("Poor for faint targets");
  });
});

describe("MoonInterferenceCard", () => {
  it("shows the verdict, sentence and phase for a bright-Moon night", async () => {
    vi.spyOn(client.api, "moonInterference").mockResolvedValue(resp());
    renderCard();
    expect(await screen.findByText(/Poor for faint targets/)).toBeInTheDocument();
    expect(screen.getByText(/faint nebulae will wash out/)).toBeInTheDocument();
    expect(screen.getByText(/Full Moon · 92% lit/)).toBeInTheDocument();
  });

  it("self-hides when there is no reading (no location / position)", async () => {
    vi.spyOn(client.api, "moonInterference").mockResolvedValue(
      resp({ location_source: "none", observer: null, moon: null }),
    );
    renderCard();
    await waitFor(() => expect(client.api.moonInterference).toHaveBeenCalled());
    expect(screen.queryByText(/Moon tonight/)).not.toBeInTheDocument();
  });
});
