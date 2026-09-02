import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BestPicturesView } from "./BestPictures";
import * as client from "../api/client";
import type { BestPicture, VideoStill } from "../api/client";

function pic(over: Partial<BestPicture>): BestPicture {
  return {
    safe: "m31", target_name: "M31", run_id: 1, output_basename: "master",
    timestamp_utc: "2026-05-02T00:00:00Z", n_frames_used: 500,
    canvas_w: 480, canvas_h: 320, total_exposure_s: 12240, noise_sigma: 0.02,
    has_preview: true, has_fits: false, has_tiff: false,
    preview_url: "/api/targets/m31/stack-runs/1/preview", score: 1, ...over,
  };
}

function still(over: Partial<VideoStill> = {}): VideoStill {
  return {
    capture_id: "cap1", label: "Moon", kind: "lunar",
    created_utc: "2026-05-02T00:00:00Z", width: 640, height: 480, n_stacked: 300,
    source_name: "moon.avi", preview_url: "/api/moonsun/cap1/preview", ...over,
  };
}

/** The page asks for the Moon/Sun stills too, because the slideshow draws them.
 *  Default: none, which is the fresh-install shape. */
function mockGallery(videos: VideoStill[] = []) {
  return vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [], videos });
}

function renderWall() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><BestPicturesView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("BestPicturesView", () => {
  it("renders the ranked wall with target names and reason lines", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({
      items: [
        pic({ safe: "m31", target_name: "M31", run_id: 1, total_exposure_s: 12240, n_frames_used: 500 }),
        pic({ safe: "m42", target_name: "M42", run_id: 2, total_exposure_s: 3600, n_frames_used: 120, score: 0.6 }),
      ],
    });
    mockGallery();
    renderWall();
    await waitFor(() => expect(screen.getByText("M31")).toBeInTheDocument());
    expect(screen.getByText("M42")).toBeInTheDocument();
    // The "why it's good" line blends integration time and frame count.
    expect(screen.getByText("3.4 h · 500 frames")).toBeInTheDocument();
    // The top three carry a rank chip.
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("#2")).toBeInTheDocument();
  });

  it("offers to start the slideshow on the picture you're looking at", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({
      items: [
        pic({ safe: "m31", target_name: "M31", run_id: 1 }),
        pic({ safe: "m42", target_name: "M42", run_id: 2 }),
      ],
    });
    mockGallery();
    renderWall();
    await waitFor(() => expect(screen.getByText("M42")).toBeInTheDocument());
    // Open the second picture, not the first — the whole point is that the show
    // starts here rather than at the top of the ranked wall.
    fireEvent.click(document.querySelectorAll("img")[1]);
    await waitFor(() =>
      expect(screen.getByLabelText("Start the slideshow here")).toBeInTheDocument());
    expect(screen.getByLabelText("Start the slideshow here"))
      .toHaveAttribute("href", "/show?from=run%3Am42%3A2");
  });

  it("shows a friendly empty state when the wall self-hides", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({ items: [] });
    mockGallery();
    renderWall();
    await waitFor(() =>
      expect(screen.getByText(/your best pictures will gather here/i)).toBeInTheDocument());
  });

  // --- "Play slideshow" only when there is a slideshow -----------------------
  // The button used to render unconditionally, so a fresh install's *only* call
  // to action led to "Nothing to show yet". The naive gate — `items.length` —
  // would break the third test below, which is the case that matters most: a
  // beginner whose first finished picture was a Moon video.

  it("hides Play slideshow when there is nothing at all to play", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({ items: [] });
    mockGallery();
    renderWall();
    await waitFor(() =>
      expect(screen.getByText(/your best pictures will gather here/i)).toBeInTheDocument());
    expect(screen.queryByText("Play slideshow")).not.toBeInTheDocument();
  });

  it("offers Play slideshow once the wall has a picture", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({
      items: [pic({ safe: "m31", run_id: 1 })],
    });
    mockGallery();
    renderWall();
    expect(await screen.findByText("Play slideshow")).toBeInTheDocument();
  });

  it("offers Play slideshow on an EMPTY wall when a Moon still can carry the show", async () => {
    // The trap the one-line fix falls into. The show is built from the wall *and*
    // the finished Moon/Sun stills, so this beginner has a perfectly good show.
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({ items: [] });
    mockGallery([still()]);
    renderWall();
    await waitFor(() =>
      expect(screen.getByText(/your best pictures will gather here/i)).toBeInTheDocument());
    expect(await screen.findByText("Play slideshow")).toBeInTheDocument();
  });

  it("marks a pinned favourite so its place on the wall is explained", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({
      items: [
        pic({ safe: "m42", target_name: "M42", run_id: 2, score: 0.4, pinned: true }),
        pic({ safe: "m31", target_name: "M31", run_id: 1 }),
      ],
    });
    mockGallery();
    renderWall();
    await waitFor(() => expect(screen.getByText("M42")).toBeInTheDocument());
    // Exactly one badge, on the pinned card only.
    expect(screen.getAllByText("Pinned")).toHaveLength(1);
    // And the wall tells everyone how to pin one of their own.
    expect(screen.getByText(/Set as cover/)).toBeInTheDocument();
  });

  it("shows no pin badge on an ordinary auto-ranked wall", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({
      items: [pic({ safe: "m31", run_id: 1 }), pic({ safe: "m42", target_name: "M42", run_id: 2 })],
    });
    mockGallery();
    renderWall();
    await waitFor(() => expect(screen.getByText("M42")).toBeInTheDocument());
    expect(screen.queryByText("Pinned")).not.toBeInTheDocument();
  });
});
