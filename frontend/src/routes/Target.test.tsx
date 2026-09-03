import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TargetView, countNewSubsSinceStack, countQcUncheckable, describeObject, mosaicGradingNote, rejectReasonLabel } from "./Target";
import * as client from "../api/client";
import type { Frame, Target } from "../api/client";
import { formatCaptureNights } from "../format";
import { sharePictureText } from "../share";

function mkFrame(id: number, overrides: Partial<Frame> = {}): Frame {
  return {
    id, name: `f${id}.fits`, timestamp_utc: "2026-01-01T00:00:00",
    exposure_s: 30, gain: 100, width_px: 480, height_px: 320,
    bayer_pattern: "RGGB", solved: true, ra_center_deg: 10, dec_center_deg: 20,
    ra_hint_deg: null, dec_hint_deg: null, fwhm_px: 2.5, star_count: 100,
    sky_adu_median: 500, eccentricity_median: 0.4, transparency_score: 5000,
    streak_detected: false,
    accept: true, reject_reason: null, user_override: false, ...overrides,
  };
}

function mkRun(overrides: Partial<client.StackRun> = {}): client.StackRun {
  return {
    id: 1, timestamp_utc: "2026-01-01T00:00:00", output_basename: "master",
    n_frames_used: 3, canvas_w: 480, canvas_h: 320,
    coverage_min: 3, coverage_max: 3, has_fits: true, has_tiff: false,
    has_preview: true, notes: null, ...overrides,
  };
}

function mkTarget(overrides: Partial<Target> = {}): Target {
  return {
    safe_name: "M_42", name: "M42", ra_deg: 10, dec_deg: 20,
    n_frames: 3, n_frames_accepted: 3, total_exposure_s: 90,
    last_activity_utc: "2026-01-01T00:00:00", has_preview: false,
    notes: null, tags: [], ...overrides,
  };
}

function mkNight(keptExposureS: number): client.NightSummary {
  return {
    start_utc: "2026-01-01T21:00:00Z", end_utc: "2026-01-02T02:00:00Z",
    n_frames: 60, n_kept: 60, n_set_aside: 0,
    exposure_s: keptExposureS, kept_exposure_s: keptExposureS,
    median_fwhm_px: 3.2, verdict: "sharp", is_best: false, reject_buckets: {},
  };
}

function renderTarget(qc = new QueryClient()) {
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/targets/M_42"]}>
          <Routes>
            <Route path="/targets/:safe" element={<TargetView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("TargetView process action", () => {
  it("kicks off the one-click process job from the Process target button", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    const process = vi
      .spyOn(client.api, "processTarget")
      .mockResolvedValue({ job_id: "j1" });

    renderTarget();

    const btn = await screen.findByRole("button", { name: "Process this target" });
    btn.click();

    await waitFor(() => expect(process).toHaveBeenCalledWith("M_42"));
  });
});

// The label a *phone* shows. Mantine's `visibleFrom` is a CSS media query and
// jsdom has no layout, so both the wide and the narrow label are in the DOM —
// stripping the wide-only ones is what tells us what the owner reads on the
// screen he actually uses.
function phoneLabel(button: HTMLElement): string {
  const clone = button.cloneNode(true) as HTMLElement;
  clone.querySelectorAll('[class*="visible-from"]').forEach((n) => n.remove());
  return (clone.textContent ?? "").trim();
}

// The hero row groups everything you can do *with the finished picture* behind
// one "Save / share" menu, so the assertions below open it first.
async function openSaveShare() {
  fireEvent.click(
    await screen.findByRole("button", { name: "Save or share the latest picture" }),
  );
}

describe("TargetView action row on a phone", () => {
  // Found by dogfooding the running build at 420 px: every one of the page's own
  // actions — Process target, Re-run QC + Solve, History, Edit, the picture menu,
  // Stack — hid its label below `sm` and rendered as a bare icon, while the
  // *secondary* Share / Scan to phone / Wallpaper buttons kept their words. So on
  // the screen the owner reads, the two things a beginner comes to this page to
  // do were the two unlabelled squares.
  it("names every action, not just the secondary ones", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget({ has_preview: true }));
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    // Three of the six are `component={Link}`, so they are links, not buttons.
    const named: [string, "button" | "link", string][] = [
      ["Process this target", "button", "Process"],
      ["Re-run QC and Solve", "button", "Re-check"],
      ["History", "link", "History"],
      ["Edit latest stack", "link", "Edit"],
      ["Save or share the latest picture", "button", "Save"],
      ["Stack", "link", "Stack"],
    ];
    for (const [aria, role, label] of named) {
      const btn = await screen.findByRole(role, { name: aria });
      expect(phoneLabel(btn)).toBe(label);
    }
  });

  it("still spells the two long actions out in full on a wide screen", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    // Nothing was traded away for the short labels: the full wording is still
    // rendered, behind the same `visibleFrom` it always used.
    const process = await screen.findByRole("button", { name: "Process this target" });
    expect(process).toHaveTextContent("Process target");
    const recheck = await screen.findByRole("button", { name: "Re-run QC and Solve" });
    expect(recheck).toHaveTextContent("Re-run QC + Solve");
  });
});

describe("TargetView noise-reduction payoff", () => {
  it("shows the measured 'cut your noise ~N×' line on the finished stack", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns")
      .mockResolvedValue([mkRun({ id: 9, n_frames_used: 300 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    const noise = vi
      .spyOn(client.api, "oneSubVsStackNoise")
      .mockResolvedValue({ ratio: 17.4 });

    renderTarget();

    await waitFor(() => expect(noise).toHaveBeenCalledWith("M_42", 9));
    expect(
      await screen.findByText(
        "Stacking your 300 subs cut the background noise about 17×."),
    ).toBeInTheDocument();
  });

  it("omits the payoff when the latest stack has no preview to measure", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns")
      .mockResolvedValue([mkRun({ id: 9, has_preview: false })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    const noise = vi.spyOn(client.api, "oneSubVsStackNoise");

    renderTarget();

    await screen.findByRole("button", { name: "Process this target" });
    expect(noise).not.toHaveBeenCalled();
    expect(screen.queryByTestId("stack-noise-badge")).not.toBeInTheDocument();
  });
});

describe("TargetView skipped-calibration note", () => {
  it("tells the user on the target page that the newest run dropped a saved master", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 9, integration_s: 400, n_frames: 40, cards: [],
      calibration_skipped: [
        "Your saved master flat wasn't used: it was built for a different camera.",
      ],
    } as never);

    renderTarget();

    expect(
      await screen.findByText(/Your saved master flat wasn't used/),
    ).toBeInTheDocument();
  });

  it("stays silent when the newest run skipped nothing", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
      run_id: 9, integration_s: 400, n_frames: 40, cards: [],
      calibration_skipped: [],
    } as never);

    renderTarget();

    await screen.findByRole("button", { name: "Process this target" });
    await waitFor(() => expect(client.api.stackRunInfo).toHaveBeenCalled());
    expect(screen.queryByTestId("calibration-skipped-note")).not.toBeInTheDocument();
  });
});

