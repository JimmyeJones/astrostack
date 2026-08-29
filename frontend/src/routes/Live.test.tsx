import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LiveView } from "./Live";
import type { LiveSession, Target } from "../api/client";
import * as client from "../api/client";

function target(over: Partial<Target> = {}): Target {
  return {
    safe_name: "M_42", name: "M 42", ra_deg: 83.8, dec_deg: -5.4,
    n_frames: 143, n_frames_accepted: 118, total_exposure_s: 8580,
    last_activity_utc: "2026-07-08T23:29:00+00:00",
    has_preview: true, notes: null, tags: [],
    ...over,
  };
}

function live(over: Partial<LiveSession> = {}): LiveSession {
  return {
    active: true,
    n_frames: 143, n_kept: 118, n_set_aside: 25,
    kept_exposure_s: 7080, session_exposure_s: 8580, total_kept_exposure_s: 7080,
    start_utc: "2026-07-08T21:00:00+00:00",
    latest_utc: "2026-07-08T23:29:00+00:00",
    minutes_since_latest: 1,
    conditions: {
      verdict: "good", n_recent: 20, n_recent_kept: 19,
      median_fwhm_px: 3.1, recent_buckets: {},
    },
    reject_buckets: {},
    newest_kept_frame_id: 4242,
    goal_exposure_s: null,
    ...over,
  };
}

function renderLive(at = "/live") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[at]}><LiveView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("LiveView", () => {
  it("opens on the target whose frames arrived most recently — no navigating", () => {
    // The whole point of the page: someone standing outside in the dark opens
    // one link and sees the night that's actually filling up.
    vi.spyOn(client.api, "listTargets").mockResolvedValue([
      target({ safe_name: "OLD", name: "NGC 7000",
               last_activity_utc: "2026-01-01T00:00:00+00:00" }),
      target(),
    ]);
    const spy = vi.spyOn(client.api, "liveSession").mockResolvedValue(live());
    renderLive();
    return waitFor(() => expect(spy).toHaveBeenCalledWith("M_42"));
  });

  it("honours ?target= so the view is bookmarkable for one target", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([
      target({ safe_name: "OLD", name: "NGC 7000",
               last_activity_utc: "2026-01-01T00:00:00+00:00" }),
      target(),
    ]);
    const spy = vi.spyOn(client.api, "liveSession").mockResolvedValue(live());
    renderLive("/live?target=OLD");
    await waitFor(() => expect(spy).toHaveBeenCalledWith("OLD"));
    expect(spy).not.toHaveBeenCalledWith("M_42");
  });

  it("answers both of the night's questions in one screen", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([target()]);
    vi.spyOn(client.api, "liveSession").mockResolvedValue(live({
      total_kept_exposure_s: 4 * 3600, goal_exposure_s: 6 * 3600,
    }));
    renderLive();
    // "Is it working?"
    await waitFor(() =>
      expect(screen.getByText("143 subs so far · 118 kept · 2.0 h")).toBeInTheDocument());
    expect(screen.getByText(/Going well — 19 of your last 20 subs were kept/))
      .toBeInTheDocument();
    expect(screen.getByText("Capturing")).toBeInTheDocument();
    // "Have I got enough to go inside?"
    expect(screen.getByText(/4.0 h of your 6.0 h goal — about 2.0 h to go/))
      .toBeInTheDocument();
  });

  it("shows the newest sub the app KEPT, not one it just set aside", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([target()]);
    vi.spyOn(client.api, "liveSession").mockResolvedValue(live());
    renderLive();
    const img = await screen.findByAltText("The most recent accepted sub");
    expect(img).toHaveAttribute(
      "src", "/api/targets/M_42/frames/4242/preview?size=640");
  });

  it("says a finished session is finished rather than pretending", async () => {
    // Nobody should stand outside watching a page that stopped updating hours ago.
    vi.spyOn(client.api, "listTargets").mockResolvedValue([target()]);
    vi.spyOn(client.api, "liveSession").mockResolvedValue(live({
      active: false, minutes_since_latest: 400,
    }));
    renderLive();
    await waitFor(() => expect(screen.getByText("Finished")).toBeInTheDocument());
    expect(screen.getByText(/this session looks finished/)).toBeInTheDocument();
  });

  it("names the cause when a stretch goes wrong", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([target()]);
    vi.spyOn(client.api, "liveSession").mockResolvedValue(live({
      conditions: { verdict: "poor", n_recent: 20, n_recent_kept: 4,
                    median_fwhm_px: null, recent_buckets: { cloudy: 16 } },
    }));
    renderLive();
    await waitFor(() =>
      expect(screen.getByText(/only 4 of your last 20 subs were kept/))
        .toBeInTheDocument());
    expect(screen.getByText("Mostly cloud.")).toBeInTheDocument();
  });

  it("shows an honest empty state for a library with nothing captured", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([]);
    const spy = vi.spyOn(client.api, "liveSession").mockResolvedValue(null);
    renderLive();
    await waitFor(() =>
      expect(screen.getByText("Nothing captured yet")).toBeInTheDocument());
    // …and it never asks the backend about a target it doesn't have.
    expect(spy).not.toHaveBeenCalled();
  });

  it("explains a target with no datable session instead of showing a blank", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([target()]);
    vi.spyOn(client.api, "liveSession").mockResolvedValue(null);
    renderLive();
    await waitFor(() =>
      expect(screen.getByText("No session to show yet")).toBeInTheDocument());
    expect(screen.getByText(/M 42 has no subs with a capture time yet/))
      .toBeInTheDocument();
  });

  it("offers no picker when there is only one target to watch", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([target()]);
    vi.spyOn(client.api, "liveSession").mockResolvedValue(live());
    renderLive();
    await waitFor(() => expect(screen.getByText("Capturing")).toBeInTheDocument());
    expect(screen.queryByLabelText("Watching")).not.toBeInTheDocument();
  });
});
