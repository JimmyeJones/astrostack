import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  GalleryView, sortGallery, filterGallery, filterByCalibration, filterByMethod, isCalibrated,
} from "./Gallery";
import * as client from "../api/client";
import type { GalleryItem } from "../api/client";

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

    // The picture control is a PNG/JPEG menu (a preview implies a jpeg too).
    const pic = await screen.findByLabelText("Download picture");
    expect(pic).not.toHaveAttribute("href");
    fireEvent.click(pic);
    expect((await screen.findByText("PNG (best quality)")).closest("a")).toHaveAttribute(
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
});
