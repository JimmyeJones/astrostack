import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

function still(over: Partial<VideoStill>): VideoStill {
  return {
    capture_id: "cap1", label: "Moon", kind: "lunar",
    created_utc: "2026-05-03T00:00:00Z", width: 800, height: 600,
    n_stacked: 400, source_name: "moon.avi",
    preview_url: "/api/videos/cap1/preview", ...over,
  };
}

/** The wall now also reads the gallery, because the slideshow it links to draws
 *  Moon/Sun stills too. Default it to an empty library; the tests that care
 *  re-spy it. */
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
  beforeEach(() => { mockGallery(); });

  it("renders the ranked wall with target names and reason lines", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({
      items: [
        pic({ safe: "m31", target_name: "M31", run_id: 1, total_exposure_s: 12240, n_frames_used: 500 }),
        pic({ safe: "m42", target_name: "M42", run_id: 2, total_exposure_s: 3600, n_frames_used: 120, score: 0.6 }),
      ],
    });
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

  it("still offers the slideshow over the one picture its own wall hides",
    async () => {
      // A beginner's first finished target: the wall self-hides (nothing to
      // curate) and used to hide the "Play slideshow" button with it, over a
      // picture that plays perfectly well. The count says otherwise.
      vi.spyOn(client.api, "getGalleryBest")
        .mockResolvedValue({ items: [], n_finished: 1 });
      renderWall();
      await waitFor(() => expect(
        screen.getByRole("link", { name: /play slideshow/i }))
        .toHaveAttribute("href", "/show"));
      // The wall itself is still honest about having nothing to rank.
      expect(screen.getByText(/your best pictures will gather here/i))
        .toBeInTheDocument();
    });

  it("keeps the wall's own two-picture floor, which the slideshow lowers",
    async () => {
      // `/show` asks the same endpoint with `min_targets=1`, because playing
      // one picture is a show while a wall of one is nothing to curate. This
      // page must keep asking without it — and the two answers must not share a
      // react-query cache entry, or which page loaded first would decide what
      // the other shows.
      const best = vi.spyOn(client.api, "getGalleryBest")
        .mockResolvedValue({ items: [] });
      renderWall();
      await waitFor(() => expect(best).toHaveBeenCalled());
      for (const call of best.mock.calls) expect(call[1]).toBeUndefined();
    });

  it("shows a friendly empty state when the wall self-hides, and does not offer "
    + "a slideshow of nothing", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({ items: [] });
    renderWall();
    await waitFor(() =>
      expect(screen.getByText(/your best pictures will gather here/i)).toBeInTheDocument());
    // The button used to render unconditionally, so a fresh install's only call
    // to action led to an empty show.
    await waitFor(() =>
      expect(screen.queryByRole("link", { name: /play slideshow/i })).not.toBeInTheDocument());
  });

  it("still offers the slideshow when the only finished picture is a Moon still",
    async () => {
      // The trap in the obvious fix: this library's ranked wall is empty, but the
      // show draws video stills too, so there is a perfectly good slideshow here.
      vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({ items: [] });
      mockGallery([still({ capture_id: "c1" })]);
      renderWall();
      await waitFor(() =>
        expect(screen.getByRole("link", { name: /play slideshow/i }))
          .toHaveAttribute("href", "/show"));
    });

  it("offers the slideshow on a wall that has pictures", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({ items: [pic({})] });
    renderWall();
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /play slideshow/i })).toBeInTheDocument());
  });

  it("keeps the button when the gallery can't be read — unknown is not empty",
    async () => {
      vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({ items: [] });
      vi.spyOn(client.api, "getGallery").mockRejectedValue(new Error("offline"));
      renderWall();
      // /show has its own graceful "nothing to show yet" state, so erring towards
      // offering it costs a dead click; erring the other way hides a working show.
      await waitFor(() =>
        expect(screen.getByRole("link", { name: /play slideshow/i })).toBeInTheDocument());
    });

  it("marks a pinned favourite so its place on the wall is explained", async () => {
    vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({
      items: [
        pic({ safe: "m42", target_name: "M42", run_id: 2, score: 0.4, pinned: true }),
        pic({ safe: "m31", target_name: "M31", run_id: 1 }),
      ],
    });
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
    renderWall();
    await waitFor(() => expect(screen.getByText("M42")).toBeInTheDocument());
    expect(screen.queryByText("Pinned")).not.toBeInTheDocument();
  });
});

