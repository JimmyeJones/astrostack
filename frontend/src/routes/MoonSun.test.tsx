import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_KEEP, DEFAULT_SHARPEN, MoonSunView, cropNote, cropSuggestion,
  resultSummary, sharpenNote, subjectNoun,
} from "./MoonSun";
import * as client from "../api/client";
import type { VideoCapture, VideoList, VideoResult } from "../api/client";

function result(over: Partial<VideoResult> = {}): VideoResult {
  return {
    created_utc: "2026-07-30T21:00:00+00:00",
    source_name: "clip.mp4",
    width: 1920, height: 1080,
    keep_percent: 30,
    n_graded: 100, n_kept: 30, n_stacked: 30, n_align_failed: 0, stride: 1,
    warnings: [],
    preview_url: "/api/videos/Lunar_video/preview.png",
    tiff_url: "/api/videos/Lunar_video/download.tiff",
    ...over,
  };
}

function capture(over: Partial<VideoCapture> = {}): VideoCapture {
  return {
    id: "Lunar_video", label: "Moon", kind: "lunar", folder_name: "Lunar_video",
    files: [{ name: "clip.mp4", size_bytes: 50 * 1024 ** 2 }],
    total_bytes: 50 * 1024 ** 2,
    result: null,
    ...over,
  };
}

function list(over: Partial<VideoList> = {}): VideoList {
  return {
    available: true, hint: null, incoming_dir: "/data/incoming", captures: [], ...over,
  };
}

function renderView() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><MoonSunView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("resultSummary", () => {
  it("says how many frames were kept and how much cleaner that is", () => {
    const text = resultSummary({ n_stacked: 25, n_graded: 100, width: 1920, height: 1080 });
    expect(text).toContain("sharpest 25 of 100 frames");
    expect(text).toContain("5.0× cleaner");
    expect(text).toContain("1920×1080");
  });

  it("never claims a single frame is cleaner than itself", () => {
    expect(resultSummary({ n_stacked: 1, n_graded: 3, width: 8, height: 8 }))
      .toContain("1.0× cleaner");
  });
});

