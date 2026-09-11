import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "./Dashboard";
import * as client from "../api/client";
import type { DashboardStats, SystemInfo } from "../api/client";
import { formatStampDate } from "../format";
import { lifeListLine } from "../components/lifeListLine";
import { describeSkyCoverage } from "../components/skyCoverage";

function mkStats(): DashboardStats {
  return {
    n_targets: 0, n_frames: 0, n_frames_accepted: 0, total_exposure_s: 0,
    integration_hours: 0, acceptance_rate: null, n_stack_runs: 0,
    n_targets_with_stacks: 0, active_jobs: 0, recent_stacks: [],
    disk: { free_gb: 100, total_gb: 500 },
  };
}

function mkSystem(astap: Partial<SystemInfo["astap"]>): SystemInfo {
  return {
    version: "0.0.0", data_root: "/data", cpu_count: 4, cpu_workers: 3,
    gpu_available: false,
    astap: { found: true, path: "/usr/bin/astap", star_db_found: true, ...astap },
    disk: {}, memory: {}, watcher_enabled: false,
  };
}

function renderDashboard() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("Dashboard plate-solving readiness banner", () => {
  it("warns and links to Settings when ASTAP isn't found", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({ found: false }));

    renderDashboard();

    await waitFor(() =>
      expect(screen.getByText("Plate-solving isn't set up yet")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Fix in Settings" }))
      .toHaveAttribute("href", "/settings/plate-solving");
  });

  it("warns about a missing star database when ASTAP is found", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem")
      .mockResolvedValue(mkSystem({ found: true, star_db_found: false }));

    renderDashboard();

    await waitFor(() =>
      expect(screen.getByText("Plate-solving needs a star database")).toBeInTheDocument());
  });

  it("shows no banner when plate-solving is set up", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));

    renderDashboard();

    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());
    expect(screen.queryByText(/Plate-solving/)).not.toBeInTheDocument();
  });

  it("stays dismissed after the user closes it", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({ found: false }));

    const { container, unmount } = renderDashboard();
    await waitFor(() =>
      expect(screen.getByText("Plate-solving isn't set up yet")).toBeInTheDocument());

    const closeBtn = container.querySelector(".mantine-Alert-closeButton");
    expect(closeBtn).not.toBeNull();
    fireEvent.click(closeBtn as Element);
    await waitFor(() =>
      expect(screen.queryByText("Plate-solving isn't set up yet")).not.toBeInTheDocument());

    // Re-mounting (a fresh visit) keeps it dismissed via localStorage.
    unmount();
    renderDashboard();
    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());
    expect(screen.queryByText("Plate-solving isn't set up yet")).not.toBeInTheDocument();
  });
});

