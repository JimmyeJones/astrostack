import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NearlyThereCard } from "./NearlyThereCard";
import * as client from "../api/client";
import type { NearlyThere } from "../api/client";

const RING: NearlyThere["missing"][number] = {
  catalog_id: "M57",
  name: "Ring Nebula",
  type: "planetary nebula",
  blurb: "",
  max_altitude_deg: 78.4,
  minutes_above_min_alt: 300,
  usable_start_utc: "2026-07-15T21:40:00+00:00",
  usable_end_utc: "2026-07-16T02:10:00+00:00",
};

function renderCard() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <NearlyThereCard />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("NearlyThereCard", () => {
  it("turns the count into a plan when the missing object is up tonight", async () => {
    vi.spyOn(client.api, "nearlyThere").mockResolvedValue({
      con: "Lyr", constellation: "Lyra", captured: 1, total: 2,
      missing: [RING], tonight_catalog_id: "M57", location_source: "settings",
    });
    renderCard();

    await waitFor(() =>
      expect(screen.getByTestId("nearly-there-card")).toBeInTheDocument());
    expect(screen.getByText(/one object away from finishing Lyra/)).toBeInTheDocument();
    expect(screen.getByText(/M57 \(Ring Nebula\) is well placed tonight/))
      .toBeInTheDocument();
    expect(screen.getByText(/climbs to about 78°/)).toBeInTheDocument();
  });

  it("still names the constellation when nothing is up, without faking an altitude",
    async () => {
      vi.spyOn(client.api, "nearlyThere").mockResolvedValue({
        con: "Lyr", constellation: "Lyra", captured: 1, total: 2,
        missing: [{ ...RING, max_altitude_deg: null, minutes_above_min_alt: null,
                    usable_start_utc: null, usable_end_utc: null }],
        tonight_catalog_id: null, location_source: "settings",
      });
      renderCard();

      await waitFor(() =>
        expect(screen.getByTestId("nearly-there-card")).toBeInTheDocument());
      expect(screen.getByText(/None of the ones you're missing are up tonight/))
        .toBeInTheDocument();
      expect(screen.queryByText(/climbs to about/)).toBeNull();
    });

  it("points a user with no location at Settings rather than going quiet", async () => {
    vi.spyOn(client.api, "nearlyThere").mockResolvedValue({
      con: "Ori", constellation: "Orion", captured: 3, total: 5,
      missing: [
        { ...RING, catalog_id: "M78", name: "", max_altitude_deg: null,
          minutes_above_min_alt: null, usable_start_utc: null, usable_end_utc: null },
        { ...RING, catalog_id: "NGC 2024", name: "Flame Nebula",
          max_altitude_deg: null, minutes_above_min_alt: null,
          usable_start_utc: null, usable_end_utc: null },
      ],
      tonight_catalog_id: null, location_source: "none",
    });
    renderCard();

    await waitFor(() =>
      expect(screen.getByTestId("nearly-there-card")).toBeInTheDocument());
    expect(screen.getByText(/2 objects away from finishing Orion/)).toBeInTheDocument();
    expect(screen.getByText(/Set your observing location in Settings/))
      .toBeInTheDocument();
    // An object with no popular name shows its id rather than a blank badge.
    expect(screen.getByText("M78")).toBeInTheDocument();
  });

  it("says nothing when no constellation is close", async () => {
    const spy = vi.spyOn(client.api, "nearlyThere").mockResolvedValue(null);
    renderCard();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("nearly-there-card")).toBeNull();
  });

  it("stays silent on an older backend or a failed fetch", async () => {
    const spy = vi.spyOn(client.api, "nearlyThere")
      .mockRejectedValue(new Error("404"));
    renderCard();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("nearly-there-card")).toBeNull();
  });
});