describe("MoonSunView", () => {
  it("explains where to put a video when there are none", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list());
    renderView();
    await waitFor(() =>
      expect(screen.getByText("No Moon or Sun videos yet")).toBeInTheDocument());
    expect(screen.getByText("/data/incoming")).toBeInTheDocument();
  });

  it("lists a lunar capture with a Stack video button", async () => {
    vi.spyOn(client.api, "listVideoCaptures")
      .mockResolvedValue(list({ captures: [capture()] }));
    renderView();
    await waitFor(() => expect(screen.getByText("Moon")).toBeInTheDocument());
    expect(screen.getByText(/Lunar_video · 1 video · 50 MB/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Stack video/i })).toBeInTheDocument();
  });

  it("stacks with the recommended keep-% by default", async () => {
    vi.spyOn(client.api, "listVideoCaptures")
      .mockResolvedValue(list({ captures: [capture()] }));
    const post = vi.spyOn(client.api, "stackVideoCapture")
      .mockResolvedValue({ job_id: "j1" });
    renderView();
    await waitFor(() => screen.getByRole("button", { name: /Stack video/i }));
    fireEvent.click(screen.getByRole("button", { name: /Stack video/i }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("Lunar_video", {
      keep_percent: Number(DEFAULT_KEEP), file_name: "clip.mp4", crop: false,
      sharpen: Number(DEFAULT_SHARPEN),
    }));
  });

  it("shows a finished still with its summary and both downloads", async () => {
    vi.spyOn(client.api, "listVideoCaptures")
      .mockResolvedValue(list({ captures: [capture({ result: result() })] }));
    renderView();
    await waitFor(() => expect(screen.getByText("Stacked")).toBeInTheDocument());
    expect(screen.getByText(/sharpest 30 of 100 frames/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^PNG$/ }))
      .toHaveAttribute("href", "/api/videos/Lunar_video/preview.png");
    expect(screen.getByRole("link", { name: /16-bit TIFF/ }))
      .toHaveAttribute("href", "/api/videos/Lunar_video/download.tiff");
    // The button re-offers the action rather than disappearing.
    expect(screen.getByRole("button", { name: /Stack again/i })).toBeInTheDocument();
  });

  it("offers the finished picture to the user's phone", async () => {
    // Fail-before: showing someone is the first thing a beginner does with a
    // Moon picture, and this page — the one that owns it — had no way to get it
    // off the laptop but a file download.
    vi.spyOn(client.api, "listVideoCaptures")
      .mockResolvedValue(list({ captures: [capture({ result: result() })] }));
    renderView();
    await waitFor(() => expect(screen.getByText("Stacked")).toBeInTheDocument());

    fireEvent.click(
      screen.getByRole("button", { name: "Scan to get this picture on your phone" }),
    );
    await waitFor(() => expect(screen.getByRole("img", { name: /QR code/i }))
      .toBeInTheDocument());
    // Named in the user's words for *this* capture, not "the picture".
    expect(screen.getByText(/open your Moon picture and save it/)).toBeInTheDocument();
  });

  it("surfaces the engine's honest notes about a run", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture({
        result: result({ warnings: ["3 of the sharpest frames moved too far to line up and were left out."] }),
      })],
    }));
    renderView();
    await waitFor(() =>
      expect(screen.getByText(/moved too far to line up/)).toBeInTheDocument());
  });

  it("explains itself and disables stacking when ffmpeg is missing", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      available: false, hint: "Video stacking needs ffmpeg…", captures: [capture()],
    }));
    renderView();
    await waitFor(() => expect(screen.getByText("Not available yet")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Stack video/i })).toBeDisabled();
  });

  it("offers a file picker only when the folder holds more than one recording", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture({
        files: [
          { name: "a.mp4", size_bytes: 1024 ** 2 },
          { name: "b.mp4", size_bytes: 2 * 1024 ** 2 },
        ],
      })],
    }));
    renderView();
    await waitFor(() => expect(screen.getByText("Which recording?")).toBeInTheDocument());
  });

  it("retries on an API error instead of spinning forever", async () => {
    const spy = vi.spyOn(client.api, "listVideoCaptures")
      .mockRejectedValue(new Error("500: boom"));
    renderView();
    await waitFor(() => expect(screen.getByRole("button", { name: /Retry/i })).toBeInTheDocument());
    spy.mockResolvedValue(list());
    fireEvent.click(screen.getByRole("button", { name: /Retry/i }));
    await waitFor(() =>
      expect(screen.getByText("No Moon or Sun videos yet")).toBeInTheDocument());
  });
  it("shows the capture's sharpness profile and applies its suggestion", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture({
        result: result({
          keep_percent: 15,
          sharpness: {
            curve: [1, 0.99, 0.98, 0.98],
            cut_fraction: 0.15,
            options: [
              { percent: 15, n_frames: 15, sharpness_vs_typical: 1.02, noise_gain: 3.9 },
              { percent: 30, n_frames: 30, sharpness_vs_typical: 1.01, noise_gain: 5.5 },
              { percent: 50, n_frames: 50, sharpness_vs_typical: 1.0, noise_gain: 7.1 },
            ],
            suggested_percent: 50,
            spread: "steady",
            summary: "The air was steady …, so you can afford to keep more: …",
          },
        }),
      })],
    }));
    renderView();
    await waitFor(() =>
      expect(screen.getByText("How steady was your capture?")).toBeInTheDocument());
    expect(screen.getByText("Steady air")).toBeInTheDocument();
    // Acting on the advice pre-selects the matching preset on the same card, so
    // "Stack again" re-runs at the suggested setting.
    fireEvent.click(screen.getByRole("button", { name: /Try 50% instead/ }));
    await waitFor(() =>
      expect(screen.getByDisplayValue(/Half of them \(50%\)/)).toBeInTheDocument());
  });

  it("leaves the panel out for a still stacked before scores were kept", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture({ result: result() })],
    }));
    renderView();
    await waitFor(() => expect(screen.getByText(/Stacked the sharpest/)).toBeInTheDocument());
    expect(screen.queryByText("How steady was your capture?")).toBeNull();
  });

  it("offers a grade-only check before any stack exists, and shows its panel", async () => {
    const grade = vi.spyOn(client.api, "gradeVideoCapture")
      .mockResolvedValue({ job_id: "j1" });
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture()],
    }));
    renderView();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Check this capture first/ }))
        .toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Check this capture first/ }));
    await waitFor(() => expect(grade).toHaveBeenCalledWith("Lunar_video", {
      file_name: "clip.mp4",
    }));
  });

  it("replaces the check button with its panel once the capture is graded", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture({
        sharpness: {
          curve: [1, 0.5, 0.3],
          cut_fraction: 0,
          options: [
            { percent: 15, n_frames: 15, sharpness_vs_typical: 1.8, noise_gain: 3.9 },
            { percent: 30, n_frames: 30, sharpness_vs_typical: 1.4, noise_gain: 5.5 },
            { percent: 50, n_frames: 50, sharpness_vs_typical: 1.1, noise_gain: 7.1 },
          ],
          suggested_percent: 15,
          spread: "variable",
          summary: "The seeing jumped around a lot, so being pickier pays: …",
        },
      })],
    }));
    renderView();
    await waitFor(() =>
      expect(screen.getByText("How steady was your capture?")).toBeInTheDocument());
    // Already answered — no reason to offer the check again.
    expect(screen.queryByRole("button", { name: /Check this capture first/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Try 15% instead/ }));
    await waitFor(() =>
      expect(screen.getByDisplayValue(/Only the very best \(15%\)/)).toBeInTheDocument());
  });

  it("shows the sharpest single frame of a checked capture, with its caveat", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture({
        quicklook: {
          url: "/api/videos/Lunar_video/quicklook.png",
          frame_number: 412,
          n_graded: 900,
          note: "This is the sharpest single frame of your capture (frame 412 of "
            + "the 900 we checked). It's one frame, so it's noisy — stacking the "
            + "sharpest 30% (270 frames) keeps detail like this and comes out "
            + "about 16× cleaner.",
        },
      })],
    }));
    renderView();
    await waitFor(() => expect(screen.getByText("Quick look")).toBeInTheDocument());
    const img = screen.getByAltText("The sharpest single frame of your Moon capture");
    expect(img).toHaveAttribute("src", "/api/videos/Lunar_video/quicklook.png");
    // The caveat is the whole reason a noisy single frame is safe to show.
    expect(screen.getByText(/It's one frame, so it's noisy/)).toBeInTheDocument();
  });

  it("offers the OS share sheet beside the picture downloads", async () => {
    // Fail-before: the row had PNG / TIFF / "To phone" and no Share. On a
    // phone the QR is redundant with the OS's own sheet, so this is the
    // control that actually gets a Moon picture to a friend.
    const nav = navigator as unknown as Record<string, unknown>;
    nav.canShare = () => true;
    const shared: ShareData[] = [];
    nav.share = async (d: ShareData) => { shared.push(d); };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(new Blob(["x"], { type: "image/png" })),
    );
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture({ result: result() })],
    }));
    renderView();

    fireEvent.click(await screen.findByRole("button", { name: /Share/ }));
    await waitFor(() => expect(shared).toHaveLength(1));
    expect((shared[0].files as File[])[0].name).toBe("moon.png");
    delete nav.canShare;
    delete nav.share;
  });

  it("shows no quick look for a capture that was never checked", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture()],
    }));
    renderView();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Stack video/ })).toBeInTheDocument());
    expect(screen.queryByText("Quick look")).toBeNull();
  });

  it("drops the quick look once the finished picture is there to show", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture({
        result: result(),
        quicklook: {
          url: "/api/videos/Lunar_video/quicklook.png",
          frame_number: 4, n_graded: 10, note: "…",
        },
      })],
    }));
    renderView();
    await waitFor(() => expect(screen.getByText(/Stacked the sharpest/)).toBeInTheDocument());
    // The stack is the picture — a single noisy frame beside it would only
    // muddle which one is the result.
    expect(screen.queryByText("Quick look")).toBeNull();
  });
});