describe("Dashboard recent-stack picture download", () => {
  function statsWithRecentStack(): DashboardStats {
    return {
      ...mkStats(),
      n_stack_runs: 1, n_targets_with_stacks: 1,
      recent_stacks: [{
        safe: "m31", target_name: "M31", run_id: 7, output_basename: "m31_stack",
        timestamp_utc: "2026-07-14T00:00:00Z", n_frames_used: 100,
        has_preview: true, has_fits: true, preview_url: "/api/targets/m31/stack-runs/7/preview",
      }],
    };
  }

  it("offers a PNG or JPEG download on a recent-stack card without navigating", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(statsWithRecentStack());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));

    const clicked: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(
      function (this: HTMLAnchorElement) { clicked.push(this.href); });

    renderDashboard();
    const btn = await screen.findByLabelText("Download picture of M31");
    fireEvent.click(btn); // opens the format menu, does not navigate

    // Pick JPEG from the menu → the transient anchor gets the jpeg URL.
    fireEvent.click(await screen.findByText("JPEG (smaller — best for sharing)"));
    expect(clicked).toHaveLength(1);
    expect(clicked[0]).toContain(client.api.stackArtifactUrl("m31", 7, "jpeg"));

    // Re-open and pick the quick preview PNG → the preview URL.
    fireEvent.click(screen.getByLabelText("Download picture of M31"));
    fireEvent.click(await screen.findByText("Quick preview PNG (up to 1024px)"));
    expect(clicked).toHaveLength(2);
    expect(clicked[1]).toContain(client.api.stackArtifactUrl("m31", 7, "preview"));

    // Re-open and pick the full-res PNG → the native-resolution render URL (the
    // FITS exists, so it's offered).
    fireEvent.click(screen.getByLabelText("Download picture of M31"));
    fireEvent.click(await screen.findByText("Full-res PNG (native size)"));
    expect(clicked).toHaveLength(3);
    expect(clicked[2]).toContain(client.api.stackFullResPngUrl("m31", 7));
  });

  it("shows no download control when the recent stack has no preview", async () => {
    const stats = statsWithRecentStack();
    stats.recent_stacks[0].has_preview = false;
    vi.spyOn(client.api, "getStats").mockResolvedValue(stats);
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));

    renderDashboard();
    await waitFor(() => expect(screen.getByText("M31")).toBeInTheDocument());
    expect(screen.queryByLabelText("Download picture of M31")).not.toBeInTheDocument();
  });

  it("flags a recent mosaic that is one sub deep, though it combined nine", async () => {
    // The strip's "N frames" badge makes a claim about one pixel, so it divides
    // the run's count by its own `field_fulls` — the same reading the Target
    // page has used since v0.419.1, on the app's front page.
    const stats = statsWithRecentStack();
    stats.recent_stacks[0].n_frames_used = 9;
    stats.recent_stacks[0].field_fulls = 9;
    vi.spyOn(client.api, "getStats").mockResolvedValue(stats);
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));

    renderDashboard();
    await waitFor(() => expect(screen.getByText("9 frames")).toBeInTheDocument());
    expect(document.querySelector(".tabler-icon-alert-triangle")).not.toBeNull();
  });

  it("leaves a deep recent stack's badge plain", async () => {
    const stats = statsWithRecentStack();
    stats.recent_stacks[0].field_fulls = 9;  // a 3x3, but 100 subs deep
    vi.spyOn(client.api, "getStats").mockResolvedValue(stats);
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));

    renderDashboard();
    await waitFor(() => expect(screen.getByText("100 frames")).toBeInTheDocument());
    expect(document.querySelector(".tabler-icon-alert-triangle")).toBeNull();
  });
});

