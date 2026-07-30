import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_KEEP, MoonSunView, resultSummary } from "./MoonSun";
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
      keep_percent: Number(DEFAULT_KEEP), file_name: "clip.mp4",
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
});