describe("TargetView latest-picture download", () => {
  it("offers a PNG or JPEG download of the latest stack's picture", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);

    renderTarget();

    // The "Save / share" control is a menu trigger; opening it offers full-res,
    // preview, and JPEG (mkRun has a FITS, so a full-res PNG is offered).
    await openSaveShare();
    const full = await screen.findByText("Full-res PNG (native size)");
    const png = screen.getByText("Quick preview PNG (up to 1024px)");
    const jpeg = screen.getByText("JPEG (smaller — best for sharing)");
    expect(full.closest("a")).toHaveAttribute(
      "href", client.api.stackFullResPngUrl("M_42", 9));
    expect(png.closest("a")).toHaveAttribute(
      "href", client.api.stackArtifactUrl("M_42", 9, "preview"));
    expect(jpeg.closest("a")).toHaveAttribute(
      "href", client.api.stackArtifactUrl("M_42", 9, "jpeg"));
  });

  it("offers the framed keepsake beside the plain downloads", async () => {
    // A share-sheet caption doesn't travel with the file, so the plain JPEG
    // arrives on Instagram (or a printed 6x4) as an unlabelled rectangle. The
    // keepsake is the same picture with its story baked into the pixels.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    await openSaveShare();
    const keepsake = await screen.findByText("Framed keepsake");
    expect(keepsake.closest("a")).toHaveAttribute(
      "href",
      client.api.stackArtifactUrl("M_42", 9, "jpeg", false, false, true),
    );
    // Plain language, no jargon: it says what you get, not how it's made.
    expect(screen.getByText(
      "Its name, date and exposure printed on the picture")).toBeInTheDocument();
  });

  it("sends the marks and the object names with the shared keepsake", async () => {
    // The keepsake share is the one meant for other people. A scale bar, a
    // compass and the names of what's in the field are what make a picture read
    // as a real astrophoto to someone who wasn't there — and all three are
    // drawn in the browser, so without baking them in the shared file loses
    // every one. The plain share above stays naked on purpose.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    // The share control renders nothing in a browser that can't share files,
    // which is jsdom's default — so say it can.
    const nav = navigator as unknown as { share?: unknown; canShare?: unknown };
    nav.share = async () => {};
    nav.canShare = () => true;
    const url = vi.spyOn(client.api, "stackArtifactUrl");
    try {
      renderTarget();

      await openSaveShare();
      const share = await screen.findByLabelText("Share the framed keepsake");
      expect(share).toHaveTextContent("Share the keepsake");
      expect(share).toHaveTextContent(/what.s in it/);
      // keepsake + scale + label_objects, in that order.
      expect(url).toHaveBeenCalledWith(
        "M_42", 9, "jpeg", false, false, true, true, true);
      // …and the plain "Framed keepsake" download is untouched: whoever wants
      // the bare frame still has it.
      expect((await screen.findByText("Framed keepsake")).closest("a"))
        .toHaveAttribute("href", "/api/targets/M_42/stack-runs/9/jpeg?keepsake=true");
    } finally {
      delete nav.share;
      delete nav.canShare;
    }
  });

  it("offers the scale-and-compass picture beside the plain downloads", async () => {
    // The app draws both marks on screen, but a browser overlay doesn't travel
    // with the file — so the downloaded picture loses the two things that make
    // it read as a real astrophoto. This bakes them into the pixels.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    await openSaveShare();
    const marked = await screen.findByText("With scale & compass");
    expect(marked.closest("a")).toHaveAttribute(
      "href",
      client.api.stackArtifactUrl("M_42", 9, "jpeg", false, false, false, true),
    );
    expect(screen.getByText(
      "How big it is and which way is North, printed on the picture",
    )).toBeInTheDocument();
  });

  it("offers a wallpaper download of the latest stack's picture", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);

    renderTarget();

    // The three aspect presets live in the same "Save / share" menu, each
    // linking the server-side wallpaper endpoint.
    await openSaveShare();
    const phone = await screen.findByText("Phone");
    expect(phone.closest("a")).toHaveAttribute(
      "href", client.api.stackWallpaperUrl("M_42", 9, "phone"));
    expect(screen.getByText("Desktop").closest("a")).toHaveAttribute(
      "href", client.api.stackWallpaperUrl("M_42", 9, "desktop"));
    expect(screen.getByText("Square").closest("a")).toHaveAttribute(
      "href", client.api.stackWallpaperUrl("M_42", 9, "square"));
  });

  it("offers the wallpaper North-up toggle when the run has an orientation to correct", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    vi.spyOn(client.api, "stackRenderSuggestion")
      .mockResolvedValue({ stretch: null, black: null, north_up_deg: 31.2 });

    renderTarget();

    await openSaveShare();
    const toggle = await screen.findByLabelText(/orient wallpaper north up/i);
    fireEvent.click(toggle);
    expect(screen.getByText("Phone").closest("a")).toHaveAttribute(
      "href", client.api.stackWallpaperUrl("M_42", 9, "phone", true));
  });

  it("hides the wallpaper North-up toggle when the run has no orientation correction", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    vi.spyOn(client.api, "stackRenderSuggestion")
      .mockResolvedValue({ stretch: null, black: null, north_up_deg: null });

    renderTarget();

    await openSaveShare();
    await screen.findByText("Phone");
    expect(screen.queryByLabelText(/orient wallpaper north up/i)).toBeNull();
  });

  it("hides the picture and wallpaper downloads when the latest stack has no preview", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns")
      .mockResolvedValue([mkRun({ id: 9, has_preview: false })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByRole("link", { name: "History" })).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Save or share the latest picture" }))
      .not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Wallpaper/ }))
      .not.toBeInTheDocument();
  });
});

describe("TargetView hero action row grouping", () => {
  // The standing "the pages are extremely busy" item (the owner named this page):
  // the row used to be nine controls wide, four of them the same "do something
  // with the finished picture" family, with *two* dropdowns side by side
  // ("Picture" and "Wallpaper") that were both "save this picture".
  it("leaves five controls inline and folds the picture actions into one menu", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    // The job and the two navigations stay where they were…
    await screen.findByRole("button", { name: "Process this target" });
    expect(screen.getByRole("button", { name: "Re-run QC and Solve" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "History" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Edit latest stack" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Stack" })).toBeInTheDocument();
    // …and the four picture controls are gone from the row itself — not as
    // buttons and not as links — leaving exactly one dropdown in their place.
    for (const gone of [/^Picture$/, /^Wallpaper$/, "Share picture", "Scan to phone"]) {
      expect(screen.queryByRole("button", { name: gone })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: gone })).not.toBeInTheDocument();
    }
    expect(
      screen.getByRole("button", { name: "Save or share the latest picture" }),
    ).toBeInTheDocument();
  });

  it("keeps every folded action reachable inside the one menu", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    // Sharing files is feature-detected at mount, so the menu item only exists
    // on a browser that can do it.
    const nav = navigator as unknown as Record<string, unknown>;
    nav.canShare = () => true;
    nav.share = async () => {};

    renderTarget();
    await openSaveShare();

    expect(await screen.findByText("Full-res PNG (native size)")).toBeInTheDocument();
    expect(screen.getByText("Quick preview PNG (up to 1024px)")).toBeInTheDocument();
    expect(screen.getByText("JPEG (smaller — best for sharing)")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Share picture" })).toBeInTheDocument();
    expect(screen.getByText("To phone")).toBeInTheDocument();
    for (const aspect of ["Phone", "Desktop", "Square"]) {
      expect(screen.getByText(aspect)).toBeInTheDocument();
    }

    delete nav.canShare;
    delete nav.share;
  });

  it("shows the phone QR after the menu that opened it has closed", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();
    await openSaveShare();
    fireEvent.click(await screen.findByText("To phone"));

    // A popover owned by the menu item would have been unmounted with the
    // dropdown; the modal is owned by the page, so it survives.
    expect(
      await screen.findByText("Scan to get it on your phone"),
    ).toBeInTheDocument();
  });
});

describe("TargetView getting-started callout", () => {
  it("nudges a fresh target (frames but no stack yet) toward one-click Process", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    const process = vi
      .spyOn(client.api, "processTarget")
      .mockResolvedValue({ job_id: "j1" });

    renderTarget();

    // The callout is its own button (distinct accessible name from the toolbar
    // "Process this target"), so a beginner sees the highlighted next step.
    const btn = await screen.findByRole("button", { name: "Process target" });
    expect(screen.getByText("Ready to process?")).toBeInTheDocument();
    btn.click();

    await waitFor(() => expect(process).toHaveBeenCalledWith("M_42"));
  });

  it("nudges when accepted frames are still waiting to be plate-solved", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    // A stack exists, but a freshly-dropped accepted frame is still unsolved, so
    // a restack would miss it — surface the Process nudge again.
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1),
      mkFrame(2, { solved: false }),
    ]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("Ready to process?")).toBeInTheDocument());
  });

  it("stays quiet once the target is solved and stacked", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("3/3 accepted")).toBeInTheDocument());
    expect(screen.queryByText("Ready to process?")).not.toBeInTheDocument();
  });

  it("shows the total integration time collected across accepted subs", async () => {
    // total_exposure_s 90s → "2 min integration"; the honest "do I have enough
    // light yet?" signal on the page where a user decides whether to keep shooting.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ total_exposure_s: 90 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("2 min integration")).toBeInTheDocument());
  });

  it("omits the integration badge when no light has been collected", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ total_exposure_s: 0 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("3/3 accepted")).toBeInTheDocument());
    expect(screen.queryByText(/integration/)).not.toBeInTheDocument();
  });

  it("stays quiet while the plate-solve setup banner is showing", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 3, n_frames_accepted: 0 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: {
        "solve_failed:astap.exe not found. Install ASTAP from https://www.hnsky.org/astap.htm":
          3,
      },
      total: 3,
    });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { accept: false, solved: false }),
    ]);

    renderTarget();

    // The setup banner takes precedence; the generic Process nudge is suppressed.
    await waitFor(() =>
      expect(
        screen.getByText("Plate-solving isn't set up — ASTAP wasn't found"),
      ).toBeInTheDocument());
    expect(screen.queryByText("Ready to process?")).not.toBeInTheDocument();
  });
});

