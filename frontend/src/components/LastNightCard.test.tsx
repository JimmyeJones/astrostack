import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LastNightCard, describeLibraryNight } from "./LastNightCard";
import type { LibrarySessionRecap, TargetNight } from "../api/client";
import * as client from "../api/client";

function tgt(over: Partial<TargetNight> = {}): TargetNight {
  return {
    name: "M 31", safe: "M_31",
    n_frames: 6, n_kept: 6, n_set_aside: 0,
    exposure_s: 60, kept_exposure_s: 60,
    ...over,
  };
}

function recap(over: Partial<LibrarySessionRecap> = {}): LibrarySessionRecap {
  return {
    n_targets: 2, n_frames: 10, n_kept: 8, n_set_aside: 2,
    session_exposure_s: 7200, kept_exposure_s: 5760,
    start_utc: "2026-07-08T21:00:00+00:00", end_utc: "2026-07-08T23:05:00+00:00",
    targets: [tgt({ n_frames: 6 }), tgt({ name: "M 42", safe: "M_42", n_frames: 4 })],
    reject_buckets: { trailed: 2 },
    ...over,
  };
}

function renderCard() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <LastNightCard />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("describeLibraryNight", () => {
  it("phrases a multi-target night with the kept-vs-set-aside breakdown", () => {
    expect(describeLibraryNight(recap())).toBe(
      "Last night you captured 10 subs across 2 targets (2.0 h). " +
        "8 kept; 2 set aside (2 trailed).",
    );
  });

  it("names the single target and says all kept when nothing was set aside", () => {
    const r = recap({
      n_targets: 1, n_frames: 6, n_kept: 6, n_set_aside: 0,
      session_exposure_s: 60, reject_buckets: {},
      targets: [tgt({ n_frames: 6 })],
    });
    expect(describeLibraryNight(r)).toBe(
      "Last night you captured 6 subs on M 31 (1 min). All 6 were kept.",
    );
  });

  it("uses the singular for a one-sub night", () => {
    const r = recap({ n_targets: 1, n_frames: 1, n_kept: 1, n_set_aside: 0,
      reject_buckets: {}, targets: [tgt({ n_frames: 1 })] });
    expect(describeLibraryNight(r)).toContain("captured 1 sub on M 31");
  });
});

describe("LastNightCard", () => {
  it("renders the combined recap with a date, kept badge and target chips", async () => {
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(recap());
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Last night · 2026-07-08")).toBeInTheDocument());
    expect(screen.getByText("80% kept")).toBeInTheDocument();
    // Per-target chips only show for a multi-target night.
    expect(screen.getByText("M 31 · 6 subs")).toBeInTheDocument();
    expect(screen.getByText("M 42 · 4 subs")).toBeInTheDocument();
  });

  it("omits the chip row for a single-target night", async () => {
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(
      recap({ n_targets: 1, n_frames: 6, n_kept: 6, n_set_aside: 0,
        session_exposure_s: 60, reject_buckets: {}, targets: [tgt({ n_frames: 6 })] }),
    );
    renderCard();
    await waitFor(() =>
      expect(screen.getByText(/captured 6 subs on M 31/)).toBeInTheDocument());
    expect(screen.queryByText("M 31 · 6 subs")).toBeNull();
  });

  it("renders nothing when there's no datable night", async () => {
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(null);
    const { container } = renderCard();
    await waitFor(() => expect(client.api.getLastNight).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
