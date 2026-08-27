import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ShowAndTellView } from "./ShowAndTell";
import * as client from "../api/client";
import type { BestPicture, VideoStill } from "../api/client";
import { SLIDE_MS } from "../showAndTell";

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

function mockLibrary(items: BestPicture[], videos: VideoStill[] = []) {
  vi.spyOn(client.api, "getGalleryBest").mockResolvedValue({ items });
  vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [], videos });
}

function renderShow() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><ShowAndTellView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("ShowAndTellView", () => {
  it("shows the first picture with its name, fact and acquisition line", async () => {
    mockLibrary([
      pic({ target_name: "M31", blurb: "The nearest big galaxy to our own." }),
      pic({ safe: "m42", target_name: "M42", run_id: 2 }),
    ]);
    renderShow();
    await waitFor(() => expect(screen.getByText("M31")).toBeInTheDocument());
    expect(screen.getByText("The nearest big galaxy to our own.")).toBeInTheDocument();
    expect(screen.getByText(/3\.4 h · 500 frames/)).toBeInTheDocument();
    expect(screen.getByText(/1 of 2/)).toBeInTheDocument();
    // The picture itself is on screen, labelled for a screen reader.
    expect(screen.getByAltText("M31")).toHaveAttribute(
      "src", "/api/targets/m31/stack-runs/1/preview");
  });

  it("advances on its own, and loops back round", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockLibrary([
      pic({ target_name: "M31" }),
      pic({ safe: "m42", target_name: "M42", run_id: 2 }),
    ]);
    renderShow();
    await waitFor(() => expect(screen.getByText("M31")).toBeInTheDocument());
    await act(async () => { await vi.advanceTimersByTimeAsync(SLIDE_MS + 50); });
    await waitFor(() => expect(screen.getByText("M42")).toBeInTheDocument());
    await act(async () => { await vi.advanceTimersByTimeAsync(SLIDE_MS + 50); });
    await waitFor(() => expect(screen.getByText("M31")).toBeInTheDocument());
  });

  it("stops advancing when paused, and carries on when played again", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockLibrary([
      pic({ target_name: "M31" }),
      pic({ safe: "m42", target_name: "M42", run_id: 2 }),
    ]);
    renderShow();
    await waitFor(() => expect(screen.getByText("M31")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Pause slideshow" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(SLIDE_MS * 3); });
    expect(screen.getByText("M31")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Play slideshow" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(SLIDE_MS + 50); });
    await waitFor(() => expect(screen.getByText("M42")).toBeInTheDocument());
  });

  it("steps by hand, forwards and back", async () => {
    mockLibrary([
      pic({ target_name: "M31" }),
      pic({ safe: "m42", target_name: "M42", run_id: 2 }),
    ]);
    renderShow();
    await waitFor(() => expect(screen.getByText("M31")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Next picture" }));
    await waitFor(() => expect(screen.getByText("M42")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Previous picture" }));
    await waitFor(() => expect(screen.getByText("M31")).toBeInTheDocument());
  });

  it("plays the Moon and Sun stills too, captioned in the app's own words", async () => {
    mockLibrary([], [still({ kind: "lunar", label: "Moon" })]);
    renderShow();
    // The best-pictures wall self-hides below two targets, so a brand-new
    // install's only picture is often a Moon still — it must still play.
    await waitFor(() => expect(screen.getByText("Moon")).toBeInTheDocument());
    expect(screen.getByText(/Moon —/)).toBeInTheDocument();
  });

  it("rests on a single picture instead of flickering against itself", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mockLibrary([], [still({ label: "Moon" })]);
    renderShow();
    await waitFor(() => expect(screen.getByText("Moon")).toBeInTheDocument());
    await act(async () => { await vi.advanceTimersByTimeAsync(SLIDE_MS * 3); });
    expect(screen.getByText("Moon")).toBeInTheDocument();
    // With nowhere to go, the transport is offered but inert.
    expect(screen.getByRole("button", { name: "Next picture" })).toBeDisabled();
  });

  it("says something friendly when there is nothing to show yet", async () => {
    mockLibrary([], []);
    renderShow();
    await waitFor(() =>
      expect(screen.getByText(/Nothing to show yet/i)).toBeInTheDocument());
    expect(screen.queryByTestId("show-and-tell")).not.toBeInTheDocument();
  });
});