describe("TargetView readiness card", () => {
  it("judges integration against the object's goal and shows a verdict + bar", async () => {
    // 3 h on a galaxy (6 h goal) → "solid" half-way verdict.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ total_exposure_s: 3 * 3600 }),
    );
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M31", name: "Andromeda Galaxy", type: "galaxy",
      constellation: "Andromeda", constellation_abbr: "And",
      ra_deg: 10, dec_deg: 41, matched_by: "name",
    });
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("Is it enough yet?")).toBeInTheDocument());
    // The goal chip is editable, so it carries the default per-type goal + a
    // pencil affordance; verdict scores against the same 6 h default.
    expect(screen.getByText(/goal ~6 h/)).toBeInTheDocument();
    expect(
      screen.getByText(/3\.0 h of ~6 h — a solid start/),
    ).toBeInTheDocument();
    // The honest √N companion line: at 3 h, one more hour cuts noise ~13% more.
    expect(
      screen.getByText(/Another clear hour would cut background noise about 13% more/),
    ).toBeInTheDocument();
  });

  it("answers 'is more time worth it?' from the measured stack, replacing the √N line", async () => {
    // 3 h on a galaxy still reads "a solid start — keep going" against the 6 h
    // type goal, but the picture itself measured σ 0.016 — inside the band the
    // owner's own deep stacks land in. The measured answer supersedes the
    // goal-independent √N line, and reconciles rather than contradicting: more
    // time buys fainter detail, so it never tells them to stop.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ total_exposure_s: 3 * 3600 }),
    );
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M31", name: "Andromeda Galaxy", type: "galaxy",
      constellation: "Andromeda", constellation_abbr: "And",
      ra_deg: 10, dec_deg: 41, matched_by: "name",
    });
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ total_exposure_s: 3 * 3600, noise_sigma: 0.016, reusable: true }),
    ]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByTestId("grain-projection")).toBeInTheDocument());
    expect(screen.getByTestId("grain-projection").textContent)
      .toMatch(/background already looks clean at 3\.0 h \(grain 0\.016\)/);
    expect(screen.getByTestId("grain-projection").textContent)
      .toMatch(/fainter detail/);
    // The goal verdict is untouched — nothing was removed, only superseded.
    expect(screen.getByText(/3\.0 h of ~6 h — a solid start/)).toBeInTheDocument();
    // …and the weaker, integration-only √N line no longer duplicates it.
    expect(
      screen.queryByText(/Another clear hour would cut background noise/),
    ).not.toBeInTheDocument();
  });

  it("tells a beginner their picture is still grainy even when the goal says 'plenty'", async () => {
    // 3 h on a cluster is well past the 1.5 h type goal, so the goal verdict
    // says "plenty for a clean image" — but the stack measured σ 0.05, the very
    // bar the editor's denoise advisor calls full-strength. The measured line is
    // the one that's right, and it quotes the light this target actually needs.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ total_exposure_s: 3 * 3600 }),
    );
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M13", name: "Great Globular Cluster", type: "globular cluster",
      constellation: "Hercules", constellation_abbr: "Her",
      ra_deg: 250, dec_deg: 36, matched_by: "name",
    });
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ total_exposure_s: 3 * 3600, noise_sigma: 0.05, reusable: true }),
    ]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByTestId("grain-projection")).toBeInTheDocument());
    const text = screen.getByTestId("grain-projection").textContent ?? "";
    expect(text).toMatch(/still grainy at 3\.0 h \(grain 0\.050\)/);
    // (0.05/0.02)² = 6.25× the light → 6.3×, i.e. ~16 h more on top of the 3 h.
    expect(text).toMatch(/6\.3× the light/);
    expect(text).toMatch(/16 h more/);
    expect(screen.getByText(/plenty for a clean image/)).toBeInTheDocument();
  });

  it("uses a user-set goal over the default and labels it 'your goal'", async () => {
    // 5 h on a galaxy would be "close" at the 6 h default, but the user set a
    // 10 h goal, so it scores against 10 h (still "solid") and reads "your goal".
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ total_exposure_s: 5 * 3600 }),
    );
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M31", name: "Andromeda Galaxy", type: "galaxy",
      constellation: "Andromeda", constellation_abbr: "And",
      ra_deg: 10, dec_deg: 41, matched_by: "name",
    });
    vi.spyOn(client.api, "getIntegrationGoal").mockResolvedValue({ goal_s: 10 * 3600 });
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText(/your goal ~10 h/)).toBeInTheDocument());
    expect(screen.getByText(/5\.0 h of ~10 h/)).toBeInTheDocument();
  });

  it("projects the remaining gap forward in clear nights at the target's own pace", async () => {
    // 3 h of a 6 h galaxy goal, and the last two nights each kept 1 h → 3 more
    // clear nights. The answer a beginner actually wants after "not yet".
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ total_exposure_s: 3 * 3600 }),
    );
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M31", name: "Andromeda Galaxy", type: "galaxy",
      constellation: "Andromeda", constellation_abbr: "And",
      ra_deg: 10, dec_deg: 41, matched_by: "name",
    });
    vi.spyOn(client.api, "targetNights").mockResolvedValue([
      mkNight(3600), mkNight(3600),
    ]);
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    await waitFor(() =>
      expect(
        screen.getByText(
          /At your recent pace \(~1\.0 h of kept subs per clear night\), that's about 3 more clear nights\./,
        ),
      ).toBeInTheDocument());
  });

  it("says nothing about clear nights once the goal is met", async () => {
    // 8 h on a 6 h galaxy goal — the verdict celebrates; there's no gap to project.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ total_exposure_s: 8 * 3600 }),
    );
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M31", name: "Andromeda Galaxy", type: "galaxy",
      constellation: "Andromeda", constellation_abbr: "And",
      ra_deg: 10, dec_deg: 41, matched_by: "name",
    });
    vi.spyOn(client.api, "targetNights").mockResolvedValue([
      mkNight(3600), mkNight(3600),
    ]);
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("Is it enough yet?")).toBeInTheDocument());
    expect(screen.queryByText(/more clear night/)).not.toBeInTheDocument();
  });

  it("says nothing about clear nights from a single night of history", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ total_exposure_s: 3 * 3600 }),
    );
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M31", name: "Andromeda Galaxy", type: "galaxy",
      constellation: "Andromeda", constellation_abbr: "And",
      ra_deg: 10, dec_deg: 41, matched_by: "name",
    });
    vi.spyOn(client.api, "targetNights").mockResolvedValue([mkNight(3600)]);
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("Is it enough yet?")).toBeInTheDocument());
    expect(screen.queryByText(/recent pace/)).not.toBeInTheDocument();
  });

  it("stays hidden until any light has been collected", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ total_exposure_s: 0 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("3/3 accepted")).toBeInTheDocument());
    expect(screen.queryByText("Is it enough yet?")).not.toBeInTheDocument();
  });
});

describe("countNewSubsSinceStack", () => {
  const F = (o: Partial<Frame>) => mkFrame(1, o);
  it("returns 0 without a stack timestamp to compare against", () => {
    expect(countNewSubsSinceStack([F({})], null)).toBe(0);
    expect(countNewSubsSinceStack([F({})], undefined)).toBe(0);
  });
  it("counts only accepted+solved frames captured after the stack", () => {
    const stack = "2026-02-01T00:00:00+00:00";
    const frames = [
      F({ id: 1, timestamp_utc: "2026-02-02T00:00:00+00:00" }),                 // new: counts
      F({ id: 2, timestamp_utc: "2026-01-31T00:00:00+00:00" }),                 // older: no
      F({ id: 3, timestamp_utc: "2026-02-03T00:00:00+00:00", solved: false }),  // unsolved: no
      F({ id: 4, timestamp_utc: "2026-02-03T00:00:00+00:00", accept: false }),  // rejected: no
      F({ id: 5, timestamp_utc: null }),                                        // no time: no
    ];
    expect(countNewSubsSinceStack(frames, stack)).toBe(1);
  });
  it("normalises a naive frame timestamp to UTC (no timezone shift)", () => {
    // Frame has no offset, stack does; both denote the same instant, so a frame
    // one second later must count as exactly one new sub regardless of the
    // runner's local timezone.
    const frames = [F({ timestamp_utc: "2026-02-01T00:00:01" })];
    expect(countNewSubsSinceStack(frames, "2026-02-01T00:00:00+00:00")).toBe(1);
  });
});

describe("countQcUncheckable", () => {
  const F = (o: Partial<Frame>) => mkFrame(1, o);
  it("counts frames carrying a qc_error reject reason, any accept state", () => {
    const frames = [
      F({ id: 1, reject_reason: "qc_error:OSError: truncated" }),       // counts
      F({ id: 2, reject_reason: "qc_error:unknown", accept: false }),   // counts (rejected too)
      F({ id: 3, reject_reason: "qc:fwhm", accept: false }),            // a normal QC reject: no
      F({ id: 4, reject_reason: null }),                               // clean frame: no
    ];
    expect(countQcUncheckable(frames)).toBe(2);
  });
  it("is 0 when nothing failed to read", () => {
    expect(countQcUncheckable([F({}), F({ id: 2, reject_reason: "user" })])).toBe(0);
  });
});

describe("TargetView QC-uncheckable callout", () => {
  it("surfaces unreadable frames and re-checks them on click", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ reusable: true })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, {}),
      mkFrame(2, { reject_reason: "qc_error:OSError: truncated file" }),
    ]);
    const qcSolve = vi
      .spyOn(client.api, "qcSolve")
      .mockResolvedValue({ job_id: "j1" });

    renderTarget();

    const btn = await screen.findByRole("button", { name: "Re-check these frames" });
    expect(
      screen.getByText("1 frame couldn't be quality-checked"),
    ).toBeInTheDocument();
    btn.click();
    await waitFor(() => expect(qcSolve).toHaveBeenCalledWith("M_42"));
  });

  it("stays quiet when every frame was quality-checked", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ reusable: true })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1, {}), mkFrame(2, {})]);

    renderTarget();

    await screen.findByText("M42");
    expect(
      screen.queryByText(/couldn't be quality-checked/),
    ).not.toBeInTheDocument();
  });
});

