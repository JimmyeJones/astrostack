import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MyDeepSkyWallCard } from "./MyDeepSkyWallCard";
import * as client from "../api/client";

function renderCard() {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <MyDeepSkyWallCard />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

const hero = (safe: string) => ({
  safe, name: safe.toUpperCase(), total_exposure_s: 3600,
  n_frames_accepted: 100, has_preview: true,
  thumbnail_url: `/api/targets/${safe}/thumbnail`,
});

function summary(heroes: ReturnType<typeof hero>[]) {
  return {
    n_targets_imaged: heroes.length, n_subs_kept: 100,
    total_integration_s: 3600 * heroes.length, integration_hours: heroes.length,
    first_light_utc: "2026-01-01T00:00:00Z",
    longest_target: null, most_imaged_target: null, heroes,
  } as never;
}

afterEach(() => vi.restoreAllMocks());

describe("MyDeepSkyWallCard", () => {
  it("offers the wall once two targets have a finished picture", async () => {
    vi.spyOn(client.api, "getLibrarySummary")
      .mockResolvedValue(summary([hero("m_42"), hero("m_31")]));
    renderCard();

    await waitFor(() =>
      expect(screen.getByText("My deep-sky wall")).toBeInTheDocument());
    const link = screen.getByRole("link", { name: /Download wall/ });
    expect(link).toHaveAttribute("href", "/api/gallery/montage.jpg?limit=9");
    expect(screen.getByText(/Your 2 best finished pictures/)).toBeInTheDocument();
  });

  it("offers the whole library as a zip, counting every finished picture", async () => {
    // The wall caps at 9; "download all" must not — a beginner backing up their
    // season expects all of them, and the count on the button has to say so.
    vi.spyOn(client.api, "getLibrarySummary").mockResolvedValue(
      summary(Array.from({ length: 14 }, (_, i) => hero(`t_${i}`))));
    renderCard();

    const link = await screen.findByRole("link", { name: /Download all 14 pictures/ });
    expect(link).toHaveAttribute("href", "/api/gallery/pictures.zip");
    expect(link).toHaveAttribute("download");
  });

  it("says how many it is showing when the library holds more than fit", async () => {
    vi.spyOn(client.api, "getLibrarySummary").mockResolvedValue(
      summary(Array.from({ length: 14 }, (_, i) => hero(`t_${i}`))));
    renderCard();

    await waitFor(() =>
      expect(screen.getByText(/Your 9 best finished pictures/)).toBeInTheDocument());
    expect(screen.getByText(/You have 14 finished/)).toBeInTheDocument();
  });

  it("stays hidden when one picture would be the whole wall", async () => {
    const spy = vi.spyOn(client.api, "getLibrarySummary")
      .mockResolvedValue(summary([hero("m_42")]));
    renderCard();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByText("My deep-sky wall")).toBeNull();
  });

  it("stays hidden while loading and on a failed fetch", async () => {
    const spy = vi.spyOn(client.api, "getLibrarySummary")
      .mockRejectedValue(new Error("nope"));
    renderCard();
    expect(screen.queryByText("My deep-sky wall")).toBeNull();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByText("My deep-sky wall")).toBeNull();
  });
});