describe("Dashboard information architecture (IA slice (e))", () => {
  function statsWithStack(): DashboardStats {
    return {
      ...mkStats(),
      n_stack_runs: 1, n_targets_with_stacks: 1,
      recent_stacks: [{
        safe: "m31", target_name: "M31", run_id: 7, output_basename: "m31_stack",
        timestamp_utc: "2026-07-14T00:00:00Z", n_frames_used: 100,
        has_preview: true, has_fits: true, preview_url: "/api/targets/m31/stack-runs/7/preview",
      }],
    };
  }

  function recap(): client.LibrarySessionRecap {
    return {
      n_targets: 1, n_frames: 10, n_kept: 10, n_set_aside: 0,
      session_exposure_s: 600, kept_exposure_s: 600,
      start_utc: "2026-07-08T21:00:00+00:00", end_utc: "2026-07-08T22:00:00+00:00",
      night_date: "2026-07-08",
      targets: [{
        name: "M 31", safe: "M_31", n_frames: 10, n_kept: 10, n_set_aside: 0,
        exposure_s: 600, kept_exposure_s: 600,
      }],
      reject_buckets: {},
    };
  }

  function progress(): client.TargetProgress[] {
    return [{
      safe: "M_31", name: "M 31", total_exposure_s: 3600,
      object_type: "galaxy", goal_s: null, recent_pace_s: null,
    }];
  }

  it("opens onto your pictures, with the analysis grouped below them", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(statsWithStack());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(recap());

    renderDashboard();

    const pictures = await screen.findByText("Recent stacks");
    const insights = await screen.findByTestId("dashboard-insights");
    // The user's own pictures come *before* everything that merely describes the
    // library — the whole point of the slice.
    expect(pictures.compareDocumentPosition(insights))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    // And the analysis card really is inside that grouped area, not stacked above.
    await waitFor(() => expect(insights).toHaveTextContent(/Last night/));
  });

  it("groups the analysis cards into tabs, one group on screen at a time", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(recap());
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue(progress());

    renderDashboard();

    // Exactly the two groups that have something to say get a tab — "Tonight"'s
    // cards are all silent here, so it gets none (an empty tab is worse than no
    // tab; see `InsightTabs`).
    await waitFor(() =>
      expect(screen.getAllByRole("tab").map((t) => t.textContent))
        .toEqual(["Recent", "Progress"]));

    // Nothing was removed: the group that isn't open is still mounted (so it
    // never refetches on a switch), just out of the way.
    await waitFor(() => expect(screen.getByText(/Last night/)).toBeVisible());
    expect(screen.getByText("Target progress")).not.toBeVisible();

    fireEvent.click(screen.getByRole("tab", { name: "Progress" }));
    await waitFor(() => expect(screen.getByText("Target progress")).toBeVisible());
    expect(screen.getByText(/Last night/)).not.toBeVisible();
  });

  it("answers \"did tonight work?\" inside the Recent group, not as another stacked card", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(statsWithStack());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(recap());
    vi.spyOn(client.api, "listTargets").mockResolvedValue([{
      safe_name: "M_31", name: "M 31", ra_deg: null, dec_deg: null,
      n_frames: 10, n_frames_accepted: 10, total_exposure_s: 600,
      last_activity_utc: "2026-07-08T22:00:00+00:00", has_preview: false,
      notes: null, tags: [],
    }]);
    vi.spyOn(client.api, "bestFrame").mockResolvedValue({
      frame_id: 3, captured_utc: null, fwhm_px: 2.4, star_count: 300, n_accepted: 10,
    });

    renderDashboard();

    const insights = await screen.findByTestId("dashboard-insights");
    await waitFor(() => expect(insights).toHaveTextContent("First look"));
    // The peek is for the target that has subs but no picture, and it links there.
    expect(screen.getByText("M 31 →")).toHaveAttribute("href", "/targets/M_31");
  });

  it("gives no tab to a group whose cards have nothing to say", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(recap());
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue([]);

    renderDashboard();

    await waitFor(() => expect(screen.getByText(/Last night/)).toBeVisible());
    // One speaking group gets no tab strip at all, and a silent group never gets
    // a tab that opens onto nothing.
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
  });

  it("keeps both setup warnings in one notes area above the page title", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue({
      ...mkSystem({ found: false }),
      folders: {
        incoming: { path: "/incoming", exists: false, writable: false },
        library: { path: "/library", exists: true, writable: true },
      },
    });

    renderDashboard();

    const notes = await screen.findByTestId("dashboard-notes");
    await waitFor(() =>
      expect(notes).toHaveTextContent("Your incoming folder doesn't exist yet"));
    expect(notes).toHaveTextContent("Plate-solving isn't set up yet");
    // The notes sit above the title, like the Target page's board (slice (a)).
    expect(notes.compareDocumentPosition(screen.getByText("Dashboard")))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("tells you about an edit you saved and never exported", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));
    vi.spyOn(client.api, "getUnexportedEdits").mockResolvedValue({
      count: 1,
      items: [{
        safe: "M_31", target_name: "M 31", run_id: 4,
        timestamp_utc: "2026-08-15T21:00:00Z",
      }],
    });

    renderDashboard();

    // It joins the board rather than becoming one more always-on banner, and it
    // is the only note here, so nothing folds.
    const notes = await screen.findByTestId("dashboard-notes");
    await waitFor(() =>
      expect(notes).toHaveTextContent("You have an edit you never finished"));
    expect(screen.getByRole("link", { name: "Finish M 31" }))
      .toHaveAttribute("href", "/targets/M_31/edit/4");
  });

  it("tells you once that the library's subs aren't on disk", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));
    // The folders themselves are fine — this is the fault that hides behind a
    // healthy-looking install, which is why it needs its own note.
    vi.spyOn(client.api, "getLibraryMissingFiles").mockResolvedValue({
      n_missing: 3200, n_accepted: 8000, n_targets_missing: 11,
      targets: [{ safe: "m42", name: "M 42", n_missing: 900 }],
    });

    renderDashboard();

    const notes = await screen.findByTestId("dashboard-notes");
    await waitFor(() =>
      expect(notes).toHaveTextContent("3,200 subs across 11 targets aren't on disk"));
    // It joins the board rather than becoming one more always-on banner.
    expect(notes.compareDocumentPosition(screen.getByText("Dashboard")))
      .toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("makes the stat tiles with an obvious destination clickable", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue({
      ...mkStats(), n_targets: 7, n_stack_runs: 23, active_jobs: 2,
    });
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));

    renderDashboard();

    // The four questions with one right answer each go straight there.
    for (const [name, href] of [
      ["Targets: 7", "/library"],
      ["Stacks: 23", "/gallery"],
      ["Active jobs: 2", "/jobs"],
      ["Free disk: 100 GB", "/storage"],
    ] as const) {
      expect(await screen.findByRole("link", { name })).toHaveAttribute("href", href);
    }
    // …and the two with no single right destination stay plain text, rather than
    // being given an arbitrary one.
    expect(screen.queryByRole("link", { name: /^Integration:/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Frames:/ })).not.toBeInTheDocument();
  });

  it("says nothing about unfinished edits when there are none", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));
    vi.spyOn(client.api, "getUnexportedEdits").mockResolvedValue({ count: 0, items: [] });

    renderDashboard();

    await waitFor(() => expect(client.api.getUnexportedEdits).toHaveBeenCalled());
    expect(screen.queryByTestId("unexported-edits-note")).not.toBeInTheDocument();
  });

  it("tells you which targets you've shot more of since their last stack", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));
    // The per-target nudge has existed since v0.90.0; what nobody could answer
    // from anywhere was *which* target to open after a night's capture.
    vi.spyOn(client.api, "getNewSubsWaiting").mockResolvedValue({
      count: 2, total_new_subs: 62,
      items: [
        { safe: "M_31", target_name: "M 31", run_id: 4,
          stacked_utc: "2026-08-15T21:00:00Z", n_frames_used: 200, n_new_subs: 45 },
        { safe: "M_42", target_name: "M 42", run_id: 9,
          stacked_utc: "2026-08-10T21:00:00Z", n_frames_used: 80, n_new_subs: 17 },
      ],
    });

    renderDashboard();

    // It joins the board rather than becoming one more always-on banner.
    const notes = await screen.findByTestId("dashboard-notes");
    await waitFor(() => expect(notes)
      .toHaveTextContent("62 subs you've shot aren't in your pictures yet"));
    expect(screen.getByRole("link", { name: "M 31 · +45" }))
      .toHaveAttribute("href", "/targets/M_31/stack");
  });

  it("says nothing when every picture already has all its subs", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));
    vi.spyOn(client.api, "getNewSubsWaiting")
      .mockResolvedValue({ count: 0, total_new_subs: 0, items: [] });

    renderDashboard();

    await waitFor(() => expect(client.api.getNewSubsWaiting).toHaveBeenCalled());
    expect(screen.queryByTestId("new-subs-waiting-note")).not.toBeInTheDocument();
  });
});