describe("TargetView missing-files preflight", () => {
  it("warns before the stack when accepted subs aren't on disk", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ reusable: true })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1, {})]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: {}, total: 0, n_missing_files: 142, n_accepted: 500,
    });

    renderTarget();

    expect(
      await screen.findByText("142 of 500 subs aren't on disk"),
    ).toBeInTheDocument();
    // Names the fix, not just the symptom — the drive is still there to reconnect.
    expect(screen.getByText(/check it's connected/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Check again" }),
    ).toBeInTheDocument();
  });

  it("stays quiet when every accepted sub is readable", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ reusable: true })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1, {})]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: {}, total: 0, n_missing_files: 0, n_accepted: 500,
    });

    renderTarget();

    await screen.findByText("M42");
    expect(screen.queryByText(/aren't on disk/)).not.toBeInTheDocument();
  });

  it("stays quiet on an older backend that doesn't report the counts", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ reusable: true })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1, {})]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({ counts: {}, total: 0 });

    renderTarget();

    await screen.findByText("M42");
    expect(screen.queryByText(/aren't on disk/)).not.toBeInTheDocument();
  });
});

describe("TargetView framing verdict", () => {
  it("tells the user how the finished picture actually caught the target", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 7 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    const framing = vi.spyOn(client.api, "stackFraming").mockResolvedValue({
      level: "clipped",
      text: "runs off the edge of the frame — about 70% of it made it in. It would "
        + "fit whole, so just re-centre it next session.",
      coverage: 0.7,
      off_centre: 0.8,
      object_name: "Orion Nebula",
      size_arcmin: 85,
    });

    renderTarget();

    await waitFor(() => expect(framing).toHaveBeenCalledWith("M_42", 7));
    expect(
      await screen.findByText(/^Orion Nebula runs off the edge of the frame/),
    ).toBeInTheDocument();
  });

  it("says 'it's bigger than one frame' once, not twice", async () => {
    // The page carried both the *measured* verdict (top) and the object card's
    // *catalogue prediction* of the same thing (bottom), so a beginner read the
    // same mosaic-mode advice twice on one screen.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 7 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "stackFraming").mockResolvedValue({
      level: "partial",
      text: "is bigger than your frame — only about 15% of it is in this picture. "
        + "Shoot it in mosaic mode to capture all of it.",
      coverage: 0.15, off_centre: 0.1,
      object_name: "Orion Nebula", size_arcmin: 85,
    });
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M42", name: "Orion Nebula", type: "nebula",
      constellation: "Orion", constellation_abbr: "Ori",
      ra_deg: 83.8, dec_deg: -5.4, matched_by: "name", size_arcmin: 85,
      framing: { level: "mosaic", text: "is bigger than the Seestar's single frame — shoot it in mosaic mode to capture all of it." },
    });

    const { container } = renderTarget();

    expect(
      await screen.findByText(/^Orion Nebula is bigger than your frame/),
    ).toBeInTheDocument();
    // The object card is still there in full — only its duplicate line is gone.
    await waitFor(() =>
      expect(screen.getByText("A nebula in the constellation Orion."))
        .toBeInTheDocument());
    expect(container.textContent)
      .not.toContain("bigger than the Seestar's single frame");
  });

  it("keeps the catalogue framing line when no picture has measured it", async () => {
    // No stack yet → no measured verdict → the prediction is the only thing that
    // can answer "will it fit?", so it must still be shown.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M42", name: "Orion Nebula", type: "nebula",
      constellation: "Orion", constellation_abbr: "Ori",
      ra_deg: 83.8, dec_deg: -5.4, matched_by: "name", size_arcmin: 85,
      framing: { level: "mosaic", text: "is bigger than the Seestar's single frame — shoot it in mosaic mode to capture all of it." },
    });

    renderTarget();

    expect(
      await screen.findByText(/Orion Nebula is bigger than the Seestar's single frame/),
    ).toBeInTheDocument();
  });
});

describe("TargetView note board", () => {
  // The owner's top complaint was that this page opened with ~15 stacked
  // alert/note blocks before anything he came for. They are all still here and
  // still one click away — but only the most urgent two speak on first paint.
  const twoPointings = (): Frame[] => [
    ...Array.from({ length: 18 }, (_, i) =>
      mkFrame(1 + i, { ra_center_deg: 10 + ((i % 3) - 1) * 0.3, dec_center_deg: 20 })),
    ...Array.from({ length: 12 }, (_, i) =>
      mkFrame(100 + i, { ra_center_deg: 83 + ((i % 3) - 1) * 0.3, dec_center_deg: -5 })),
  ];

  it("keeps the urgent notes inline and folds the rest behind one line", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      ...twoPointings(),
      mkFrame(200, { accept: false, reject_reason: "qc_error: unreadable" }),
    ]);

    renderTarget();

    // Three notes want the page: a mixed-pointing warning, an unreadable-frame
    // warning and the "ready to process?" offer. Two slots, ranked by severity.
    const mixed = await screen.findByText("This batch looks like 2 different targets");
    expect(mixed).toBeVisible();
    expect(
      screen.getByText("1 frame couldn't be quality-checked"),
    ).toBeVisible();

    // Wait for the disclosure before asserting the fold. `NoticeBoard` counts
    // the notes that actually rendered by *measuring the DOM* (a
    // MutationObserver, because a self-hiding note decides for itself and does
    // not re-render the parent), so the demote lands one render after a note's
    // text appears — the board deliberately shows everything inline until it has
    // measured. The button is that measurement's own signal, exactly as
    // `NoticeBoard.test.tsx` waits for it; asserting straight off `findByText`
    // races that commit and went red on CI (run 1228) while passing locally.
    const more = await screen.findByRole("button", { name: /1 more note$/ });
    const offer = screen.getByText("Ready to process?");
    expect(offer).not.toBeVisible();

    // Nothing is lost: the rest are one click away, and go back when done.
    fireEvent.click(more);
    expect(screen.getByText("Ready to process?")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /Hide 1 note/ }));
    expect(screen.getByText("Ready to process?")).not.toBeVisible();
  });

  it("shows a lone note inline with no disclosure to open", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);

    renderTarget();

    expect(await screen.findByText("Ready to process?")).toBeVisible();
    expect(screen.queryByRole("button", { name: /more notes?$/ })).toBeNull();
  });
});

describe("TargetView insight tabs", () => {
  // IA slice (b) of the owner's "the pages are extremely busy" item: the nine
  // analysis cards that used to stack one below another between the picture and
  // the frames table now share one tabbed area. Nothing is gone — one group is on
  // screen at a time, the rest are one click away.
  it("groups the analysis cards behind tabs instead of stacking them", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    // Two groups have something to say: Overview (a target spanning more than one
    // night) and Quality (a stack-health note).
    vi.spyOn(client.api, "targetNights").mockResolvedValue([
      mkNight(3600),
      { ...mkNight(3600), start_utc: "2026-01-03T21:00:00Z",
        end_utc: "2026-01-04T02:00:00Z" },
    ]);
    vi.spyOn(client.api, "stackHealth").mockResolvedValue({
      run_id: 1,
      notes: [{ kind: "frames", severity: "good",
                message: "42 subs went into this picture", action: null }],
    });

    renderTarget();

    // The frames table (what the user came for) and both group tabs are there...
    const quality = await screen.findByRole("tab", { name: "Quality" });
    expect(screen.getByRole("tab", { name: "Overview" })).toBeInTheDocument();
    // ...but only the open group's cards take up the page.
    expect(screen.getByText("42 subs went into this picture")).not.toBeVisible();

    fireEvent.click(quality);
    expect(screen.getByText("42 subs went into this picture")).toBeVisible();
  });

  it("gives no tab to a group whose cards have nothing to say", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun()]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    // Only the Quality group speaks; every other card self-hides.
    vi.spyOn(client.api, "stackHealth").mockResolvedValue({
      run_id: 1,
      notes: [{ kind: "frames", severity: "good",
                message: "42 subs went into this picture", action: null }],
    });

    renderTarget();

    // A lone speaking group needs no tab strip at all — and no empty tabs are
    // offered for the groups that had nothing.
    await waitFor(() =>
      expect(screen.getByText("42 subs went into this picture")).toBeVisible());
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
  });
});

describe("TargetView mixed-pointings callout", () => {
  const cluster = (n: number, ra: number, dec: number, startId: number): Frame[] =>
    Array.from({ length: n }, (_, i) =>
      mkFrame(startId + i, {
        ra_center_deg: ra + ((i % 3) - 1) * 0.3,
        dec_center_deg: dec + ((i % 2) - 0.5) * 0.3,
      }),
    );

  it("warns when the accepted+solved subs cluster into two pointings", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ reusable: true })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      ...cluster(18, 10, 20, 1),
      ...cluster(12, 83, -5, 100),
    ]);

    renderTarget();

    expect(
      await screen.findByText("This batch looks like 2 different targets"),
    ).toBeInTheDocument();
  });

  it("stays quiet for a single pointing", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ reusable: true })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue(cluster(30, 10, 20, 1));

    renderTarget();

    await screen.findByText("M42");
    expect(
      screen.queryByText(/looks like .* different targets/),
    ).not.toBeInTheDocument();
  });

  it("one-click rejects just the odd-target frames (the minority pointing)", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ reusable: true })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      ...cluster(18, 10, 20, 1),
      ...cluster(12, 83, -5, 100), // ids 100..111 are the odd-target subs
    ]);
    const bulk = vi
      .spyOn(client.api, "bulkFrames")
      .mockResolvedValue({ changed: 12, changed_ids: [] });

    renderTarget();

    const btn = await screen.findByRole("button", {
      name: /Reject the 12 odd-target frames/,
    });
    btn.click();
    await waitFor(() =>
      expect(bulk).toHaveBeenCalledWith("M_42", {
        action: "reject",
        ids: Array.from({ length: 12 }, (_, i) => 100 + i),
      }),
    );
  });
});