describe("cropping the empty sky", () => {
  it("names the subject the way the user would", () => {
    expect(subjectNoun("lunar")).toBe("Moon");
    expect(subjectNoun("solar")).toBe("Sun");
    expect(subjectNoun("other")).toBe("subject");
  });

  it("quantifies the empty sky and says what to do about it", () => {
    const text = cropSuggestion(
      { crop_available: true, crop_trim_fraction: 0.78 }, "lunar",
    );
    expect(text).toContain("78%");
    expect(text).toContain("Moon");
    // ...and no longer threatens a re-stack: trimming is a slice of the picture.
    expect(text).not.toMatch(/stack again/i);
  });

  it("stays quiet when there is nothing worth trimming", () => {
    expect(cropSuggestion({ crop_available: false, crop_trim_fraction: 0.9 }, "lunar"))
      .toBeNull();
    // An older backend sends neither field — never nag on a guess.
    expect(cropSuggestion({}, "lunar")).toBeNull();
    expect(cropSuggestion(null, "lunar")).toBeNull();
    // ...nor round a sliver up into an offer.
    expect(cropSuggestion({ crop_available: true, crop_trim_fraction: 0.001 }, "lunar"))
      .toBeNull();
  });

  it("says what a cropped still gave up, and what it came from", () => {
    const text = cropNote({
      crop_applied: true, crop_trim_fraction: 0.62,
      source_width: 1920, source_height: 1080,
    }, "solar");
    expect(text).toContain("Cropped to the Sun");
    expect(text).toContain("62%");
    expect(text).toContain("1920×1080");
    expect(cropNote({ crop_applied: false }, "solar")).toBeNull();
  });

  it("crops a finished still in place — no second stack of the capture", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture({
        result: result({ crop_available: true, crop_trim_fraction: 0.8 }),
      })],
    }));
    const crop = vi.spyOn(client.api, "cropVideoStill").mockResolvedValue(
      result({ width: 620, height: 620, crop_applied: true, crop_trim_fraction: 0.8 }),
    );
    const stack = vi.spyOn(client.api, "stackVideoCapture")
      .mockResolvedValue({ job_id: "j1" });
    renderView();
    await waitFor(() =>
      expect(screen.getByText(/80% of this picture is empty sky/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /^Crop it$/i }));
    await waitFor(() => expect(crop).toHaveBeenCalledWith("Lunar_video"));
    // The whole point: the capture is never decoded again.
    expect(stack).not.toHaveBeenCalled();
  });

  it("offers to crop even when ffmpeg is missing — it only touches the picture",
    async () => {
      vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
        available: false,
        hint: "no ffmpeg here",
        captures: [capture({
          result: result({ crop_available: true, crop_trim_fraction: 0.8 }),
        })],
      }));
      const crop = vi.spyOn(client.api, "cropVideoStill").mockResolvedValue(result());
      renderView();
      await waitFor(() => screen.getByRole("button", { name: /^Crop it$/i }));
      fireEvent.click(screen.getByRole("button", { name: /^Crop it$/i }));
      await waitFor(() => expect(crop).toHaveBeenCalledWith("Lunar_video"));
    });

  it("lets a crop be undone while the full frame is still saved", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture({
        result: result({
          width: 620, height: 620,
          crop_applied: true, crop_available: false, crop_trim_fraction: 0.8,
          crop_restorable: true, source_width: 1920, source_height: 1080,
        }),
      })],
    }));
    const undo = vi.spyOn(client.api, "restoreVideoStill").mockResolvedValue(result());
    renderView();
    await waitFor(() => screen.getByRole("button", { name: /Undo crop/i }));
    fireEvent.click(screen.getByRole("button", { name: /Undo crop/i }));
    await waitFor(() => expect(undo).toHaveBeenCalledWith("Lunar_video"));
  });

  it("doesn't offer an undo when the full frame isn't saved", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture({
        result: result({
          width: 620, height: 620, crop_applied: true, crop_trim_fraction: 0.8,
          source_width: 1920, source_height: 1080,
        }),
      })],
    }));
    renderView();
    await waitFor(() => screen.getByText(/Cropped to the Moon/));
    expect(screen.queryByRole("button", { name: /Undo crop/i })).toBeNull();
  });

  it("sends the crop when the checkbox is ticked before stacking", async () => {
    vi.spyOn(client.api, "listVideoCaptures")
      .mockResolvedValue(list({ captures: [capture()] }));
    const post = vi.spyOn(client.api, "stackVideoCapture")
      .mockResolvedValue({ job_id: "j1" });
    renderView();
    await waitFor(() => screen.getByRole("checkbox", { name: /Crop to the Moon/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /Crop to the Moon/i }));
    fireEvent.click(screen.getByRole("button", { name: /Stack video/i }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("Lunar_video", {
      keep_percent: Number(DEFAULT_KEEP), file_name: "clip.mp4", crop: true,
      sharpen: Number(DEFAULT_SHARPEN),
    }));
  });

  it("reports a cropped still instead of offering to crop it again", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture({
        result: result({
          width: 620, height: 620,
          crop_applied: true, crop_available: false, crop_trim_fraction: 0.8,
          source_width: 1920, source_height: 1080,
        }),
      })],
    }));
    renderView();
    await waitFor(() =>
      expect(screen.getByText(/Cropped to the Moon/)).toBeInTheDocument());
    expect(screen.queryByText(/empty sky around the Moon/)).toBeNull();
    expect(screen.queryByRole("button", { name: /^Crop it$/i })).toBeNull();
  });

  it("says nothing about framing for a still from an older backend", async () => {
    vi.spyOn(client.api, "listVideoCaptures")
      .mockResolvedValue(list({ captures: [capture({ result: result() })] }));
    renderView();
    await waitFor(() => expect(screen.getByText(/Stacked the sharpest/)).toBeInTheDocument());
    // The checkbox is still offered (it costs nothing); what must not appear is
    // a claim about *this* picture's framing, which the backend never measured.
    expect(screen.queryByText(/of this picture is empty sky/)).toBeNull();
    expect(screen.queryByText(/Cropped to the/)).toBeNull();
    expect(screen.queryByRole("button", { name: /Crop it and stack again/i })).toBeNull();
  });

  it("labels the checkbox for the Sun on a solar capture", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture({ id: "Solar_video", label: "Sun", kind: "solar" })],
    }));
    renderView();
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: /Crop to the Sun/i })).toBeInTheDocument());
  });
});