describe("Dashboard integration stat", () => {
  it("shows an em-dash, not \"0.0h\", on a fresh empty library", async () => {
    // A first-time user lands on the Dashboard with zero integration. The card
    // must read "—" like its sibling stat cards, not a bare "0.0h" — and use the
    // shared formatIntegration units the rest of the app uses.
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));

    renderDashboard();

    await waitFor(() => expect(screen.getByText("Integration")).toBeInTheDocument());
    expect(screen.queryByText("0.0h")).not.toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("formats a real integration total with shared friendly units", async () => {
    vi.spyOn(client.api, "getStats")
      .mockResolvedValue({ ...mkStats(), integration_hours: 2.3 });
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));

    renderDashboard();

    // 2.3 h, spaced like formatIntegration everywhere else (not "2.3h").
    await waitFor(() => expect(screen.getByText("2.3 h")).toBeInTheDocument());
  });
});

describe("Dashboard recent-stack date", () => {
  function statsWithEveningStack(): DashboardStats {
    return {
      ...mkStats(),
      n_stack_runs: 1, n_targets_with_stacks: 1,
      recent_stacks: [{
        safe: "m31", target_name: "M31", run_id: 7, output_basename: "m31_stack",
        // 03:30 UTC — the evening of the 16th anywhere west of UTC, which is
        // exactly the case a raw `slice(0, 10)` used to date as the 17th.
        timestamp_utc: "2026-08-17T03:30:00Z", n_frames_used: 100,
        has_preview: true, has_fits: true, preview_url: "/api/targets/m31/stack-runs/7/preview",
      }],
    };
  }

  it("dates the newest picture the way every other picture surface does", async () => {
    // Found by dogfooding: the card printed the raw ISO `2026-08-17` while the
    // Gallery, History and the Target hero print "17 Aug 2026" for the same run
    // — and the raw slice is the *UTC* day, so it can name a different calendar
    // day from the surfaces that convert to local time.
    vi.spyOn(client.api, "getStats").mockResolvedValue(statsWithEveningStack());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));

    renderDashboard();
    await waitFor(() => expect(screen.getByText("M31")).toBeInTheDocument());

    const expected = formatStampDate("2026-08-17T03:30:00Z");
    expect(screen.getByText(`Stacked ${expected}`)).toBeInTheDocument();
    expect(screen.queryByText("2026-08-17")).not.toBeInTheDocument();
  });

  it("names the night the subs were shot when the run recorded one", async () => {
    // The tile's date used to be the run's own stamp, unlabelled — so a
    // re-stack of a 2024 back catalogue was captioned with today's date, on the
    // app's front page. Prefer the capture window; label whichever it is.
    const stats = statsWithEveningStack();
    stats.recent_stacks[0].capture_night_start = "2024-11-15";
    stats.recent_stacks[0].capture_night_end = "2024-11-15";
    vi.spyOn(client.api, "getStats").mockResolvedValue(stats);
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));

    renderDashboard();
    await waitFor(() => expect(screen.getByText("M31")).toBeInTheDocument());
    expect(screen.getByText("Shot 15 Nov 2024")).toBeInTheDocument();
    expect(screen.queryByText(/^Stacked /)).not.toBeInTheDocument();
  });

  it("says which date it is, so a bare stamp can't be read as a capture night", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(statsWithEveningStack());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));

    renderDashboard();
    await waitFor(() => expect(screen.getByText("M31")).toBeInTheDocument());
    expect(screen.getByText(/^Stacked /)).toBeInTheDocument();
  });

  it("prints nothing rather than 'Invalid Date' for an unreadable stamp", async () => {
    const stats = statsWithEveningStack();
    stats.recent_stacks[0].timestamp_utc = "not-a-date";
    vi.spyOn(client.api, "getStats").mockResolvedValue(stats);
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));

    renderDashboard();
    await waitFor(() => expect(screen.getByText("M31")).toBeInTheDocument());
    expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument();
    // The raw slice used to print the garbage straight onto the card.
    expect(screen.queryByText("not-a-date")).not.toBeInTheDocument();
  });
});