describe("TargetView new-subs-since-stack nudge", () => {
  it("nudges a restack when accepted+solved subs arrived after the last stack", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ reusable: true, timestamp_utc: "2026-01-01T00:00:00+00:00" }),
    ]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { timestamp_utc: "2026-01-01T00:00:00+00:00" }),
      mkFrame(2, { timestamp_utc: "2026-02-05T00:00:00+00:00" }),  // a new night
    ]);
    const process = vi
      .spyOn(client.api, "processTarget")
      .mockResolvedValue({ job_id: "j1" });

    renderTarget();

    const btn = await screen.findByRole("button", { name: "Restack" });
    expect(screen.getByText("1 new sub since your last stack")).toBeInTheDocument();
    btn.click();
    await waitFor(() => expect(process).toHaveBeenCalledWith("M_42"));
  });

  it("stays quiet when every accepted+solved frame predates the stack", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ reusable: true, timestamp_utc: "2026-03-01T00:00:00+00:00" }),
    ]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { timestamp_utc: "2026-01-01T00:00:00+00:00" }),
      mkFrame(2, { timestamp_utc: "2026-02-01T00:00:00+00:00" }),
    ]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("3/3 accepted")).toBeInTheDocument());
    expect(screen.queryByText(/new sub/)).not.toBeInTheDocument();
  });

  it("ignores an editor-export run (non-reusable) when finding the last stack", async () => {
    // A later editor-export run must not reset the 'new subs' clock: the genuine
    // stack is old, and a newer accepted+solved sub still counts.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ id: 2, reusable: false, timestamp_utc: "2026-02-10T00:00:00+00:00" }),
      mkRun({ id: 1, reusable: true, timestamp_utc: "2026-01-01T00:00:00+00:00" }),
    ]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { timestamp_utc: "2026-02-05T00:00:00+00:00" }),
    ]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("1 new sub since your last stack")).toBeInTheDocument());
  });
});

describe("TargetView older-stack restack offer", () => {
  it("offers to re-stack a picture that can't say which night it's from", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ reusable: true, timestamp_utc: "2026-03-01T00:00:00+00:00" }),
    ]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { timestamp_utc: "2026-01-01T00:00:00+00:00" }),
    ]);
    vi.spyOn(client.api, "restackGain").mockResolvedValue({
      run_id: 1, timestamp_utc: "2026-03-01T00:00:00+00:00",
      n_frames_used: 200, n_frames_ready: 512,
      missing_capture_window: true, missing_night_count: false,
    });

    renderTarget();

    await waitFor(() =>
      expect(screen.getByTestId("restack-gain-note")).toBeInTheDocument());
  });

  it("stands down while the 'new subs' note is already offering a restack", async () => {
    // Two restack offers stacked on one page is exactly the banner-piling the
    // owner complained about — and the new-subs one is the more pressing, since
    // its restack fixes the dates too.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ reusable: true, timestamp_utc: "2026-01-01T00:00:00+00:00" }),
    ]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { timestamp_utc: "2026-02-05T00:00:00+00:00" }),  // a new night
    ]);
    vi.spyOn(client.api, "restackGain").mockResolvedValue({
      run_id: 1, timestamp_utc: "2026-01-01T00:00:00+00:00",
      n_frames_used: 200, n_frames_ready: 512,
      missing_capture_window: true, missing_night_count: false,
    });

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("1 new sub since your last stack")).toBeInTheDocument());
    expect(screen.queryByTestId("restack-gain-note")).toBeNull();
  });
});

describe("TargetView streaked badge", () => {
  it("shows a streaked-frame count for accepted frames carrying a trail", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { streak_detected: true }),
      mkFrame(2, { streak_detected: true }),
      // a rejected streaked frame should not count
      mkFrame(3, { streak_detected: true, accept: false }),
    ]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("2 streaked")).toBeInTheDocument());
  });

  it("rejects all streaked frames in one gesture from the badge action", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { streak_detected: true }),
      mkFrame(2, { streak_detected: true }),
    ]);
    const bulk = vi
      .spyOn(client.api, "bulkFrames")
      .mockResolvedValue({ changed: 2, changed_ids: [1, 2] });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderTarget();

    const btn = await screen.findByRole("button", {
      name: "Reject all streaked frames",
    });
    btn.click();

    await waitFor(() =>
      expect(bulk).toHaveBeenCalledWith("M_42", { action: "reject_streaked" }));
  });

  it("omits the badge when no accepted frame carries a trail", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1), mkFrame(2),
    ]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("3/3 accepted")).toBeInTheDocument());
    expect(screen.queryByText(/streaked/)).not.toBeInTheDocument();
  });

  it("points at Auto outlier removal, never at sigma-clip by name", async () => {
    // κ-σ dispatches from 4 subs but is mathematically blind to a *lone* trail
    // until kappa_min_frames (11 at the default κ=3). The tooltip used to read
    // "Stack with sigma-clip or drizzle outlier rejection to remove the trail",
    // so an owner with a handful of streaked subs — or any mosaic panel thinner
    // than 11 — was pointed at the one setting that would clip nothing. Auto
    // resolves to min/max down there and to κ-σ once the stack is deep enough,
    // so it is the honest advice at every depth. Naming a method here is the
    // bug; assert on the absence as well as the presence, so nobody re-adds one.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { streak_detected: true }),
    ]);

    renderTarget();

    // Mantine renders a tooltip's label only once it opens, so hover the badge.
    const badge = await screen.findByText("1 streaked");
    fireEvent.mouseEnter(badge.parentElement as HTMLElement);

    const tip = await screen.findByText(/carry a satellite\/plane trail/);
    expect(tip.textContent).toContain("Auto outlier removal");
    expect(tip.textContent).not.toContain("sigma-clip");
  });

  it("gives the metric column headers plain-language hint tooltips", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    // Each metric header is a dotted-underline span carrying a Tooltip hint, so
    // a beginner can learn what "Ecc." / "FWHM" mean without leaving the table.
    // (Some labels also appear in the frame-detail panel, so match the header
    // span by its dotted-underline styling.)
    await screen.findAllByText("Ecc.");
    for (const label of ["FWHM", "Stars", "Ecc.", "Sky", "Transp."]) {
      const header = screen.getAllByText(label).find(
        (el) => el.tagName === "SPAN"
          && (el.getAttribute("style") ?? "").includes("underline dotted"));
      expect(header, `${label} header should carry a hint`).toBeTruthy();
    }
  });

  it("also spells those hints out for a reader with no hover", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    // A tooltip opens on hover or focus, and a tap on one of these headings
    // sorts the table — so on a phone the hints above were, in practice, not
    // written at all. The disclosure carries the same words as text, and costs
    // one line until it is asked for.
    const toggle = await screen.findByTestId("frame-column-guide-toggle");
    expect(screen.queryByText(/Full-width-half-maximum/)).not.toBeInTheDocument();
    fireEvent.click(toggle);
    expect(screen.getByText(/Full-width-half-maximum/)).toBeVisible();
    expect(screen.getByText(/Median star eccentricity/)).toBeVisible();
  });
});

describe("TargetView trailed badge", () => {
  // Eight tight, round subs plus one strongly-elongated one: only the outlier
  // (both >3·MAD and above the 0.6 floor) counts as trailed.
  const trailedSet = () => [
    ...Array.from({ length: 8 }, (_, i) =>
      mkFrame(i + 1, { eccentricity_median: 0.2 })),
    mkFrame(9, { eccentricity_median: 0.85 }),
  ];

  it("counts accepted frames whose stars are strong eccentricity outliers", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget({ n_frames: 9, n_frames_accepted: 9 }));
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue(trailedSet());

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("1 trailed")).toBeInTheDocument());
  });

  it("rejects all trailed frames in one gesture from the badge action", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget({ n_frames: 9, n_frames_accepted: 9 }));
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue(trailedSet());
    const bulk = vi
      .spyOn(client.api, "bulkFrames")
      .mockResolvedValue({ changed: 1, changed_ids: [9] });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderTarget();

    const btn = await screen.findByRole("button", {
      name: "Reject all trailed frames",
    });
    btn.click();

    await waitFor(() =>
      expect(bulk).toHaveBeenCalledWith("M_42", { action: "reject_trailed" }));
  });

  it("omits the badge when the set is uniformly round", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget({ n_frames: 6, n_frames_accepted: 6 }));
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue(
      Array.from({ length: 6 }, (_, i) => mkFrame(i + 1, { eccentricity_median: 0.3 })),
    );

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("6/6 accepted")).toBeInTheDocument());
    expect(screen.queryByText(/trailed/)).not.toBeInTheDocument();
  });
});

