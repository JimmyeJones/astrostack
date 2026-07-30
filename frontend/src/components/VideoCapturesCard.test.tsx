import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VideoCapturesCard, describeCaptures } from "./VideoCapturesCard";
import * as client from "../api/client";
import type { VideoCapture, VideoList, VideoResult } from "../api/client";

function result(): VideoResult {
  return {
    created_utc: "2026-07-30T21:00:00+00:00", source_name: "clip.mp4",
    width: 1920, height: 1080, keep_percent: 30,
    n_graded: 100, n_kept: 30, n_stacked: 30, n_align_failed: 0, stride: 1,
    warnings: [], preview_url: "/p.png", tiff_url: "/t.tiff",
  };
}

function capture(over: Partial<VideoCapture> = {}): VideoCapture {
  return {
    id: "Lunar_video", label: "Moon", kind: "lunar", folder_name: "Lunar_video",
    files: [{ name: "clip.mp4", size_bytes: 1024 }], total_bytes: 1024,
    result: null, ...over,
  };
}

function list(captures: VideoCapture[]): VideoList {
  return { available: true, hint: null, incoming_dir: "/data/incoming", captures };
}

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><VideoCapturesCard /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("describeCaptures", () => {
  it("invites the user to stack a lone waiting video", () => {
    expect(describeCaptures([capture()]))
      .toBe("You have a Moon video waiting — we can turn it into one sharp picture.");
  });

  it("names the object when there is only one", () => {
    expect(describeCaptures([capture({ label: "Sun", kind: "solar" })]))
      .toContain("a Sun video waiting");
  });

  it("counts how many of several are still unstacked", () => {
    expect(describeCaptures([
      capture({ id: "a" }),
      capture({ id: "b", result: result() }),
      capture({ id: "c" }),
    ])).toBe(
      "2 of your 3 Moon and Sun videos haven't been stacked yet "
      + "— we can turn each into one sharp picture.",
    );
  });

  it("says so when everything is already stacked", () => {
    expect(describeCaptures([capture({ result: result() })]))
      .toBe("Your Moon video is stacked and ready to look at.");
    expect(describeCaptures([
      capture({ id: "a", result: result() }), capture({ id: "b", result: result() }),
    ])).toBe("All 2 of your Moon and Sun videos are stacked.");
  });
});

describe("VideoCapturesCard", () => {
  it("renders nothing for a deep-sky-only user", async () => {
    const spy = vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list([]));
    renderCard();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByText("Moon & Sun videos")).not.toBeInTheDocument();
  });

  it("nudges toward the Moon & Sun page when a capture is waiting", async () => {
    vi.spyOn(client.api, "listVideoCaptures").mockResolvedValue(list([capture()]));
    renderCard();
    await waitFor(() => expect(screen.getByText("Moon & Sun videos")).toBeInTheDocument());
    expect(screen.getByText("1 to stack")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Stack a video/i }))
      .toHaveAttribute("href", "/moon-sun");
  });

  it("drops the to-do badge once everything is stacked", async () => {
    vi.spyOn(client.api, "listVideoCaptures")
      .mockResolvedValue(list([capture({ result: result() })]));
    renderCard();
    await waitFor(() =>
      expect(screen.getByRole("link", { name: /Open Moon & Sun/i })).toBeInTheDocument());
    expect(screen.queryByText(/to stack/)).not.toBeInTheDocument();
  });

  it("stays silent when the endpoint fails", async () => {
    const spy = vi.spyOn(client.api, "listVideoCaptures")
      .mockRejectedValue(new Error("500: boom"));
    renderCard();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByText("Moon & Sun videos")).not.toBeInTheDocument();
  });
});
