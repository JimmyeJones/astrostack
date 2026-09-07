import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WishlistTonightCard } from "./WishlistTonightCard";
import * as client from "../api/client";
import type { WishlistTonightObject } from "../api/client";

const RING: WishlistTonightObject = {
  catalog_id: "M57",
  name: "Ring Nebula",
  type: "planetary nebula",
  con: "Lyr",
  blurb: "",
  captured: false,
  safe_name: null,
  max_altitude_deg: 78.4,
  minutes_above_min_alt: 300,
  moon_separation_deg: 92,
  moon_up_fraction: 0.1,
  usable_start_utc: "2026-07-15T21:40:00+00:00",
  usable_end_utc: "2026-07-16T02:10:00+00:00",
  transit_utc: "2026-07-16T00:00:00+00:00",
  score: 0.9,
};

function renderCard() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider
          client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <WishlistTonightCard />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("WishlistTonightCard", () => {
  it("says the thing you asked for is up, and how well placed it is", async () => {
    vi.spyOn(client.api, "wishlistTonight").mockResolvedValue({
      saved: 2, up: [RING], location_source: "settings",
    });
    renderCard();

    await waitFor(() =>
      expect(screen.getByTestId("wishlist-tonight-card")).toBeInTheDocument());
    expect(screen.getByText(/M57 \(Ring Nebula\) is on your wishlist/))
      .toBeInTheDocument();
    expect(screen.getByText(/climbs to about 78°/)).toBeInTheDocument();
    expect(screen.getByText(/5\.0 h of it usable/)).toBeInTheDocument();
  });

  it("counts them when several saved objects are up", async () => {
    vi.spyOn(client.api, "wishlistTonight").mockResolvedValue({
      saved: 3,
      up: [RING, { ...RING, catalog_id: "M31", name: "Andromeda Galaxy" }],
      location_source: "settings",
    });
    renderCard();

    await waitFor(() => expect(
      screen.getByText("2 objects from your wishlist are up tonight"),
    ).toBeInTheDocument());
  });

  it("marks a saved object you have already shot rather than implying it's new",
    async () => {
      vi.spyOn(client.api, "wishlistTonight").mockResolvedValue({
        saved: 1, up: [{ ...RING, captured: true, safe_name: "M_57" }],
        location_source: "settings",
      });
      renderCard();

      await waitFor(() =>
        expect(screen.getByText("Already got one")).toBeInTheDocument());
    });

  it("self-hides when nothing saved is up tonight", async () => {
    vi.spyOn(client.api, "wishlistTonight").mockResolvedValue({
      saved: 2, up: [], location_source: "settings",
    });
    renderCard();

    await waitFor(() => expect(client.api.wishlistTonight).toHaveBeenCalled());
    expect(screen.queryByTestId("wishlist-tonight-card")).not.toBeInTheDocument();
    // Not merely hidden — the card contributes no copy at all, so the page reads
    // exactly as it did before the wishlist existed.
    expect(screen.queryByText(/wishlist/i)).not.toBeInTheDocument();
  });

  it("self-hides on a fresh install, with nothing saved and no location", async () => {
    vi.spyOn(client.api, "wishlistTonight").mockResolvedValue({
      saved: 0, up: [], location_source: "none",
    });
    renderCard();

    await waitFor(() => expect(client.api.wishlistTonight).toHaveBeenCalled());
    expect(screen.queryByTestId("wishlist-tonight-card")).not.toBeInTheDocument();
  });

  it("self-hides on a backend that has never heard of a wishlist", async () => {
    vi.spyOn(client.api, "wishlistTonight")
      .mockRejectedValue(new Error("404: Not Found"));
    renderCard();

    await waitFor(() => expect(client.api.wishlistTonight).toHaveBeenCalled());
    expect(screen.queryByTestId("wishlist-tonight-card")).not.toBeInTheDocument();
  });
});