describe("TargetView auto-grade", () => {
  function mkReport(overrides: Partial<client.GradeReport> = {}): client.GradeReport {
    return {
      sensitivity: "balanced", n_accepted: 30, n_considered: 30,
      recommendations: [], metrics_used: ["fwhm_px"], metrics_skipped: {},
      capped: false, changed_ids: null, ...overrides,
    };
  }

  it("previews outliers with reasons, applies, and offers undo", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    const preview = vi.spyOn(client.api, "autoGradePreview").mockResolvedValue(
      mkReport({
        recommendations: [{
          frame_id: 2, name: "f2.fits",
          reasons: [{
            metric: "fwhm_px", value: 8.0, typical: 3.0, z: 6.1,
            label: "much softer than typical (FWHM 8.0 px vs 3.0 px) — poor seeing, focus drift or cloud",
          }],
        }],
      }),
    );
    const apply = vi.spyOn(client.api, "autoGradeApply").mockResolvedValue(
      mkReport({ changed_ids: [2] }),
    );
    const bulk = vi.spyOn(client.api, "bulkFrames")
      .mockResolvedValue({ changed: 1, changed_ids: [2] });

    renderTarget();

    (await screen.findByRole("button", { name: /Auto-grade/ })).click();

    // The preview modal lists the flagged frame with its plain-language reason.
    await waitFor(() => expect(preview).toHaveBeenCalledWith("M_42", undefined));
    expect(await screen.findByText(/of 30 accepted frames look/)).toBeInTheDocument();
    expect(screen.getByText(/much softer than typical/)).toBeInTheDocument();

    (await screen.findByRole("button", { name: "Reject 1 frame" })).click();
    await waitFor(() => expect(apply).toHaveBeenCalledWith("M_42", undefined));

    // The apply flows into the shared undo affordance.
    const undo = await screen.findByRole("button", { name: "Undo last bulk reject" });
    undo.click();
    await waitFor(() =>
      expect(bulk).toHaveBeenCalledWith("M_42", { action: "accept", ids: [2] }));
  });

  it("shows a quiet all-consistent state when nothing is flagged", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "autoGradePreview").mockResolvedValue(mkReport());

    renderTarget();
    (await screen.findByRole("button", { name: /Auto-grade/ })).click();

    expect(await screen.findByText(/No outliers found/)).toBeInTheDocument();
    // The apply button is disabled with nothing to reject.
    const rejectBtn = screen.getByRole("button", { name: "Reject 0 frames" });
    expect(rejectBtn).toBeDisabled();
  });

  it("explains when there aren't enough graded frames yet", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "autoGradePreview").mockResolvedValue(
      mkReport({ metrics_used: [], metrics_skipped: { fwhm_px: "only 3 of 3" } }),
    );

    renderTarget();
    (await screen.findByRole("button", { name: /Auto-grade/ })).click();

    expect(await screen.findByText(/Not enough graded frames/)).toBeInTheDocument();
  });

  it("labels auto-grade rejections on frame rows", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 2, n_frames_accepted: 1 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: { "auto:grade:transparency_score": 1 }, total: 1,
    });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1),
      mkFrame(2, { accept: false, reject_reason: "auto:grade:transparency_score" }),
    ]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("Auto-grade: transparency")).toBeInTheDocument());
  });
});

describe("TargetView reject breakdown + undo", () => {
  it("shows a rejected-count badge with a why breakdown", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 5, n_frames_accepted: 3 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    const summary = vi
      .spyOn(client.api, "rejectSummary")
      .mockResolvedValue({ counts: { "qc:fwhm": 1, user: 1 }, total: 2 });

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("2 rejected")).toBeInTheDocument());
    expect(summary).toHaveBeenCalledWith("M_42");
  });

  it("shows a 'not located yet' badge when accepted subs haven't plate-solved", async () => {
    // No frames rejected (n_frames === n_frames_accepted), but the breakdown
    // reports accepted-unsolved subs — surface them so a thin stack is explained.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 5, n_frames_accepted: 5 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: {},
      total: 0,
      summary: {
        used: 0,
        dropped: 5,
        dropped_fraction: 1,
        verdict: { tone: "warn", text: "Run Plate Solve so the rest can be added." },
        buckets: [
          { key: "unsolved", label: "Not located in the sky yet", count: 5, note: "Run Plate Solve." },
        ],
      },
    });

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("5 not located yet")).toBeInTheDocument());
    // A visible "?" explainer sits beside the count so a first-timer can learn what
    // "located"/"plate-solve" means without having to hover the badge to discover it.
    expect(
      screen.getByRole("button", { name: /what does .*not located yet.* mean/i }),
    ).toBeInTheDocument();
  });

  it("stops the explainer calling the subs harmless while the setup banner blocks the target", async () => {
    // Both were on screen at once: the blocking banner saying ASTAP is missing
    // and "this blocks the whole target", and this popover a few pixels away
    // saying the same subs are "usually harmless — the located subs still stack
    // into your picture". With no solver there are no located subs. This pins
    // the wiring (the page hands the popover the banner's own verdict), which
    // the component's own tests can't see.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 5, n_frames_accepted: 5 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: {
        "solve_failed:astap.exe not found. Install ASTAP from https://www.hnsky.org/astap.htm":
          5,
      },
      total: 5,
      summary: {
        used: 0,
        dropped: 5,
        dropped_fraction: 1,
        verdict: { tone: "warn", text: "Run Plate Solve so the rest can be added." },
        buckets: [
          { key: "unsolved", label: "Not located in the sky yet", count: 5, note: "Run Plate Solve." },
        ],
      },
    });

    renderTarget();

    await waitFor(() =>
      expect(
        screen.getByText("Plate-solving isn't set up — ASTAP wasn't found"),
      ).toBeInTheDocument());
    fireEvent.click(
      screen.getByRole("button", { name: /what does .*not located yet.* mean/i }),
    );
    expect(await screen.findByText(/ASTAP — the program that does the locating/))
      .toBeInTheDocument();
    expect(screen.queryByText(/usually\s+harmless/)).toBeNull();
  });

  it("omits the plate-solve explainer when frames were only rejected, not unsolved", async () => {
    // Everything that was left out was a hand/QC reject — there's no "not located"
    // jargon to explain, so the "?" affordance must not appear.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 5, n_frames_accepted: 3 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: { user: 2 },
      total: 2,
      summary: {
        used: 3,
        dropped: 2,
        dropped_fraction: 0.4,
        verdict: { tone: "ok", text: "A couple set aside — still a solid stack." },
        buckets: [{ key: "user", label: "You rejected these", count: 2, note: "" }],
      },
    });

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("2 rejected")).toBeInTheDocument());
    expect(
      screen.queryByRole("button", { name: /what does .*not located yet.* mean/i }),
    ).toBeNull();
  });

  it("surfaces the unsolved count in the badge even when some frames were also rejected", async () => {
    // A first-light night: 2 rejected + 200 accepted-but-unsolved subs. The pill
    // must not collapse to "2 rejected" and hide the (far larger) unsolved count —
    // both are disjoint left-out sets and both silently miss the stack.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 202, n_frames_accepted: 200 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: { user: 2 },
      total: 2,
      summary: {
        used: 0,
        dropped: 202,
        dropped_fraction: 1,
        verdict: { tone: "warn", text: "Run Plate Solve so the rest can be added." },
        buckets: [
          { key: "unsolved", label: "Not located in the sky yet", count: 200, note: "Run Plate Solve." },
          { key: "user", label: "You rejected these", count: 2, note: "" },
        ],
      },
    });

    renderTarget();

    await waitFor(() =>
      expect(
        screen.getByText("2 rejected · 200 not located yet"),
      ).toBeInTheDocument());
  });

  it("shows a per-row plain-language reason chip on rejected frames", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 3, n_frames_accepted: 1 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: { "auto:streak": 1, solve_failed: 1 }, total: 2,
    });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1),
      mkFrame(2, { accept: false, reject_reason: "auto:streak" }),
      mkFrame(3, { accept: false, reject_reason: "solve_failed:no stars" }),
    ]);

    renderTarget();

    // Each rejected row shows its own plain-language reason; an accepted row shows none.
    await waitFor(() =>
      expect(screen.getByText("Auto: streak")).toBeInTheDocument());
    expect(screen.getByText("Plate-solve failed")).toBeInTheDocument();
  });

  it("rejectReasonLabel humanizes raw engine codes (used by the row badge + its tooltip)", () => {
    // Both the badge and its hover tooltip now pass reject_reason through this
    // helper, so a beginner never sees the raw `qc:fwhm` / `solve_failed:…` code.
    expect(rejectReasonLabel("solve_failed:no stars")).toBe("Plate-solve failed");
    expect(rejectReasonLabel("qc:fwhm_px")).toBe("QC: FWHM");
    expect(rejectReasonLabel("auto:grade:star_count")).toBe("Auto-grade: star count");
    expect(rejectReasonLabel("bulk:streaked")).toBe("Streaked (bulk)");
    expect(rejectReasonLabel("user")).toBe("Manual reject");
    expect(rejectReasonLabel("qc_error:OSError")).toBe("QC error");
    // None of the plain-language labels is the raw code it came from.
    for (const raw of ["solve_failed:x", "qc:fwhm_px", "auto:grade:star_count"]) {
      expect(rejectReasonLabel(raw)).not.toBe(raw);
    }
  });

  it("shows an actionable setup banner when ASTAP is missing for the whole target", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 3, n_frames_accepted: 0 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: {
        "solve_failed:astap.exe not found. Install ASTAP from https://www.hnsky.org/astap.htm":
          3,
      },
      total: 3,
    });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { accept: false, solved: false }),
    ]);

    renderTarget();

    await waitFor(() =>
      expect(
        screen.getByText("Plate-solving isn't set up — ASTAP wasn't found"),
      ).toBeInTheDocument());
    // The banner offers the one-time fix, not per-frame drops.
    expect(
      screen.getByRole("button", { name: "Re-run QC + Solve" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Settings" })).toBeInTheDocument();
  });

  it("prefers the server's solve_setup_problem classification (reliable for the database case)", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 4, n_frames_accepted: 0 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    // The stored `counts` key lacks the "no star database" phrase (the old
    // unreliable truncation case), so client-side detection alone would miss it —
    // but the server classified it, so the banner still fires.
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: { "solve_failed:Reading FITS header... found 214 stars...": 4 },
      total: 4,
      solve_setup_problem: { kind: "database", frames: 4 },
    });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { accept: false, solved: false }),
    ]);

    renderTarget();

    await waitFor(() =>
      expect(
        screen.getByText("Plate-solving needs a star database"),
      ).toBeInTheDocument());
  });

  it("shows no setup banner for ordinary per-frame solve failures", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 3, n_frames_accepted: 2 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: { "solve_failed:no solution": 1 }, total: 1,
    });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1),
      mkFrame(2),
      mkFrame(3, { accept: false, solved: false, reject_reason: "solve_failed:no solution" }),
    ]);

    renderTarget();

    await waitFor(() => expect(screen.getByText("2/3 accepted")).toBeInTheDocument());
    expect(
      screen.queryByText(/Plate-solving isn't set up/),
    ).not.toBeInTheDocument();
  });

  it("tells the user when hands-off auto-stack is waiting for more subs to be located", async () => {
    // Owner's faint-field case: 202 accepted subs, only 2 plate-solved. With
    // Auto-stack on and the v0.183.0 minimum-frames floor at 3, the walk-away
    // pass holds the target back instead of publishing a 2-frame speckle master —
    // so the page must say so plainly rather than looking idle.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 202, n_frames_accepted: 202 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);  // no stack yet
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "getSettings").mockResolvedValue({
      auto_stack: true, auto_stack_min_frames: 3,
      resolved_incoming_dir: "/in", resolved_library_root: "/lib",
    });
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: {}, total: 0,
      summary: {
        used: 2, dropped: 200, dropped_fraction: 200 / 202,
        verdict: { tone: "warn", text: "Run Plate Solve so the rest can be added." },
        buckets: [
          { key: "unsolved", label: "Not located in the sky yet", count: 200, note: "Run Plate Solve." },
        ],
      },
    });

    renderTarget();

    await waitFor(() =>
      expect(
        screen.getByText("Auto-stack is waiting for more of your subs to be located"),
      ).toBeInTheDocument());
    expect(screen.getByText(/Only 2 of your accepted subs have been located/))
      .toBeInTheDocument();
    expect(screen.getByText(/at least 3 subs are located/)).toBeInTheDocument();
  });

  it("says on the Target page when the last scan held the stack back for missing files",
    async () => {
    // The hold was explained only on the Jobs page, which is not where someone
    // whose picture stopped updating goes looking — they come here.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 787, n_frames_accepted: 787 }),
    );
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "autoStackHold").mockResolvedValue({
      offered: 787, readable: 271, unreadable: 516,
      reason: "that would be a thinner stack than this target already has",
      when_utc: "2026-08-26T02:00:00Z",
    });
    renderTarget();
    await waitFor(() =>
      expect(screen.getByTestId("autostack-hold-note")).toBeInTheDocument());
    expect(screen.getByText(
      /516 of 787 subs couldn't be read on the last scan/,
    )).toBeInTheDocument();
  });

  it("does not show the auto-stack waiting note when Auto-stack is off", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 202, n_frames_accepted: 202 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "getSettings").mockResolvedValue({
      auto_stack: false, auto_stack_min_frames: 3,
      resolved_incoming_dir: "/in", resolved_library_root: "/lib",
    });
    vi.spyOn(client.api, "rejectSummary").mockResolvedValue({
      counts: {}, total: 0,
      summary: {
        used: 2, dropped: 200, dropped_fraction: 200 / 202,
        verdict: { tone: "warn", text: "Run Plate Solve." },
        buckets: [
          { key: "unsolved", label: "Not located in the sky yet", count: 200, note: "Run Plate Solve." },
        ],
      },
    });

    renderTarget();

    await waitFor(() => expect(screen.getByText("202/202 accepted")).toBeInTheDocument());
    expect(
      screen.queryByText(/Auto-stack is waiting for more of your subs/),
    ).not.toBeInTheDocument();
  });

  it("offers Undo after a bulk reject and re-accepts exactly those ids", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { streak_detected: true }),
      mkFrame(2, { streak_detected: true }),
    ]);
    const bulk = vi
      .spyOn(client.api, "bulkFrames")
      .mockResolvedValue({ changed: 2, changed_ids: [1, 2] });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderTarget();

    const reject = await screen.findByRole("button", {
      name: "Reject all streaked frames",
    });
    reject.click();

    const undo = await screen.findByRole("button", {
      name: "Undo last bulk reject",
    });
    undo.click();

    await waitFor(() =>
      expect(bulk).toHaveBeenCalledWith("M_42", { action: "accept", ids: [1, 2] }));
  });
});

