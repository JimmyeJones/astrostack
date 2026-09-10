import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  LastNightCard, describeEarlyStop, describeLibraryNight, describeNeedsLook,
  describeNewPicture, describeOvernightWork, lastNightLabel, roughDuration,
} from "./LastNightCard";
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

describe("roughDuration", () => {
  it("rounds to a quarter-hour under two hours and a half-hour above", () => {
    expect(roughDuration(95)).toBe("90 minutes");
    expect(roughDuration(100)).toBe("105 minutes");
    expect(roughDuration(180)).toBe("3 h");
    expect(roughDuration(200)).toBe("3.5 h");
    expect(roughDuration(240)).toBe("4 h");
  });

  it("never rounds a real gap away to nothing", () => {
    // The server only ever sends gaps past its own 90-minute floor, but a
    // formatter that can print "0 minutes" is one backend tweak from nonsense.
    expect(roughDuration(1)).toBe("15 minutes");
  });
});

describe("describeEarlyStop", () => {
  const stop = {
    name: "M 42", safe: "M_42",
    stopped_utc: "2026-07-08T22:00:00+00:00",
    minutes_earlier: 240, n_nights_compared: 4,
  };

  it("names the target, the gap and the innocent explanation", () => {
    const text = describeEarlyStop(stop);
    expect(text).toContain("M 42 stopped getting subs at");
    expect(text).toContain("about 4 h earlier than its last 4 nights");
    // Not an alarm: most early stops are deliberate, and a Dashboard that cries
    // wolf over bedtime is worse than one that says nothing.
    expect(text).toContain("if you didn't stop on purpose");
    expect(text.toLowerCase()).not.toContain("lost");
    expect(text.toLowerCase()).not.toContain("failed");
  });
});

describe("LastNightCard early-stop line", () => {
  it("renders the line, linked to the target, when the server sends one", async () => {
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(recap({
      early_stop: {
        name: "M 42", safe: "M_42",
        stopped_utc: "2026-07-08T22:00:00+00:00",
        minutes_earlier: 240, n_nights_compared: 4,
      },
    }));
    renderCard();
    const line = await screen.findByTestId("last-night-early-stop");
    expect(line.textContent).toContain("M 42 stopped getting subs at");
    expect(screen.getByRole("link", { name: /M 42 stopped getting subs/ }))
      .toHaveAttribute("href", "/targets/M_42");
  });

  it("renders nothing extra on an ordinary night, or against an older backend", async () => {
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(recap());
    renderCard();
    await waitFor(() => expect(screen.getByText(/Last night/)).toBeInTheDocument());
    expect(screen.queryByTestId("last-night-early-stop")).toBeNull();
  });
});

describe("describeNewPicture", () => {
  const pic = {
    name: "M 42", safe: "M_42", run_id: 7,
    when_utc: "2026-07-09T04:00:00+00:00", n_frames: 120, previous_frames: 78,
  };

  it("says how much deeper the new picture is than the one it replaced", () => {
    expect(describeNewPicture(pic)).toBe(
      "M 42 — 120 subs, deeper than the 78 it had before");
  });

  it("says 'first picture' rather than comparing against nothing", () => {
    expect(describeNewPicture({ ...pic, previous_frames: null })).toBe(
      "M 42 — its first picture, from 120 subs");
    expect(describeNewPicture({ ...pic, previous_frames: undefined })).toContain(
      "its first picture");
  });

  it("never claims 'deeper' for a re-stack that used the same subs or fewer", () => {
    // A re-stack after some subs were set aside is a *new* picture, but it is
    // not a deeper one, and saying so would be a lie the owner can measure.
    expect(describeNewPicture({ ...pic, n_frames: 78 })).toBe("M 42 — 78 subs");
    expect(describeNewPicture({ ...pic, n_frames: 60 })).toBe("M 42 — 60 subs");
  });

  it("uses the singular for a one-sub picture", () => {
    expect(describeNewPicture({ ...pic, n_frames: 1, previous_frames: null }))
      .toContain("from 1 sub");
  });
});