// --- a still whose source video is gone ------------------------------------
//
// The backend keeps listing a finished still after its clip leaves `incoming/`
// (the case the in-place crop exists for), sending it with an empty `files`
// list. The card must then read as "here is your picture" rather than offering
// a stack that can only fail.

describe("MoonSunView with a still whose video is gone", () => {
  const orphan = () => capture({
    files: [], total_bytes: 0, result: result({ crop_available: true, crop_trim_fraction: 0.8 }),
  });

  it("keeps the picture and its crop, and hides the stacking controls", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(
      list({ captures: [orphan()] }));

    renderView();

    // The picture and everything that acts on it survive...
    expect(await screen.findByText("Moon")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Crop it/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "PNG" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /16-bit TIFF/ })).toBeInTheDocument();
    // ...and it says plainly why there's nothing to stack.
    expect(screen.getByText(/isn't in your incoming folder any more/)).toBeInTheDocument();
    expect(screen.getByText(/video no longer in your incoming folder/)).toBeInTheDocument();
    // Fail-before: "Stack again" was offered on a capture with no video to read.
    expect(screen.queryByRole("button", { name: /Stack again/ })).not.toBeInTheDocument();
    expect(screen.queryByText("How picky should we be?")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Check this capture/ }))
      .not.toBeInTheDocument();
  });

  it("still offers to stack a capture whose video is present", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(
      list({ captures: [capture({ result: result() })] }));

    renderView();

    expect(await screen.findByRole("button", { name: /Stack again/ })).toBeInTheDocument();
    expect(screen.getByText("How picky should we be?")).toBeInTheDocument();
    expect(screen.queryByText(/isn't in your incoming folder any more/))
      .not.toBeInTheDocument();
  });
});