// The last surface of the "one picture, two captions" class (v0.453.0 /
// v0.453.1). This is the page you open to *show someone your pictures*, and its
// viewer handed the OS share sheet the target's name and a date while the same
// picture, shared from the Target page, History or the Gallery, went out with
// its whole story.
describe("BestPicturesView — the caption a shared picture carries", () => {
  function stubShare(share: (d?: ShareData) => Promise<void>) {
    const nav = navigator as unknown as Record<string, unknown>;
    nav.canShare = () => true;
    nav.share = share;
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      blob: async () => new Blob([new Uint8Array([1])], { type: "image/jpeg" }),
    })));
    return () => {
      delete nav.canShare; delete nav.share; vi.unstubAllGlobals();
    };
  }

  const identified = (over: Partial<BestPicture> = {}) => pic({
    n_frames_used: 240, total_exposure_s: 2400,
    capture_night_start: "2024-11-15", capture_night_end: "2024-11-15",
    object_id: "M42", object_name: "Orion Nebula", object_type: "nebula",
    blurb: "A vast stellar nursery.", ...over,
  });

  const openAndShare = async (share: ReturnType<typeof vi.fn>) => {
    renderWall();
    const img = await screen.findByRole("img");
    fireEvent.click(img);
    await screen.findByRole("dialog");
    fireEvent.click(await screen.findByLabelText("Share picture"));
    await waitFor(() => expect(share).toHaveBeenCalledTimes(1));
    return (share.mock.calls[0][0] as ShareData).text ?? "";
  };

  it("shares the ready-to-post sentence, named off the row's own catalog match",
    async () => {
      // No per-picture lookup: the wall's endpoint already resolved the match to
      // fill `object_type`/`blurb`, so the name and designation ride along.
      mockGallery();
      vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({
        items: [identified()],
      });
      const identify = vi.spyOn(client.api, "identifyTarget").mockResolvedValue(null);
      const share = vi.fn(async (_d?: ShareData) => {});
      const restore = stubShare(share);

      const text = await openAndShare(share);

      expect(text).toContain("Orion Nebula (M42)");
      expect(text).toContain("a stack of 240 subs (40 min total)");
      expect(text).toContain("shot on 15 Nov 2024 with a Seestar");
      expect(text).toContain("A vast stellar nursery.");
      expect(identify).not.toHaveBeenCalled();
      restore();
    });

  it("adds the scale sentence, measured on the picture being handed over",
    async () => {
      mockGallery();
      vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({
        items: [identified({ has_fits: true })],
      });
      vi.spyOn(client.api, "stackAnnotations").mockResolvedValue({
        width: 1920, height: 1080, objects: [], north_up_deg: null,
        scale_bar: { moon_comparison: "the whole frame is about 5.4 full Moons wide" },
        preview_scale_bar: {
          moon_comparison: "the whole frame is about 3.8 full Moons wide",
        },
      } as never);
      vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({
        preview_crop: { x0: 0.1, y0: 0.1, x1: 0.8, y1: 0.8 },
      } as never);
      const share = vi.fn(async (_d?: ShareData) => {});
      const restore = stubShare(share);

      renderWall();
      fireEvent.click(await screen.findByRole("img"));
      await waitFor(() => expect(client.api.stackRunInfo).toHaveBeenCalled());
      await waitFor(() => expect(client.api.stackAnnotations).toHaveBeenCalled());
      fireEvent.click(await screen.findByLabelText("Share picture"));
      await waitFor(() => expect(share).toHaveBeenCalledTimes(1));

      const text = (share.mock.calls[0][0] as ShareData).text ?? "";
      // The trimmed preview's own bar, never the wider canvas's.
      expect(text).toContain("The whole frame is about 3.8 full Moons wide.");
      expect(text).not.toContain("5.4");
      restore();
    });

  it("captions under the wall's own name against a backend that names no object",
    async () => {
      // An older backend sends neither field, and a target the catalog doesn't
      // know sends both empty — both read as "no identity", which is what this
      // viewer had for every picture before.
      mockGallery();
      vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({
        items: [pic({
          target_name: "My backyard field", n_frames_used: 12,
          total_exposure_s: 300,
        })],
      });
      const info = vi.spyOn(client.api, "stackRunInfo").mockResolvedValue({} as never);
      const share = vi.fn(async (_d?: ShareData) => {});
      const restore = stubShare(share);

      const text = await openAndShare(share);

      expect(text).toContain("My backyard field — a stack of 12 subs (5 min total)");
      expect(text).not.toContain("undefined");
      // A preview-only run has no FITS behind it, so neither read is made.
      expect(info).not.toHaveBeenCalled();
      restore();
    });
});