describe("describeOvernightWork", () => {
  const pic = {
    name: "M 42", safe: "M_42", run_id: 7,
    when_utc: "2026-07-09T04:00:00+00:00", n_frames: 120, previous_frames: 78,
  };

  it("is null when the app made nothing — the card stays as it was", () => {
    expect(describeOvernightWork([])).toBeNull();
  });

  it("counts the pictures, singular and plural", () => {
    expect(describeOvernightWork([pic])).toBe(
      "While you were away, AstroStack made a new picture.");
    expect(describeOvernightWork([pic, { ...pic, safe: "M_31", run_id: 8 }])).toBe(
      "While you were away, AstroStack made 2 new pictures.");
  });
});

describe("describeNeedsLook", () => {
  it("words a missing-files hold as something outside the app to go and check", () => {
    const text = describeNeedsLook({
      name: "NGC 7000", safe: "NGC_7000", kind: "missing_files",
      n_frames: 271, n_other: 516,
    });
    expect(text).toContain("NGC 7000 is waiting");
    expect(text).toContain("516 of its subs had no file on disk");
    // The reassurance matters: the app kept the good picture rather than
    // publishing a thinner one over it.
    expect(text).toContain("existing picture was kept");
    expect(text).toContain("drive");
  });

  it("words a thin hold as patience, not a problem", () => {
    const text = describeNeedsLook({
      name: "NGC 7000", safe: "NGC_7000", kind: "too_thin",
      n_frames: 3, n_other: 8,
    });
    expect(text).toContain("only 3 of its subs are located");
    expect(text).toContain("needs 8");
    expect(text).toContain("stack itself once more subs come in");
    expect(text).not.toContain("drive");
  });

  it("words a mosaic held on depth about its panels, not about locating subs", () => {
    // Fail-before: "only 9 of its subs are located so far, and it needs 3" —
    // a sentence arguing with its own numbers, on a target whose every sub is
    // located and whose count is three times the floor.
    const text = describeNeedsLook({
      name: "M 31", safe: "M_31", kind: "too_thin",
      n_frames: 9, n_other: 3, panel_depth: 1, panels: 9,
    });
    expect(text).toContain("its 9 subs are spread over 9 panels");
    expect(text).toContain("only 1 sub on it");
    expect(text).toContain("needs 3");
    expect(text).not.toContain("are located so far");
    expect(text).toContain("shot the mosaic a few more times");
  });

  it("keeps the single-field wording against a backend that sends no panels", () => {
    const text = describeNeedsLook({
      name: "NGC 7000", safe: "NGC_7000", kind: "too_thin",
      n_frames: 3, n_other: 8, panel_depth: 0, panels: 0,
    });
    expect(text).toContain("only 3 of its subs are located");
  });
});

describe("LastNightCard overnight digest", () => {
  const pic = {
    name: "M 42", safe: "M_42", run_id: 7,
    when_utc: "2026-07-09T04:00:00+00:00", n_frames: 120, previous_frames: 78,
  };

  it("lists each picture the app made, linked to that target's history", async () => {
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(recap({
      since_utc: "2026-07-08T21:00:00+00:00", new_pictures: [pic],
    }));
    renderCard();
    const block = await screen.findByTestId("last-night-new-pictures");
    expect(block.textContent).toContain("AstroStack made a new picture");
    expect(block.textContent).toContain("deeper than the 78 it had before");
    expect(screen.getByRole("link", { name: /M 42 — 120 subs/ }))
      .toHaveAttribute("href", "/targets/M_42/history");
  });

  it("explains a held target where the news is, linked to it", async () => {
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(recap({
      needs_look: [{ name: "NGC 7000", safe: "NGC_7000", kind: "missing_files",
        n_frames: 271, n_other: 516 }],
    }));
    renderCard();
    const line = await screen.findByTestId("last-night-needs-look-missing_files");
    expect(line.textContent).toContain("NGC 7000 is waiting");
    expect(screen.getByRole("link", { name: /NGC 7000 is waiting/ }))
      .toHaveAttribute("href", "/targets/NGC_7000");
  });

  it("adds nothing on a night the app did nothing, or against an older backend", async () => {
    // The owner's live settings have auto-stack off: this is the ordinary case,
    // and the card must look exactly as it did before the digest existed.
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(recap());
    renderCard();
    await waitFor(() => expect(screen.getByText(/Last night/)).toBeInTheDocument());
    expect(screen.queryByTestId("last-night-new-pictures")).toBeNull();
    expect(screen.queryByTestId("last-night-needs-look-missing_files")).toBeNull();
    expect(screen.queryByTestId("last-night-needs-look-too_thin")).toBeNull();
  });
});