describe("sharpening a Moon or Sun picture", () => {
  it("says nothing about sharpening for a picture that wasn't sharpened", () => {
    expect(sharpenNote(0)).toBeNull();
    expect(sharpenNote(undefined)).toBeNull();
    expect(sharpenNote(null)).toBeNull();
    expect(sharpenNote(Number.NaN)).toBeNull();
  });

  it("names the strength in words rather than printing a number", () => {
    expect(sharpenNote(0.6)).toContain("Gentle");
    expect(sharpenNote(1.2)).toContain("Medium");
    expect(sharpenNote(2)).toContain("Strong");
    // A value that didn't come from the menu still reads as the nearest one.
    expect(sharpenNote(0.55)).toContain("Gentle");
    expect(sharpenNote(0.6)).not.toMatch(/0\.6/);
  });

  it("offers sharpening, off by default, so an existing install is unchanged",
    async () => {
      vi.spyOn(client.api, "listVideoCaptures")
        .mockResolvedValue(list({ captures: [capture()] }));
      const post = vi.spyOn(client.api, "stackVideoCapture")
        .mockResolvedValue({ job_id: "j1" });
      renderView();
      await waitFor(() => screen.getByText("Sharpen the detail"));
      fireEvent.click(screen.getByRole("button", { name: /Stack video/i }));
      await waitFor(() => expect(post).toHaveBeenCalledWith(
        "Lunar_video",
        expect.objectContaining({ sharpen: 0 }),
      ));
    });

  it("sends the strength the user picked", async () => {
    vi.spyOn(client.api, "listVideoCaptures")
      .mockResolvedValue(list({ captures: [capture()] }));
    const post = vi.spyOn(client.api, "stackVideoCapture")
      .mockResolvedValue({ job_id: "j1" });
    renderView();
    await waitFor(() => screen.getByText("Sharpen the detail"));
    // The Select's own input, addressed by the value it is showing — the label
    // text also appears on the wrapper, so it can't be used to pick one element.
    fireEvent.click(screen.getByDisplayValue(/Off — the plain stacked picture/));
    fireEvent.click(await screen.findByText(/Gentle — recommended/));
    fireEvent.click(screen.getByRole("button", { name: /Stack video/i }));
    await waitFor(() => expect(post).toHaveBeenCalledWith(
      "Lunar_video",
      expect.objectContaining({ sharpen: 0.6 }),
    ));
  });

  it("says on the finished picture that it was sharpened", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture({ result: result({ sharpen_amount: 1.2 }) })],
    }));
    renderView();
    await waitFor(() => expect(screen.getByText(/Sharpening: Medium/))
      .toBeInTheDocument());
  });

  it("says nothing on a still stacked before sharpening existed", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list({
      captures: [capture({ result: result() })],
    }));
    renderView();
    await waitFor(() => screen.getByText(/Stacked the sharpest/));
    expect(screen.queryByText(/Sharpening:/)).not.toBeInTheDocument();
  });
});
