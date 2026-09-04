import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  SessionRecapCard,
  describeQualityDrift,
  describeRejects,
  describeSession,
  sessionRecapTitle,
} from "./SessionRecapCard";
import type { SessionRecap } from "../api/client";
import * as client from "../api/client";

function recap(over: Partial<SessionRecap> = {}): SessionRecap {
  return {
    n_frames: 10, n_kept: 8, n_set_aside: 2,
    session_exposure_s: 100, kept_exposure_s: 80, total_kept_exposure_s: 130,
    start_utc: "2026-07-08T22:00:00", end_utc: "2026-07-08T22:05:00",
    night_date: "2026-07-08",
    reject_buckets: { trailed: 2 },
    quality_drift: null,
    ...over,
  };
}

function renderCard(safe = "M_31") {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <SessionRecapCard safe={safe} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("describeRejects", () => {
  it("lists present buckets in a friendly order", () => {
    expect(describeRejects({ trailed: 2, cloudy: 10 })).toBe("10 cloudy, 2 trailed");
    expect(describeRejects({ soft: 3 })).toBe("3 soft");
    expect(describeRejects({})).toBe("");
    // Unknown buckets sort after the known ones.
    expect(describeRejects({ other: 1, cloudy: 4 })).toBe("4 cloudy, 1 other");
  });
});

// The morning after the fixture's 8 Jul night — so "Last night" is honest and
// the existing phrasing assertions stay deterministic whatever day the suite runs.
const MORNING_AFTER = new Date("2026-07-09T09:00:00Z");

describe("describeSession", () => {
  it("phrases the kept-vs-set-aside recap with a reason breakdown", () => {
    expect(describeSession(recap(), MORNING_AFTER)).toBe(
      "Last night added 10 subs (2 min). 8 kept; 2 set aside (2 trailed). " +
        "Total on this target: 2 min.",
    );
  });

  it("says all kept when nothing was set aside", () => {
    const r = recap({ n_frames: 3, n_kept: 3, n_set_aside: 0, reject_buckets: {},
      session_exposure_s: 30, kept_exposure_s: 30, total_kept_exposure_s: 30 });
    expect(describeSession(r, MORNING_AFTER)).toBe(
      "Last night added 3 subs (30 s). All 3 were kept. Total on this target: 30 s.",
    );
  });

  it("uses the singular for a one-sub session", () => {
    const r = recap({ n_frames: 1, n_kept: 1, n_set_aside: 0, reject_buckets: {} });
    expect(describeSession(r, MORNING_AFTER)).toContain("added 1 sub (");
  });

  it("dates itself instead of saying 'Last night' weeks later", () => {
    // The card always shows the most recent session, so after a cloudy fortnight
    // "Last night added…" reads as though the app lost track of the date.
    expect(describeSession(recap(), new Date("2026-07-23T09:00:00Z"))).toBe(
      "Your night on 8 Jul added 10 subs (2 min). 8 kept; 2 set aside (2 trailed). " +
        "Total on this target: 2 min.",
    );
  });

  it("adds the year once the session is no longer this year", () => {
    expect(describeSession(recap(), new Date("2027-01-05T09:00:00Z")))
      .toContain("Your night on 8 Jul 2026 added");
  });

  it("keeps the warm wording when the night can't be dated at all", () => {
    const r = recap({ night_date: null, start_utc: null });
    expect(describeSession(r, MORNING_AFTER)).toContain("Last night added");
  });
});

describe("describeQualityDrift", () => {
  it("phrases the softness nudge with both FWHM values, to one decimal", () => {
    expect(
      describeQualityDrift({
        kind: "fwhm", latest_fwhm_px: 5.2, baseline_fwhm_px: 3.4,
        n_latest: 8, n_baseline: 8,
      }),
    ).toBe(
      "Heads up: last night's stars are softer than this target's usual " +
        "(5.2 px vs 3.4 px FWHM) — worth checking focus.",
    );
  });

  it("calls the baseline a usual night, never a best one", () => {
    // The server's baseline is the *median* of the prior nights, not the
    // sharpest of them (the sharpest kept getting sharper as a project grew, so
    // this nudge fired on ordinary nights). A sentence saying "your usual best"
    // over a median would be quoting a number that is nobody's best.
    const line = describeQualityDrift({
      kind: "fwhm", latest_fwhm_px: 5.2, baseline_fwhm_px: 3.4,
      n_latest: 8, n_baseline: 40,
    });
    expect(line).toContain("usual");
    expect(line).not.toContain("best");
  });

  it("says 'that session' once the session it describes is no longer last night", () => {
    // Must agree with the recap sentence right above it, which has already
    // stopped calling an old session "last session".
    expect(
      describeQualityDrift({
        kind: "fwhm", latest_fwhm_px: 5.2, baseline_fwhm_px: 3.4,
        n_latest: 8, n_baseline: 8,
      }, false),
    ).toContain("Heads up: that night's stars are softer");
  });
});

describe("sessionRecapTitle", () => {
  it("names the observing night the server bucketed the session into", () => {
    // 22:00 UTC on the 8th is still the night *of* the 8th for an observer east
    // of UTC, and the server's night_date says so — the title must follow it
    // rather than re-deriving a date from the raw UTC stamp.
    expect(sessionRecapTitle({ night_date: "2026-07-08", start_utc: "2026-07-09T03:00:00+00:00" }))
      .toBe("Last night — 8 Jul 2026");
  });

  it("falls back to the UTC start when an older backend sends no night_date", () => {
    expect(sessionRecapTitle({ start_utc: "2026-07-08T22:00:00+00:00" }))
      .toBe("Last night — 8 Jul 2026");
    expect(sessionRecapTitle({ night_date: null, start_utc: "2026-07-08T22:00:00+00:00" }))
      .toBe("Last night — 8 Jul 2026");
  });

  it("stays a bare heading when the night can't be dated at all", () => {
    expect(sessionRecapTitle({ night_date: null, start_utc: null })).toBe("Last night");
  });
});

describe("SessionRecapCard", () => {
  it("renders the recap card with a kept-percentage badge", async () => {
    vi.spyOn(client.api, "sessionRecap").mockResolvedValue(recap());
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Last night — 8 Jul 2026")).toBeInTheDocument());
    expect(screen.getByText("80% kept")).toBeInTheDocument();
    expect(screen.getByText(/2 set aside \(2 trailed\)/)).toBeInTheDocument();
  });

  it("shows the softness nudge only when a quality drift is reported", async () => {
    vi.spyOn(client.api, "sessionRecap").mockResolvedValue(
      recap({
        quality_drift: {
          kind: "fwhm", latest_fwhm_px: 5.2, baseline_fwhm_px: 3.4,
          n_latest: 8, n_baseline: 8,
        },
      }),
    );
    renderCard();
    await waitFor(() => expect(screen.getByText(/worth checking focus/)).toBeInTheDocument());
  });

  it("omits the nudge when quality is steady", async () => {
    vi.spyOn(client.api, "sessionRecap").mockResolvedValue(recap());
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Last night — 8 Jul 2026")).toBeInTheDocument());
    expect(screen.queryByText(/worth checking focus/)).toBeNull();
  });

  it("explains a Moon-washed session when the backend says so", async () => {
    const note =
      "A bright 99%-lit Moon was only ~20\u00b0 from this target while you were " +
      "shooting, so the sky background is brighter and faint detail is harder to " +
      "pull out. That's the sky, not your setup \u2014 the same target on a " +
      "dark-Moon night will come out cleaner.";
    vi.spyOn(client.api, "sessionRecap").mockResolvedValue(recap({ moon_note: note }));
    renderCard();
    await waitFor(() => expect(screen.getByText(note)).toBeInTheDocument());
  });

  it("says nothing about the Moon on an ordinary night", async () => {
    vi.spyOn(client.api, "sessionRecap").mockResolvedValue(recap());
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Last night \u2014 8 Jul 2026")).toBeInTheDocument());
    expect(screen.queryByText(/Moon/)).toBeNull();
  });

  it("renders nothing when there's nothing datable to report", async () => {
    vi.spyOn(client.api, "sessionRecap").mockResolvedValue(null);
    const { container } = renderCard();
    await waitFor(() => expect(client.api.sessionRecap).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