describe("Dashboard sky-coverage line", () => {
  it("says how much of the sky the pictures cover, in My map's own words", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));
    vi.spyOn(client.api, "skyCoverage").mockResolvedValue({
      deg2: 18.4, sky_fraction: 18.4 / 41252.96, n_pictures: 12,
      whole_sky_deg2: 41252.96,
    });

    renderDashboard();
    // Asserted against the shared helper itself, not a copy of its wording, so
    // the Dashboard and My map cannot drift into two different sentences.
    const expected = describeSkyCoverage(18.4, 18.4 / 41252.96, 12);
    await waitFor(() => expect(
      screen.getByTestId("sky-coverage-line").textContent).toContain(expected));
    // …and it lands on the map it's describing, not the real-sky atlas.
    expect(screen.getByRole("link", { name: /See it on My map/ }))
      .toHaveAttribute("href", "/sky?view=mine");
  });

  it("stays quiet until a finished picture actually carries a position", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));
    vi.spyOn(client.api, "skyCoverage").mockResolvedValue({
      deg2: 0, sky_fraction: 0, n_pictures: 0, whole_sky_deg2: 41252.96,
    });

    renderDashboard();
    await waitFor(() => expect(client.api.skyCoverage).toHaveBeenCalled());
    expect(screen.queryByTestId("sky-coverage-line")).toBeNull();
    expect(screen.queryByText(/See it on My map/)).toBeNull();
  });
});