describe("describeObject helper", () => {
  it("builds a plain-language sentence with the right article and constellation", () => {
    expect(describeObject("galaxy", "Andromeda")).toBe(
      "A galaxy in the constellation Andromeda.");
    expect(describeObject("open cluster", "Taurus")).toBe(
      "An open cluster in the constellation Taurus.");
  });
  it("omits the constellation when it is unknown", () => {
    expect(describeObject("nebula", "")).toBe("A nebula.");
  });
});

describe("TargetView object-info card", () => {
  it("shows the 'what am I looking at' card when the target matches the catalog", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M42", name: "Orion Nebula", type: "nebula",
      constellation: "Orion", constellation_abbr: "Ori",
      ra_deg: 83.8, dec_deg: -5.4, matched_by: "name",
    });

    renderTarget();

    expect(await screen.findByText("Orion Nebula")).toBeInTheDocument();
    expect(screen.getByText("A nebula in the constellation Orion.")).toBeInTheDocument();
  });

  it("renders no card when the target does not match the catalog", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget({ name: "backyard" }));
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue(null);

    renderTarget();

    await screen.findByRole("button", { name: "Process this target" });
    expect(screen.queryByText(/in the constellation/)).not.toBeInTheDocument();
  });
});

describe("TargetView error state", () => {
  it("shows a recoverable error (not a broken shell) when the target 404s", async () => {
    // A deleted target / stale bookmark: api.getTarget rejects with the 404.
    vi.spyOn(client.api, "getTarget").mockRejectedValue(new Error("No target 'M_42'"));
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    renderTarget(qc);

    // The shared QueryError surfaces instead of a blank title + empty table.
    await waitFor(() =>
      expect(screen.getByText("Couldn't load this page")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("TargetView content order (IA slice (c))", () => {
  // IA slice (c) of the owner's "the pages are extremely busy" item: the page now
  // opens onto what the user came for — the finished picture and the frames table
  // — with everything that merely *describes* the target (its catalog card, the
  // insight tabs) moved below. Nothing was removed; the order changed.
  const precedes = (a: Element, b: Element) =>
    !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

  it("puts the picture and the frames table above the analysis, not below it", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M42", name: "Orion Nebula", type: "nebula",
      constellation: "Orion", constellation_abbr: "Ori",
      ra_deg: 83.8, dec_deg: -5.4, matched_by: "name",
    });
    // One insight group with something to say, so the tabbed area is rendered.
    vi.spyOn(client.api, "stackHealth").mockResolvedValue({
      run_id: 9,
      notes: [{ kind: "frames", severity: "good",
                message: "42 subs went into this picture", action: null }],
    });

    renderTarget();

    const picture = await screen.findByTestId("latest-picture");
    const table = screen.getByRole("button", { name: "Reject worst" });
    const insights = await screen.findByTestId("target-insights");
    const objectCard = screen.getByText("A nebula in the constellation Orion.");

    // The picture leads, the frames table follows it, and the analysis that used
    // to sit between them is now after both.
    expect(precedes(picture, table)).toBe(true);
    expect(precedes(table, insights)).toBe(true);
    expect(precedes(table, objectCard)).toBe(true);
    // "Is it enough yet?" stays above the fold too — beside the picture, not
    // below the table (it's the question the beginner opened the page with).
    expect(precedes(screen.getByText("Is it enough yet?"), table)).toBe(true);
  });

  it("shows the target's newest finished picture on the page itself", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ id: 9, n_frames_used: 128, total_exposure_s: 7560 }),
      mkRun({ id: 3, n_frames_used: 40 }),
    ]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    // The newest run (listStackRuns returns newest first), captioned honestly.
    const img = await screen.findByAltText("Latest stacked picture of M42");
    expect(img.getAttribute("src")).toContain("/stack-runs/9/preview");
    expect(screen.getByText(/128 frames/)).toBeInTheDocument();
  });

  it("shows no picture card on a target that has never been stacked", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    await screen.findByRole("button", { name: "Process this target" });
    expect(screen.queryByTestId("latest-picture")).not.toBeInTheDocument();
  });
});

