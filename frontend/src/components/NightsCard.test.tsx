import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  NightsCard,
  formatNightDate,
  nightDateLabel,
  verdictBadge,
  verdictTooltip,
} from "./NightsCard";
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

describe("nightDateLabel", () => {
  it("labels the night by the observing-night date, not the UTC start", () => {
    // 8 Jul 21:00 in Seattle is already 9 Jul in UTC — labelling from `start_utc`
    // named the wrong night for every observer west of UTC.
    expect(nightDateLabel({
      night_date: "2026-07-08", start_utc: "2026-07-09T05:00:00+00:00",
    })).toBe("8 Jul 2026");
  });
  it("falls back to the UTC start when an older backend sends no night_date", () => {
    expect(nightDateLabel({ start_utc: "2026-07-09T05:00:00+00:00" }))
      .toBe("9 Jul 2026");
    expect(nightDateLabel({ night_date: null, start_utc: "2026-07-09T05:00:00+00:00" }))
      .toBe("9 Jul 2026");
  });
  it("returns a dash when neither is usable", () => {
    expect(nightDateLabel({ night_date: null, start_utc: null })).toBe("—");
  });
});

describe("verdictTooltip", () => {
  it("says what a soft night was compared against", () => {
    // The yellow word sits beside a button that discards the night, so the
    // reader needs the comparison, not just the conclusion.
    expect(verdictTooltip(night({
      verdict: "soft", median_fwhm_px: 5.2, typical_fwhm_px: 3.4,
    }))).toBe("5.2 px stars — softer than this target's usual 3.4 px.");
  });

  it("never calls the baseline a 'best'", () => {
    // The baseline is the median of the other nights, so quoting it as anyone's
    // best would be a number nobody achieved (the v0.319.1 fix's whole point).
    const tip = verdictTooltip(night({
      verdict: "soft", median_fwhm_px: 5.2, typical_fwhm_px: 3.4,
    }));
    expect(tip).not.toMatch(/best|sharpest/i);
  });

  it("gives a sharp night the same yardstick", () => {
    expect(verdictTooltip(night({
      verdict: "sharp", median_fwhm_px: 2.4, typical_fwhm_px: 3.4,
    }))).toBe("2.4 px stars — this target's usual is 3.4 px.");
  });

  it("explains a hazy night by its clouds, not by sharpness", () => {
    const tip = verdictTooltip(night({ verdict: "hazy", typical_fwhm_px: null }));
    expect(tip).toMatch(/cloudy/i);
    expect(tip).not.toMatch(/px/);
  });

  it("stays silent rather than inventing a comparison", () => {
    // A lone judgeable night (no baseline), an older backend that sends no
    // baseline at all, an unmeasured night, and junk numbers.
    expect(verdictTooltip(night({ verdict: "soft", typical_fwhm_px: null }))).toBeNull();
    expect(verdictTooltip(night({ verdict: "sharp" }))).toBeNull();
    expect(verdictTooltip(night({
      verdict: "soft", median_fwhm_px: null, typical_fwhm_px: 3.4,
    }))).toBeNull();
    expect(verdictTooltip(night({
      verdict: "soft", median_fwhm_px: Number.NaN, typical_fwhm_px: 3.4,
    }))).toBeNull();
    expect(verdictTooltip(night({ verdict: "", typical_fwhm_px: 3.4 }))).toBeNull();
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

  it("labels the badge with what it was measured against", async () => {
    vi.spyOn(client.api, "targetNights").mockResolvedValue([
      night({
        start_utc: "2026-07-08T22:00:00+00:00", verdict: "soft",
        median_fwhm_px: 5.2, typical_fwhm_px: 3.4,
      }),
      night({
        start_utc: "2026-07-01T22:00:00+00:00", verdict: "sharp",
        median_fwhm_px: 2.4, typical_fwhm_px: 3.4,
      }),
    ]);
    renderCard();
    await waitFor(() => expect(screen.getByText("Nights")).toBeInTheDocument());
    expect(screen.getByLabelText(
      "soft: 5.2 px stars — softer than this target's usual 3.4 px.",
    )).toBeInTheDocument();
    // Still a badge, not a fourth column: the sentence is not rendered as text.
    expect(screen.queryByText(/softer than this target's usual/)).not.toBeInTheDocument();
  });

  it("leaves the badge bare when an older backend sends no baseline", async () => {
    vi.spyOn(client.api, "targetNights").mockResolvedValue([
      night({ start_utc: "2026-07-08T22:00:00+00:00", verdict: "soft", median_fwhm_px: 5.2 }),
      night({ start_utc: "2026-07-01T22:00:00+00:00", verdict: "sharp", median_fwhm_px: 2.4 }),
    ]);
    renderCard();
    await waitFor(() => expect(screen.getByText("Nights")).toBeInTheDocument());
    const badge = screen.getByText("soft");
    expect(badge).toBeInTheDocument();
    expect(badge.getAttribute("aria-label")).toBeNull();
  });

  it("shows the observing night, not the UTC date of the first sub", async () => {
    // Both sessions start after local sunset west of UTC, so their UTC stamps
    // roll into the next day; the card must still name the evening the owner
    // was out (matching the Dashboard's imaging calendar).
    vi.spyOn(client.api, "targetNights").mockResolvedValue([
      night({ night_date: "2026-07-08", start_utc: "2026-07-09T05:00:00+00:00" }),
      night({ night_date: "2026-07-01", start_utc: "2026-07-02T04:30:00+00:00" }),
    ]);
    renderCard();
    await waitFor(() => expect(screen.getByText("Nights")).toBeInTheDocument());
    expect(screen.getByText("8 Jul 2026")).toBeInTheDocument();
    expect(screen.getByText("1 Jul 2026")).toBeInTheDocument();
    expect(screen.queryByText("9 Jul 2026")).not.toBeInTheDocument();
    expect(screen.queryByText("2 Jul 2026")).not.toBeInTheDocument();
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
