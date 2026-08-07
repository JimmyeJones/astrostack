import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  GalleryView, sortGallery, filterGallery, filterByCalibration, filterByMethod, isCalibrated,
  filterVideoStills, mergeGalleryEntries, videoStillCaption,
} from "./Gallery";
import * as client from "../api/client";
import type { GalleryItem, VideoStill } from "../api/client";

function item(run_id: number, safe = "M_42"): GalleryItem {
  return {
    safe, target_name: safe, run_id, output_basename: `m${run_id}`,
    timestamp_utc: "2026-05-02T00:00:00Z", n_frames_used: 5, canvas_w: 100, canvas_h: 80,
    total_exposure_s: 300, has_preview: false, has_fits: true, has_tiff: false,
    preview_url: "", options: {},
  };
}

function renderGallery() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><GalleryView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("Gallery batch apply", () => {
  it("selects images and applies a preset via the batch endpoint", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [item(1), item(2)] });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({
      builtin: [{ id: "galaxy_broadband", label: "Galaxy", group: "Built-in", ops: [] }],
      user: [],
    });
    const batch = vi.spyOn(client.api, "batchApply").mockResolvedValue({ job_id: "j1" });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderGallery();

    await waitFor(() => expect(screen.getAllByLabelText("Select for batch edit").length).toBe(2));
    fireEvent.click(screen.getAllByLabelText("Select for batch edit")[0]);
    expect(screen.getByText("1 selected")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Apply preset to selected"));
    fireEvent.click(await screen.findByText("Galaxy"));

    await waitFor(() => expect(batch).toHaveBeenCalledTimes(1));
    expect(batch.mock.calls[0][0]).toMatchObject({
      preset_id: "galaxy_broadband",
      items: [{ safe: "M_42", run_id: 1 }],
    });
  });

  it("downloads the finished picture (and raw FITS) from the fullscreen view", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [{ ...item(1), has_preview: true, preview_url: "/p/1.png" }],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();
    // Open the fullscreen viewer by clicking the card preview.
    await waitFor(() => expect(screen.getAllByRole("img").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole("img")[0]);

    // The picture control is a full-res / preview / JPEG menu (has_fits gives a
    // full-res PNG; a preview implies a jpeg too).
    const pic = await screen.findByLabelText("Download picture");
    expect(pic).not.toHaveAttribute("href");
    fireEvent.click(pic);
    expect((await screen.findByText("Full-res PNG (native size)")).closest("a")).toHaveAttribute(
      "href", "/api/targets/M_42/stack-runs/1/full-res-png");
    expect(screen.getByText("Quick preview PNG (up to 1024px)").closest("a")).toHaveAttribute(
      "href", "/api/targets/M_42/stack-runs/1/preview");
    expect(screen.getByText("JPEG (smaller — best for sharing)").closest("a")).toHaveAttribute(
      "href", "/api/targets/M_42/stack-runs/1/jpeg");
    expect(screen.getByLabelText("Download raw data")).toHaveAttribute(
      "href", "/api/targets/M_42/stack-runs/1/fits");
  });

  it("shows the integration time on a card", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [item(1)] });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();

    // 300 s → "5 min" rendered in the card's metadata line.
    await waitFor(() => expect(screen.getByText(/5 min/)).toBeInTheDocument());
  });

  it("flags a thin (1-frame) stack on its gallery tile so it can't pass as finished", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [{ ...item(1), n_frames_used: 1 }],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();

    await waitFor(() => expect(screen.getByText("1 frames")).toBeInTheDocument());
    // The honest thin-stack cue (warning triangle) rides the frame-count badge.
    expect(document.querySelector(".tabler-icon-alert-triangle")).not.toBeNull();
  });

  it("shows no thin-stack cue on a healthy gallery tile", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [{ ...item(1), n_frames_used: 40 }],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();

    await waitFor(() => expect(screen.getByText("40 frames")).toBeInTheDocument());
    expect(document.querySelector(".tabler-icon-alert-triangle")).toBeNull();
  });

  it("shows a run's label and filters by it (and by target name)", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [
        { ...item(1, "M_42"), notes: "best RGB v2" },
        { ...item(2, "NGC_7000"), notes: "cloudy night" },
      ],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();

    // Both labels are visible up front.
    await waitFor(() => expect(screen.getByText("best RGB v2")).toBeInTheDocument());
    expect(screen.getByText("cloudy night")).toBeInTheDocument();

    // Searching the label narrows to the one card.
    fireEvent.change(screen.getByPlaceholderText(/Search by label/), {
      target: { value: "rgb v2" },
    });
    await waitFor(() => expect(screen.queryByText("cloudy night")).not.toBeInTheDocument());
    expect(screen.getByText("best RGB v2")).toBeInTheDocument();

    // Searching a target name that matches nothing shows the empty message.
    fireEvent.change(screen.getByPlaceholderText(/Search by label/), {
      target: { value: "zzz-nope" },
    });
    await waitFor(() => expect(screen.getByText(/No images match/)).toBeInTheDocument());
  });

  it("filterGallery matches label, target, basename and calibration status", () => {
    const items = [
      { ...item(1, "M_42"), notes: "best RGB v2", calstat: "dark+flat" },
      { ...item(2, "NGC_7000"), notes: "cloudy night", calstat: null },
      { ...item(3, "M_31"), notes: null, calstat: "bias+flat" },
    ];
    // Empty query is a passthrough (and non-mutating).
    expect(filterGallery(items, "").map((i) => i.run_id)).toEqual([1, 2, 3]);
    expect(filterGallery(items, "   ").map((i) => i.run_id)).toEqual([1, 2, 3]);
    // Label / target / basename still match.
    expect(filterGallery(items, "rgb v2").map((i) => i.run_id)).toEqual([1]);
    expect(filterGallery(items, "ngc").map((i) => i.run_id)).toEqual([2]);
    expect(filterGallery(items, "m3").map((i) => i.run_id)).toEqual([3]);
    // Calibration status is now searchable: "flat" hits both calibrated runs,
    // "dark" only the dark+flat one.
    expect(filterGallery(items, "flat").map((i) => i.run_id)).toEqual([1, 3]);
    expect(filterGallery(items, "dark").map((i) => i.run_id)).toEqual([1]);
    // No match → empty; input untouched.
    expect(filterGallery(items, "zzz")).toEqual([]);
    expect(items.map((i) => i.run_id)).toEqual([1, 2, 3]);
  });

  it("filterByCalibration splits calibrated from uncalibrated runs", () => {
    const items = [
      { ...item(1), calstat: "dark+flat" },
      { ...item(2), calstat: null },
      { ...item(3), calstat: "" },
      { ...item(4), calstat: "flat" },
    ];
    expect(isCalibrated(items[0])).toBe(true);
    expect(isCalibrated(items[1])).toBe(false);
    expect(isCalibrated(items[2])).toBe(false);
    // "all" is a passthrough.
    expect(filterByCalibration(items, "all").map((i) => i.run_id)).toEqual([1, 2, 3, 4]);
    // Only runs that recorded a non-empty calstat.
    expect(filterByCalibration(items, "calibrated").map((i) => i.run_id)).toEqual([1, 4]);
    // The rest (null or empty).
    expect(filterByCalibration(items, "uncalibrated").map((i) => i.run_id)).toEqual([2, 3]);
    // Pure: input untouched.
    expect(items.map((i) => i.run_id)).toEqual([1, 2, 3, 4]);
  });

  it("filterByMethod keeps runs matching the coarse combine method", () => {
    const items = [
      { ...item(1), options: { drizzle: true, drizzle_scale: 2 } },
      { ...item(2), options: { min_max_reject: true } },
      { ...item(3), options: { sigma_clip: true } },
      { ...item(4), options: {} },                              // plain mean
      { ...item(5), options: { editor_recipe: [] } },           // no method key
    ];
    // "all" is a passthrough.
    expect(filterByMethod(items, "all").map((i) => i.run_id)).toEqual([1, 2, 3, 4, 5]);
    expect(filterByMethod(items, "drizzle").map((i) => i.run_id)).toEqual([1]);
    expect(filterByMethod(items, "min-max").map((i) => i.run_id)).toEqual([2]);
    expect(filterByMethod(items, "sigma-clip").map((i) => i.run_id)).toEqual([3]);
    expect(filterByMethod(items, "mean").map((i) => i.run_id)).toEqual([4]);
    // Editor/channel-combine runs (no method key) are excluded by any real filter.
    expect(filterByMethod(items, "drizzle").some((i) => i.run_id === 5)).toBe(false);
    // Pure: input untouched.
    expect(items.map((i) => i.run_id)).toEqual([1, 2, 3, 4, 5]);
  });

  it("shows the combine-method facet only for a mixed set and narrows by it", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [
        { ...item(1, "Drizzled"), options: { drizzle: true, drizzle_scale: 2 } },
        { ...item(2, "Sigma"), options: { sigma_clip: true } },
      ],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();

    await waitFor(() => expect(screen.getByRole("radio", { name: "Drizzle" })).toBeInTheDocument());
    const targetLinks = () =>
      screen.getAllByRole("link").map((l) => l.textContent).filter((t) => t === "Drizzled" || t === "Sigma");
    expect(targetLinks()).toEqual(["Drizzled", "Sigma"]);

    // Clicking the "σ-clip" segment hides the drizzled card.
    fireEvent.click(screen.getByRole("radio", { name: "σ-clip" }));
    await waitFor(() => expect(targetLinks()).toEqual(["Sigma"]));
  });

  it("hides the combine-method facet when every run used the same method", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [
        { ...item(1), options: { sigma_clip: true } },
        { ...item(2), options: { sigma_clip: true } },
      ],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();

    await waitFor(() => expect(screen.getAllByLabelText("Select for batch edit").length).toBe(2));
    expect(screen.queryByRole("radio", { name: "σ-clip" })).not.toBeInTheDocument();
  });

  it("shows the calibration filter only for a mixed set and narrows by it", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [
        { ...item(1, "Calibrated"), calstat: "dark+flat" },
        { ...item(2, "Uncalibrated"), calstat: null },
      ],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();

    await waitFor(() => expect(screen.getByRole("radio", { name: "Uncalibrated" })).toBeInTheDocument());
    const targetLinks = () =>
      screen.getAllByRole("link").map((l) => l.textContent).filter((t) => t === "Calibrated" || t === "Uncalibrated");
    expect(targetLinks()).toEqual(["Calibrated", "Uncalibrated"]);

    // Clicking the "Calibrated" segment hides the uncalibrated card.
    fireEvent.click(screen.getByRole("radio", { name: "Calibrated" }));
    await waitFor(() => expect(targetLinks()).toEqual(["Calibrated"]));
  });

  it("hides the calibration filter when every run is uncalibrated", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [{ ...item(1), calstat: null }, { ...item(2), calstat: null }],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();

    await waitFor(() => expect(screen.getAllByLabelText("Select for batch edit").length).toBe(2));
    // No calibration segment when the set isn't mixed.
    expect(screen.queryByRole("radio", { name: "Uncalibrated" })).toBeNull();
  });

  it("sortGallery puts lowest-noise stacks first and keeps unmeasured runs last", () => {
    const items = [
      { ...item(1), noise_sigma: 0.05 },
      { ...item(2), noise_sigma: null },
      { ...item(3), noise_sigma: 0.01 },
      { ...item(4), noise_sigma: 0.03 },
    ];
    // Newest preserves the API order untouched.
    expect(sortGallery(items, "newest").map((i) => i.run_id)).toEqual([1, 2, 3, 4]);
    // Cleanest: ascending σ, then the unmeasured run last in its original order.
    expect(sortGallery(items, "cleanest").map((i) => i.run_id)).toEqual([3, 4, 1, 2]);
    // Pure: the input array is not mutated.
    expect(items.map((i) => i.run_id)).toEqual([1, 2, 3, 4]);
  });

  it("shows the Cleanest sort control and reorders by noise", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [
        { ...item(1, "Noisy"), noise_sigma: 0.05 },
        { ...item(2, "Clean"), noise_sigma: 0.01 },
      ],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();

    await waitFor(() => expect(screen.getByText("Cleanest")).toBeInTheDocument());
    const order = () =>
      screen.getAllByRole("link").map((l) => l.textContent).filter((t) => t === "Noisy" || t === "Clean");
    // Newest order preserves the API order: Noisy card first.
    expect(order()).toEqual(["Noisy", "Clean"]);

    fireEvent.click(screen.getByText("Cleanest"));
    // Cleanest order: the lower-σ "Clean" target comes first.
    await waitFor(() => expect(order()).toEqual(["Clean", "Noisy"]));
  });

  it("offers a Compare link only when exactly two images are selected", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [item(1), item(2), item(3)] });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();

    await waitFor(() => expect(screen.getAllByLabelText("Select for batch edit").length).toBe(3));
    const boxes = screen.getAllByLabelText("Select for batch edit");
    fireEvent.click(boxes[0]);
    // One selected: no Compare yet.
    expect(screen.queryByRole("link", { name: /Compare/ })).toBeNull();

    fireEvent.click(boxes[1]);
    const link = await screen.findByRole("link", { name: /Compare/ });
    expect(link).toHaveAttribute("href", "/compare?a=M_42:1&b=M_42:2");

    // A third selection removes the (pairwise-only) Compare action again.
    fireEvent.click(boxes[2]);
    await waitFor(() => expect(screen.queryByRole("link", { name: /Compare/ })).toBeNull());
  });

  it("offers Reuse settings only for reusable cards", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [
        { ...item(1), reusable: true },
        { ...item(2), reusable: false },
      ],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();

    // Only the reusable card exposes the link, pointing at the Stack form.
    const links = await screen.findAllByRole("link", { name: /Reuse settings/ });
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/targets/M_42/stack?from=1");
  });

  it("shows the getting-started map on a truly empty gallery, not on a filtered-empty one", async () => {
    // A first-time user who lands on Gallery before stacking anything sees an
    // empty page; the "Your first image" checklist is the answer to "what now?".
    // But a *search* that matches nothing must not get the same pitch — the user
    // clearly already has pictures, they just filtered them out.
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [] });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getSystem").mockResolvedValue({
      version: "0.0.0", data_root: "/data", cpu_count: 4, cpu_workers: 3,
      gpu_available: false, disk: {}, memory: {}, watcher_enabled: true,
      astap: { found: false, path: null, star_db_found: false },
    } as never);
    vi.spyOn(client.api, "getStats").mockResolvedValue({
      n_targets: 0, n_frames: 0, n_frames_accepted: 0, total_exposure_s: 0,
      integration_hours: 0, acceptance_rate: null, n_stack_runs: 0,
      n_targets_with_stacks: 0, active_jobs: 0, recent_stacks: [], disk: {},
    } as never);

    const { unmount } = renderGallery();
    await waitFor(() =>
      expect(screen.getByTestId("first-image-card")).toBeInTheDocument());
    unmount();

    // With pictures present, a search that matches nothing empties the grid — but
    // that user is not at the start of the journey, so no checklist.
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [item(1)] });
    renderGallery();
    await waitFor(() => expect(screen.getByPlaceholderText(/Search/i)).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/Search/i), {
      target: { value: "nothing-matches-this" },
    });
    await waitFor(() =>
      expect(screen.getByText(/No images match/)).toBeInTheDocument());
    expect(screen.queryByTestId("first-image-card")).not.toBeInTheDocument();
  });
});

