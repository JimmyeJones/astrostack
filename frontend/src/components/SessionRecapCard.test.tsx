import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionRecapCard, describeRejects, describeSession } from "./SessionRecapCard";
import type { SessionRecap } from "../api/client";
import * as client from "../api/client";

function recap(over: Partial<SessionRecap> = {}): SessionRecap {
  return {
    n_frames: 10, n_kept: 8, n_set_aside: 2,
    session_exposure_s: 100, kept_exposure_s: 80, total_kept_exposure_s: 130,
    start_utc: "2026-07-08T22:00:00", end_utc: "2026-07-08T22:05:00",
    reject_buckets: { trailed: 2 },
    ...over,
  };
}

function renderCard(safe = "M_31") {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <SessionRecapCard safe={safe} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("describeRejects", () => {
  it("lists present buckets in a friendly order", () => {
    expect(describeRejects({ trailed: 2, cloudy: 10 })).toBe("10 cloudy, 2 trailed");
    expect(describeRejects({ soft: 3 })).toBe("3 soft");
    expect(describeRejects({})).toBe("");
    // Unknown buckets sort after the known ones.
    expect(describeRejects({ other: 1, cloudy: 4 })).toBe("4 cloudy, 1 other");
  });
});

describe("describeSession", () => {
  it("phrases the kept-vs-set-aside recap with a reason breakdown", () => {
    expect(describeSession(recap())).toBe(
      "Last session added 10 subs (2 min). 8 kept; 2 set aside (2 trailed). " +
        "Total on this target: 2 min.",
    );
  });

  it("says all kept when nothing was set aside", () => {
    const r = recap({ n_frames: 3, n_kept: 3, n_set_aside: 0, reject_buckets: {},
      session_exposure_s: 30, kept_exposure_s: 30, total_kept_exposure_s: 30 });
    expect(describeSession(r)).toBe(
      "Last session added 3 subs (30 s). All 3 were kept. Total on this target: 30 s.",
    );
  });

  it("uses the singular for a one-sub session", () => {
    const r = recap({ n_frames: 1, n_kept: 1, n_set_aside: 0, reject_buckets: {} });
    expect(describeSession(r)).toContain("added 1 sub (");
  });
});

describe("SessionRecapCard", () => {
  it("renders the recap card with a kept-percentage badge", async () => {
    vi.spyOn(client.api, "sessionRecap").mockResolvedValue(recap());
    renderCard();
    await waitFor(() => expect(screen.getByText("Last session")).toBeInTheDocument());
    expect(screen.getByText("80% kept")).toBeInTheDocument();
    expect(screen.getByText(/2 set aside \(2 trailed\)/)).toBeInTheDocument();
  });

  it("renders nothing when there's nothing datable to report", async () => {
    vi.spyOn(client.api, "sessionRecap").mockResolvedValue(null);
    const { container } = renderCard();
    await waitFor(() => expect(client.api.sessionRecap).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