describe("TargetView share text", () => {
  // Both share paths for the *same* picture — the header's Share button and the
  // hero card's — have to name the same date, in the app's own unambiguous
  // "17 Aug 2026" form. The header used a bare `toLocaleDateString()`, whose
  // numeric form ("8/16/2026") half the world reads the other way round, and
  // this text is what the owner posts publicly.
  function stubShare(share: (data?: ShareData) => Promise<void>) {
    const nav = navigator as unknown as Record<string, unknown>;
    nav.canShare = () => true;
    nav.share = share;
    return () => { delete nav.canShare; delete nav.share; };
  }

  /** Open the menu, press one of its share items, and return what the OS got. */
  async function shareFrom(item: string, run: Partial<client.StackRun>) {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget({ name: "M42" }));
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9, ...run })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    const share = vi.fn(async (_d?: ShareData) => {});
    const restore = stubShare(share);
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      blob: async () => new Blob([new Uint8Array([1, 2, 3])], { type: "image/jpeg" }),
    })));

    renderTarget();
    // The header's own Share control — now an item inside the "Save / share"
    // menu the hero row collapses its picture actions into.
    await openSaveShare();
    fireEvent.click(await screen.findByRole("menuitem", { name: item }));
    await waitFor(() => expect(share).toHaveBeenCalledTimes(1));
    const data = share.mock.calls[0][0] as ShareData;
    restore();
    vi.unstubAllGlobals();
    return data;
  }

  it("tells the OS share sheet the night the subs were shot, not the stack day", async () => {
    // Regression: this menu went on filling the share caption with
    // `timestamp_utc` after every other share surface was fixed, so the app's
    // most prominent picture announced itself as "captured" on the day it was
    // processed — years out on a re-stack of a back catalogue.
    const data = await shareFrom("Share picture", {
      timestamp_utc: "2026-08-17T03:30:00Z",
      capture_night_start: "2024-11-15", capture_night_end: "2024-11-18",
    });
    const expected = sharePictureText("M42", formatCaptureNights("2024-11-15", "2024-11-18"));
    expect(data.text).toBe(expected.text);
    expect(data.title).toBe(expected.title);
    expect(data.text).toContain("captured 15–18 Nov 2024");
    expect(data.text).not.toContain("2026");
    // …and specifically not the ambiguous numeric form it used to send.
    expect(data.text).not.toMatch(/\d+\/\d+\/\d{4}/);
  });

  it("shares the keepsake with the same date as the plain picture", async () => {
    const data = await shareFrom("Share the framed keepsake", {
      timestamp_utc: "2026-08-17T03:30:00Z",
      capture_night_start: "2024-11-15", capture_night_end: "2024-11-15",
    });
    expect(data.text).toBe(sharePictureText("M42", formatCaptureNights("2024-11-15", "2024-11-15")).text);
    expect(data.text).not.toContain("2026");
  });

  it("shares with no date at all when the run recorded no capture window", async () => {
    // Every run on an install that predates the window. Saying nothing is the
    // honest outcome; reaching for the stack stamp is the bug.
    const data = await shareFrom("Share picture", {
      timestamp_utc: "2026-08-17T03:30:00Z",
    });
    expect(data.text).toBe("M42");
    expect(data.text).not.toContain("captured");
  });
});

describe("mosaicGradingNote", () => {
  it("says nothing for an ordinary single-pointing target", () => {
    // The backend reports 0 when the per-panel split didn't apply, and an older
    // backend doesn't report it at all — neither should mention panels.
    expect(mosaicGradingNote(0)).toBeNull();
    expect(mosaicGradingNote(1)).toBeNull();
    expect(mosaicGradingNote(undefined)).toBeNull();
  });

  it("explains that a mosaic's panels are judged against themselves", () => {
    const note = mosaicGradingNote(6);
    expect(note).toContain("6-panel mosaic");
    expect(note).toContain("compared against itself");
    expect(note).toContain("isn't cloud");
  });
});

describe("TargetView honours the pinned cover", () => {
  // Every other surface — the Library tile, the Best wall, the montage,
  // `gallery._representative_run` — resolves the pinned cover first. This page
  // took the newest run flat, so pinning run 3 and then stacking run 4 showed a
  // *different picture* here from the one on the Library card, while this page's
  // own notes talked about "the cover".
  const pinned = () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ cover_stack_run_id: 3 }));
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ id: 4, output_basename: "newest" }),
      mkRun({ id: 3, output_basename: "pinned" }),
    ]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
  };

  it("shows, saves and edits the pinned cover rather than the newest run", async () => {
    pinned();
    renderTarget();

    const edit = await screen.findByRole("link", { name: "Edit latest stack" });
    expect(edit).toHaveAttribute("href", "/targets/M_42/edit/3");

    await openSaveShare();
    const jpeg = await screen.findByText("JPEG (smaller — best for sharing)");
    expect(jpeg.closest("a")).toHaveAttribute(
      "href", client.api.stackArtifactUrl("M_42", 3, "jpeg"));
  });

  it("says so, so a beginner doesn't think their new stack vanished", async () => {
    pinned();
    renderTarget();

    expect(await screen.findByTestId("pinned-cover-note")).toHaveTextContent(
      /pinned as this target/i);
    expect(await screen.findByText("Your picture (cover)")).toBeInTheDocument();
  });

  it("falls back to the newest picture when the pinned cover is gone", async () => {
    // Same degrade as `_representative_run`: a cover that was pruned (or whose
    // preview file has gone) must not blank the page.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ cover_stack_run_id: 77 }));
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    const edit = await screen.findByRole("link", { name: "Edit latest stack" });
    expect(edit).toHaveAttribute("href", "/targets/M_42/edit/9");
    expect(screen.queryByTestId("pinned-cover-note")).toBeNull();
  });

  it("says nothing when the pinned cover IS the newest run", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ cover_stack_run_id: 9 }));
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun({ id: 9 })]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    await screen.findByText("Your picture");
    expect(screen.queryByTestId("pinned-cover-note")).toBeNull();
  });
});

describe("TargetView hero when the newest run has no picture", () => {
  // The second half of `_representative_run`'s precedence, and the same
  // divergence A5 was about one step along: it falls back to the newest run
  // **with a preview**, not simply the newest run. Fails before: a preview-less
  // newest run (a channel-combine, or one whose preview file has gone) left this
  // page showing nothing while the Library tile went on showing the run before it.
  it("falls back to the newest run that actually has one", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget({ has_preview: true }));
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ id: 4, has_preview: false }),
      mkRun({ id: 3 }),
    ]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    const img = await screen.findByAltText("Latest stacked picture of M42");
    expect(img.getAttribute("src")).toContain("/stack-runs/3/");
    // …and it is not announced as a pinned cover: nobody pinned anything.
    expect(screen.getByText("Your picture")).toBeInTheDocument();
    expect(screen.queryByTestId("pinned-cover-note")).toBeNull();
  });

  it("still routes the action row at the newest run when nothing has a picture", async () => {
    // A target mid-first-stack: the row's Edit/Stack must keep working.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([
      mkRun({ id: 7, has_preview: false }),
    ]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);

    renderTarget();

    expect(await screen.findByRole("link", { name: "Edit latest stack" }))
      .toHaveAttribute("href", "/targets/M_42/edit/7");
  });
});

describe("TargetView frames table dates", () => {
  // The bug: the table printed `timestamp_utc` raw, so a page whose picture is
  // captioned "Shot 11 Sep 2024" listed every one of its subs as 2024-09-12 —
  // the same night, named two different ways, a few hundred pixels apart. West
  // of Greenwich that is every evening's subs, not an edge case.
  const NIGHT_SUB = { night_date: "2024-09-11", timestamp_utc: "2024-09-12T03:14:55" };

  it("names the observing night a sub belongs to, not its UTC day", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1, NIGHT_SUB)]);

    renderTarget();

    // The night the caption would name, and the clock time from the header.
    expect(await screen.findByText("11 Sep 2024 · 03:14:55")).toBeInTheDocument();
    expect(screen.queryByText("2024-09-12 03:14:55")).not.toBeInTheDocument();
    // And the heading says which of the two the date is, so the reader doesn't
    // have to work it out from a stamp that no longer looks like a UTC one.
    expect(screen.getByText("Night · time (UTC)")).toBeInTheDocument();
  });

  it("falls back to the old raw stamp when the server sends no night", async () => {
    // An older backend mid-upgrade still renders exactly as it always did.
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { night_date: undefined, timestamp_utc: "2024-09-12T03:14:55" }),
    ]);

    renderTarget();

    expect(await screen.findByText("2024-09-12 03:14:55")).toBeInTheDocument();
  });
});
