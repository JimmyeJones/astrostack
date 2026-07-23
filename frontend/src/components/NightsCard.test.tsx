import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("sets a night aside with its own bounds, then undoes via bulk-accept", async () => {
    vi.spyOn(client.api, "targetNights").mockResolvedValue([
      night({ start_utc: "2026-07-08T22:00:00+00:00", end_utc: "2026-07-08T23:00:00+00:00", n_kept: 18 }),
      night({ start_utc: "2026-07-01T22:00:00+00:00", end_utc: "2026-07-01T23:00:00+00:00", n_kept: 5 }),
    ]);
    const setAside = vi.spyOn(client.api, "setAsideNight")
      .mockResolvedValue({ changed: 18, changed_ids: [1, 2, 3] });
    const bulk = vi.spyOn(client.api, "bulkFrames")
      .mockResolvedValue({ changed: 3, changed_ids: [1, 2, 3] });
    renderCard();
    await waitFor(() => expect(screen.getByText("8 Jul 2026")).toBeInTheDocument());

    const buttons = screen.getAllByRole("button", { name: "Set aside" });
    expect(buttons).toHaveLength(2);  // one per night
    fireEvent.click(buttons[0]);  // newest night (8 Jul)

    await waitFor(() =>
      expect(setAside).toHaveBeenCalledWith(
        "M_42", "2026-07-08T22:00:00+00:00", "2026-07-08T23:00:00+00:00",
      ),
    );
    // The undo affordance names the touched subs.
    const undo = await screen.findByRole("button", { name: "Undo" });
    fireEvent.click(undo);
    await waitFor(() =>
      expect(bulk).toHaveBeenCalledWith("M_42", { action: "accept", ids: [1, 2, 3] }),
    );
  });

  it("offers no Set-aside button for a night already fully set aside", async () => {
    vi.spyOn(client.api, "targetNights").mockResolvedValue([
      night({ start_utc: "2026-07-08T22:00:00+00:00", n_kept: 10 }),
      night({ start_utc: "2026-07-01T22:00:00+00:00", n_frames: 6, n_kept: 0, n_set_aside: 6 }),
    ]);
    renderCard();
    await waitFor(() => expect(screen.getByText("1 Jul 2026")).toBeInTheDocument());
    // Only the night with kept subs (8 Jul) gets a button.
    expect(screen.getAllByRole("button", { name: "Set aside" })).toHaveLength(1);
    // The fully-set-aside night shows the dimmed marker instead of a button.
    expect(screen.getByText("set aside", { selector: "p" })).toBeInTheDocument();
  });
});
