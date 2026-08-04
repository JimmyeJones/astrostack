import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LastNightCard, describeLibraryNight, lastNightLabel } from "./LastNightCard";
import type { LibrarySessionRecap, TargetNight } from "../api/client";
import * as client from "../api/client";

function tgt(over: Partial<TargetNight> = {}): TargetNight {
  return {
    name: "M 31", safe: "M_31",
    n_frames: 6, n_kept: 6, n_set_aside: 0,
    exposure_s: 60, kept_exposure_s: 60,
    ...over,
  };
}

function recap(over: Partial<LibrarySessionRecap> = {}): LibrarySessionRecap {
  return {
    n_targets: 2, n_frames: 10, n_kept: 8, n_set_aside: 2,
    session_exposure_s: 7200, kept_exposure_s: 5760,
    start_utc: "2026-07-08T21:00:00+00:00", end_utc: "2026-07-08T23:05:00+00:00",
    night_date: "2026-07-08",
    targets: [tgt({ n_frames: 6 }), tgt({ name: "M 42", safe: "M_42", n_frames: 4 })],
    reject_buckets: { trailed: 2 },
    ...over,
  };
}

function renderCard() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <LastNightCard />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("lastNightLabel", () => {
  it("names the observing night the server bucketed the session into", () => {
    // A session that runs past local midnight ENDS on the following UTC day, so
    // the old end_utc slice named tomorrow and disagreed with the imaging
    // calendar. The server's night_date is the one source of truth.
    expect(lastNightLabel({
      night_date: "2026-07-08", start_utc: "2026-07-09T05:00:00+00:00",
    })).toBe("8 Jul 2026");
  });

  it("falls back to the night's START when an older backend sends no date", () => {
    expect(lastNightLabel({ start_utc: "2026-07-08T21:00:00+00:00" })).toBe("8 Jul 2026");
    expect(lastNightLabel({ night_date: null, start_utc: "2026-07-08T21:00:00+00:00" }))
      .toBe("8 Jul 2026");
  });

  it("is null — no label at all — when the night can't be dated", () => {
    expect(lastNightLabel({ night_date: null, start_utc: null })).toBeNull();
  });
});

// The morning after the fixture's 8 Jul night — so "Last night" is honest and
// the existing phrasing assertions stay deterministic whatever day the suite runs.
const MORNING_AFTER = new Date("2026-07-09T09:00:00Z");

describe("describeLibraryNight", () => {
  it("phrases a multi-target night with the kept-vs-set-aside breakdown", () => {
    expect(describeLibraryNight(recap(), MORNING_AFTER)).toBe(
      "Last night you captured 10 subs across 2 targets (2.0 h). " +
        "8 kept; 2 set aside (2 trailed).",
    );
  });

  it("names the single target and says all kept when nothing was set aside", () => {
    const r = recap({
      n_targets: 1, n_frames: 6, n_kept: 6, n_set_aside: 0,
      session_exposure_s: 60, reject_buckets: {},
      targets: [tgt({ n_frames: 6 })],
    });
    expect(describeLibraryNight(r, MORNING_AFTER)).toBe(
      "Last night you captured 6 subs on M 31 (1 min). All 6 were kept.",
    );
  });

  it("uses the singular for a one-sub night", () => {
    const r = recap({ n_targets: 1, n_frames: 1, n_kept: 1, n_set_aside: 0,
      reject_buckets: {}, targets: [tgt({ n_frames: 1 })] });
    expect(describeLibraryNight(r, MORNING_AFTER)).toContain("captured 1 sub on M 31");
  });

  it("still says 'Last night' during the evening of the night itself", () => {
    // A walk-away user checking mid-session: the night bucket is today's date.
    expect(describeLibraryNight(recap(), new Date("2026-07-08T23:30:00Z")))
      .toContain("Last night you captured");
  });

  it("names the date instead of claiming 'last night' after a spell of cloud", () => {
    // The card isn't time-boxed — it shows the most recent night whenever that
    // was — so a fortnight later "Last night you captured" is simply untrue.
    expect(describeLibraryNight(recap(), new Date("2026-07-23T09:00:00Z"))).toBe(
      "On 8 Jul you captured 10 subs across 2 targets (2.0 h). " +
        "8 kept; 2 set aside (2 trailed).",
    );
  });

  it("adds the year once the night is no longer this year", () => {
    expect(describeLibraryNight(recap(), new Date("2027-01-05T09:00:00Z")))
      .toContain("On 8 Jul 2026 you captured");
  });

  it("buckets by the observing night, not the raw UTC start", () => {
    // 05:00 UTC on the 9th is still the night OF the 8th for a US observer; the
    // server says so, and the recency test must follow that, not the stamp.
    const r = recap({ night_date: "2026-07-08", start_utc: "2026-07-09T05:00:00+00:00" });
    expect(describeLibraryNight(r, MORNING_AFTER)).toContain("Last night you captured");
  });

  it("keeps the warm wording when the night can't be dated at all", () => {
    const r = recap({ night_date: null, start_utc: null });
    expect(describeLibraryNight(r, MORNING_AFTER)).toContain("Last night you captured");
  });
});

describe("LastNightCard", () => {
  it("renders the combined recap with a date, kept badge and target chips", async () => {
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(recap());
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Last night · 8 Jul 2026")).toBeInTheDocument());
    expect(screen.getByText("80% kept")).toBeInTheDocument();
    // Per-target chips only show for a multi-target night.
    expect(screen.getByText("M 31 · 6 subs")).toBeInTheDocument();
    expect(screen.getByText("M 42 · 4 subs")).toBeInTheDocument();
  });

  it("omits the chip row for a single-target night", async () => {
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(
      recap({ n_targets: 1, n_frames: 6, n_kept: 6, n_set_aside: 0,
        session_exposure_s: 60, reject_buckets: {}, targets: [tgt({ n_frames: 6 })] }),
    );
    renderCard();
    await waitFor(() =>
      expect(screen.getByText(/captured 6 subs on M 31/)).toBeInTheDocument());
    expect(screen.queryByText("M 31 · 6 subs")).toBeNull();
  });

  it("renders nothing when there's no datable night", async () => {
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(null);
    const { container } = renderCard();
    await waitFor(() => expect(client.api.getLastNight).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