// --- Moon/Sun stills in the gallery ---------------------------------------
//
// A finished video still is a picture the user made, so it belongs where every
// other finished picture lives. It is *not* a stack run, though, so it gets a
// plain read-only card that links back to the page that owns it.

function still(capture_id: string, created_utc = "2026-05-02T00:00:00+00:00"): VideoStill {
  return {
    capture_id, label: "Moon", kind: "lunar", created_utc,
    width: 640, height: 480, n_stacked: 29, source_name: "clip.mp4",
    preview_url: `/api/videos/${capture_id}/preview.png`,
  };
}

describe("Gallery Moon & Sun stills", () => {
  it("filterVideoStills matches label, source file and capture id", () => {
    const stills = [
      { ...still("Lunar_video"), label: "Moon", source_name: "clip.mp4" },
      { ...still("Solar_2026"), label: "Sun", source_name: "midday.mov" },
    ];
    expect(filterVideoStills(stills, "").length).toBe(2);
    expect(filterVideoStills(stills, "  ").length).toBe(2);
    expect(filterVideoStills(stills, "moon").map((v) => v.capture_id)).toEqual(["Lunar_video"]);
    expect(filterVideoStills(stills, "midday").map((v) => v.capture_id)).toEqual(["Solar_2026"]);
    expect(filterVideoStills(stills, "solar_").map((v) => v.capture_id)).toEqual(["Solar_2026"]);
    expect(filterVideoStills(stills, "nope")).toEqual([]);
  });

  it("mergeGalleryEntries interleaves stills with runs by date when sorting newest", () => {
    const runs = [
      { ...item(2), timestamp_utc: "2026-05-03T00:00:00.123456+00:00" },
      { ...item(1), timestamp_utc: "2026-05-01T00:00:00.000000+00:00" },
    ];
    const stills = [still("V", "2026-05-02T00:00:00+00:00")];
    const merged = mergeGalleryEntries(runs, stills, "newest");
    expect(merged.map((e) => (e.kind === "run" ? `run${e.run.run_id}` : e.video.capture_id)))
      .toEqual(["run2", "V", "run1"]);
  });

  it("mergeGalleryEntries keeps the noise ranking intact and puts stills after it", () => {
    // A video still has no measured background σ, so it can't be ranked among
    // the cleanest stacks — it must not be given an invented position.
    const runs = [item(1), item(2)];
    const merged = mergeGalleryEntries(runs, [still("V")], "cleanest");
    expect(merged.map((e) => (e.kind === "run" ? `run${e.run.run_id}` : e.video.capture_id)))
      .toEqual(["run1", "run2", "V"]);
  });

  it("videoStillCaption says where it came from, when, how big and how many frames", () => {
    expect(videoStillCaption(still("V", "2026-05-02T21:30:00+00:00")))
      .toBe("clip.mp4 · 2026-05-02 21:30 · 640×480 · 29 frames stacked");
    expect(videoStillCaption({ ...still("V"), n_stacked: 1 })).toContain("1 frame stacked");
  });

  it("shows a finished Moon still on a card that links back to Moon & Sun", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [], videos: [still("Lunar_video")],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();

    // Fail-before: the gallery only knew about stack runs, so this said
    // "No stacked images yet".
    expect(await screen.findByText("Moon")).toBeInTheDocument();
    expect(screen.getByText(/clip\.mp4 · .* · 640×480 · 29 frames stacked/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Open in Moon & Sun/ });
    expect(link).toHaveAttribute("href", "/moon-sun");
    // Read-only: none of the per-run actions apply to a video still.
    expect(screen.queryByLabelText("Select for batch edit")).not.toBeInTheDocument();
    expect(screen.queryByText("Edit image")).not.toBeInTheDocument();
    expect(screen.queryByText("Reuse settings")).not.toBeInTheDocument();
    // ...and it counts as one of the user's pictures.
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("finds a still through the one search box and hides it under a stack-only facet", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [
        { ...item(1), notes: "best RGB v2", calstat: "dark+flat" },
        { ...item(2), notes: "cloudy night" },
      ],
      videos: [still("Lunar_video")],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();
    expect(await screen.findByText("Moon")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/Search/i), { target: { value: "moon" } });
    await waitFor(() => expect(screen.queryByText("best RGB v2")).not.toBeInTheDocument());
    expect(screen.getByText("Moon")).toBeInTheDocument();

    // "Calibrated" is a question about a stack's masters; a video still has
    // none, so it drops out rather than pretending to be calibrated.
    fireEvent.change(screen.getByPlaceholderText(/Search/i), { target: { value: "" } });
    await waitFor(() => expect(screen.getByText("Moon")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Calibrated"));
    await waitFor(() => expect(screen.queryByText("Moon")).not.toBeInTheDocument());
  });

  it("shows nothing extra when the backend sends no videos field (older server)", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [{ ...item(1), notes: "best RGB v2" }],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();
    await waitFor(() => expect(screen.getByText("best RGB v2")).toBeInTheDocument());
    expect(screen.queryByRole("link", { name: /Open in Moon & Sun/ })).not.toBeInTheDocument();
  });

  // The crop offer on the Gallery card. Moon & Sun lists the *captures* still in
  // `incoming/`, so someone who has cleared the video off the NAS only ever sees
  // their picture here — with, before this, no way to trim the empty sky.
  it("offers the crop on an uncropped still and fires it in one click", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [],
      videos: [{ ...still("Lunar_video"), crop_available: true, crop_trim_fraction: 0.78 }],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    const crop = vi.spyOn(client.api, "cropVideoStill").mockResolvedValue({
      crop_applied: true, crop_trim_fraction: 0.78, width: 300, height: 300,
    } as never);

    renderGallery();

    // Fail-before: the Gallery card had no crop offer at all.
    expect(await screen.findByText(/About 78% of this picture is empty sky/))
      .toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Crop it/ }));
    await waitFor(() => expect(crop).toHaveBeenCalledWith("Lunar_video"));
  });

  it("says a still is cropped and offers to undo it", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [],
      videos: [{
        ...still("Lunar_video"), width: 300, height: 300,
        crop_applied: true, crop_available: false, crop_trim_fraction: 0.62,
        crop_restorable: true, source_width: 640, source_height: 480,
      }],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    const undo = vi.spyOn(client.api, "restoreVideoStill").mockResolvedValue({} as never);

    renderGallery();

    expect(await screen.findByText(/Cropped to the Moon — trimmed 62% of empty sky \(from 640×480\)\./))
      .toBeInTheDocument();
    // The offer is gone once it has been taken.
    expect(screen.queryByRole("button", { name: /Crop it/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Undo crop/ }));
    await waitFor(() => expect(undo).toHaveBeenCalledWith("Lunar_video"));
  });

  it("offers no crop on a still with nothing worth trimming, and no undo without a backup",
    async () => {
      vi.spyOn(client.api, "getGallery").mockResolvedValue({
        items: [],
        videos: [
          { ...still("Full_video"), crop_available: false },
          {
            ...still("Old_crop"), crop_applied: true, crop_trim_fraction: 0.5,
            crop_restorable: false,
          },
        ],
      });
      vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
      vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

      renderGallery();
      await waitFor(() => expect(screen.getAllByText("Moon").length).toBe(2));
      expect(screen.queryByRole("button", { name: /Crop it/ })).not.toBeInTheDocument();
      // The full frame is gone (a re-stack cleared it), so undo is not offered —
      // but the card still says what happened.
      expect(screen.queryByRole("button", { name: /Undo crop/ })).not.toBeInTheDocument();
      expect(screen.getByText(/Cropped to the Moon/)).toBeInTheDocument();
    });

  // The full-quality copy. A Moon still was the only finished picture in the
  // Gallery whose fullscreen view offered nothing but the small preview PNG,
  // so sending the sharpest copy somewhere meant knowing a *different* page
  // held it — and for a user whose clip is off the NAS, that page is empty.
  it("offers the 16-bit TIFF of a still from the fullscreen view", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [],
      videos: [{
        ...still("Lunar_video"),
        tiff_url: "/api/videos/Lunar_video/download.tiff",
      }],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();
    await waitFor(() => expect(screen.getAllByRole("img").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole("img")[0]);

    // Fail-before: the still's viewer passed no `rawHref` at all.
    expect(await screen.findByLabelText("Download 16-bit TIFF")).toHaveAttribute(
      "href", "/api/videos/Lunar_video/download.tiff");
    // The picture download stays the plain PNG — there is no JPEG or full-res
    // render behind a still, so it must not become a menu offering neither.
    expect(screen.getByLabelText("Download picture"))
      .toHaveAttribute("href", "/api/videos/Lunar_video/preview.png");
  });

  it("offers the OS share sheet for a still, named for the file it sends", async () => {
    // Fail-before: the lightbox gated its Share control on a JPEG, which no
    // still has — so on a phone (where the QR is redundant with the OS's own
    // sheet) a Moon picture had no way out of the app at all.
    const nav = navigator as unknown as Record<string, unknown>;
    nav.canShare = () => true;
    const shared: ShareData[] = [];
    nav.share = async (d: ShareData) => { shared.push(d); };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(new Blob(["x"], { type: "image/png" })),
    );
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [], videos: [still("Lunar_video")],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();
    await waitFor(() => expect(screen.getAllByRole("img").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole("img")[0]);

    fireEvent.click(await screen.findByLabelText("Share picture"));
    await waitFor(() => expect(shared).toHaveLength(1));
    // A PNG called `.jpg` would confuse whatever app it lands in.
    expect((shared[0].files as File[])[0].name).toBe("moon.png");
    expect(shared[0].title).toContain("Moon");
    delete nav.canShare;
    delete nav.share;
  });

  it("offers no TIFF for a still that has none on disk", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [], videos: [{ ...still("Lunar_video"), tiff_url: null }],
    });
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });

    renderGallery();
    await waitFor(() => expect(screen.getAllByRole("img").length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByRole("img")[0]);

    expect(await screen.findByLabelText("Download picture")).toBeInTheDocument();
    expect(screen.queryByLabelText("Download 16-bit TIFF")).not.toBeInTheDocument();
  });
});
