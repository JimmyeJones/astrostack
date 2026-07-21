import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NightsCard, formatNightDate, verdictBadge } from "./NightsCard";
import type { NightSummary } from "../api/client";
import * as client from "../api/client";

function night(over: Partial<NightSummary> = {}): NightSummary {
  return {
    start_utc: "2026-07-08T22:00:00+00:00",
    end_utc: "2026-07-08T23:00:00+00:00",
    n_frames: 20,
    n_kept: 18,
    n_set_aside: 2,
    exposure_s: 200,
    kept_exposure_s: 180,
    median_fwhm_px: 2.4,
    verdict: "sharp",
    is_best: false,
    reject_buckets: { trailed: 2 },
    ...over,
  };
}

function renderCard(safe = "M_42") {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <NightsCard safe={safe} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("formatNightDate", () => {
  it("formats an ISO UTC stamp as a friendly day/month/year", () => {
    expect(formatNightDate("2026-07-08T22:00:00+00:00")).toBe("8 Jul 2026");
    expect(formatNightDate("2026-12-31T01:00:00+00:00")).toBe("31 Dec 2026");
  });
  it("returns a dash for a missing or unparseable stamp", () => {
    expect(formatNightDate(null)).toBe("—");
    expect(formatNightDate("nope")).toBe("—");
    expect(formatNightDate("2026-13-01T00:00:00Z")).toBe("—");
  });
});

describe("verdictBadge", () => {
  it("maps each verdict to a colour + label", () => {
    expect(verdictBadge("sharp")).toEqual({ color: "teal", label: "sharp" });
    expect(verdictBadge("soft")).toEqual({ color: "yellow", label: "soft" });
    expect(verdictBadge("hazy")).toEqual({ color: "orange", label: "hazy" });
  });
  it("returns null when there's no verdict", () => {
    expect(verdictBadge("")).toBeNull();
    expect(verdictBadge("unknown")).toBeNull();
  });
});

describe("NightsCard", () => {
  it("lists each night with its verdict, newest first", async () => {
    vi.spyOn(client.api, "targetNights").mockResolvedValue([
      night({ start_utc: "2026-07-08T22:00:00+00:00", verdict: "soft", median_fwhm_px: 4.0 }),
      night({ start_utc: "2026-07-01T22:00:00+00:00", verdict: "sharp", is_best: true, median_fwhm_px: 2.4 }),
    ]);
    renderCard();
    await waitFor(() => expect(screen.getByText("Nights")).toBeInTheDocument());
    expect(screen.getByText("8 Jul 2026")).toBeInTheDocument();
    expect(screen.getByText("1 Jul 2026")).toBeInTheDocument();
    expect(screen.getByText("soft")).toBeInTheDocument();
    expect(screen.getByText("sharp")).toBeInTheDocument();
    expect(screen.getByText("sharpest")).toBeInTheDocument();
  });

  it("renders nothing for a target with only one night (Last session covers it)", async () => {
    vi.spyOn(client.api, "targetNights").mockResolvedValue([night()]);
    const { container } = renderCard();
    await waitFor(() => expect(client.api.targetNights).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });

  it("renders nothing when there are no nights", async () => {
    vi.spyOn(client.api, "targetNights").mockResolvedValue([]);
    const { container } = renderCard();
    await waitFor(() => expect(client.api.targetNights).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