// The life list already existed as a page; nothing on the home screen ever
// pointed at it, so the number that is its whole hook was one nobody saw.
describe("Dashboard life-list line", () => {
  it("says how many of the famous objects are in the bag, and links to the list", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));
    vi.spyOn(client.api, "lifeListCounts").mockResolvedValue({
      messier_captured: 42, messier_total: 110,
      other_captured: 5, other_total: 47,
    });

    renderDashboard();
    // Asserted against the shared helper, not a copy of its wording, so this
    // sentence and the life-list page's own header cannot drift apart.
    const expected = lifeListLine({
      messier_captured: 42, messier_total: 110,
      other_captured: 5, other_total: 47,
    });
    await waitFor(() => expect(
      screen.getByTestId("life-list-line").textContent).toContain(expected));
    expect(screen.getByRole("link", { name: /See your life list/ }))
      .toHaveAttribute("href", "/life-list");
  });

  it("stays quiet until at least one famous object is captured", async () => {
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));
    vi.spyOn(client.api, "lifeListCounts").mockResolvedValue({
      messier_captured: 0, messier_total: 110,
      other_captured: 0, other_total: 47,
    });

    renderDashboard();
    await waitFor(() => expect(client.api.lifeListCounts).toHaveBeenCalled());
    expect(screen.queryByTestId("life-list-line")).toBeNull();
  });

  it("asks for the counts only — not the whole catalog with its thumbnails", async () => {
    // The tally is one sentence; the full response is ~160 rows plus a preview
    // stat per captured target. Pinned because the cheap route is the whole
    // reason this line can sit on the page a beginner opens every session.
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));
    const full = vi.spyOn(client.api, "getLifeList");
    vi.spyOn(client.api, "lifeListCounts").mockResolvedValue({
      messier_captured: 3, messier_total: 110,
      other_captured: 0, other_total: 47,
    });

    renderDashboard();
    await waitFor(() => expect(screen.getByTestId("life-list-line")).toBeInTheDocument());
    expect(full).not.toHaveBeenCalled();
  });

  it("renders the rest of the Dashboard when the counts can't be had", async () => {
    // An older backend has no such route; the home screen must not lose its
    // stats over an advisory sentence.
    vi.spyOn(client.api, "getStats").mockResolvedValue(mkStats());
    vi.spyOn(client.api, "getSystem").mockResolvedValue(mkSystem({}));
    vi.spyOn(client.api, "lifeListCounts").mockRejectedValue(new Error("404"));

    renderDashboard();
    await waitFor(() => expect(screen.getByText("Dashboard")).toBeInTheDocument());
    expect(screen.queryByTestId("life-list-line")).toBeNull();
  });
});
