import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FirstLookStrip, pickFirstLookTarget } from "./FirstLookStrip";
import type { BestFrame, Target } from "../../api/client";
import * as client from "../../api/client";

function target(over: Partial<Target> = {}): Target {
  return {
    safe_name: "M_42",
    name: "M 42",
    ra_deg: null,
    dec_deg: null,
    n_frames: 40,
    n_frames_accepted: 38,
    total_exposure_s: 380,
    last_activity_utc: "2026-09-05T22:00:00+00:00",
    has_preview: false,
    notes: null,
    tags: [],
    ...over,
  };
}

function best(over: Partial<BestFrame> = {}): BestFrame {
  return {
    frame_id: 7,
    captured_utc: null,
    fwhm_px: 2.1,
    star_count: 480,
    n_accepted: 38,
    ...over,
  };
}

function renderStrip() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <FirstLookStrip />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("pickFirstLookTarget", () => {
  it("picks the target with kept subs and no picture yet", () => {
    const pick = pickFirstLookTarget([
      target({ safe_name: "done", name: "Done", has_preview: true }),
      target({ safe_name: "waiting", name: "Waiting" }),
    ]);
    expect(pick?.safe_name).toBe("waiting");
  });

  it("returns null when every target already has a picture", () => {
    expect(pickFirstLookTarget([target({ has_preview: true })])).toBeNull();
  });

  it("returns null for a target with nothing kept yet", () => {
    expect(pickFirstLookTarget([target({ n_frames_accepted: 0 })])).toBeNull();
  });

  it("returns null for an empty or missing list", () => {
    expect(pickFirstLookTarget([])).toBeNull();
    expect(pickFirstLookTarget(undefined)).toBeNull();
  });

  it("prefers the most recently active target", () => {
    const pick = pickFirstLookTarget([
      target({ safe_name: "old", last_activity_utc: "2026-08-01T22:00:00+00:00" }),
      target({ safe_name: "new", last_activity_utc: "2026-09-05T22:00:00+00:00" }),
    ]);
    expect(pick?.safe_name).toBe("new");
  });

  it("keeps a target with no activity stamp, but sorts it last", () => {
    expect(pickFirstLookTarget([target({ safe_name: "undated", last_activity_utc: null })])
      ?.safe_name).toBe("undated");
    const pick = pickFirstLookTarget([
      target({ safe_name: "undated", last_activity_utc: null }),
      target({ safe_name: "dated", last_activity_utc: "2020-01-01T00:00:00+00:00" }),
    ]);
    expect(pick?.safe_name).toBe("dated");
  });

  it("ignores an unparseable activity stamp rather than ranking it newest", () => {
    const pick = pickFirstLookTarget([
      target({ safe_name: "junk", last_activity_utc: "not-a-date" }),
      target({ safe_name: "dated", last_activity_utc: "2020-01-01T00:00:00+00:00" }),
    ]);
    expect(pick?.safe_name).toBe("dated");
  });

  it("breaks a tie deterministically, and does not reorder the caller's list", () => {
    const list = [
      target({ safe_name: "b", name: "B", n_frames_accepted: 10 }),
      target({ safe_name: "a", name: "A", n_frames_accepted: 10 }),
      target({ safe_name: "deep", name: "Deep", n_frames_accepted: 99 }),
    ];
    expect(pickFirstLookTarget(list)?.safe_name).toBe("deep");
    expect(pickFirstLookTarget(list.slice(0, 2))?.safe_name).toBe("a");
    expect(list.map((t) => t.safe_name)).toEqual(["b", "a", "deep"]);
  });
});

describe("FirstLookStrip", () => {
  it("shows the waiting target's sharpest sub, named and linked", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([
      target({ safe_name: "done", name: "Done", has_preview: true }),
      target({ safe_name: "M_42", name: "M 42" }),
    ]);
    vi.spyOn(client.api, "bestFrame").mockResolvedValue(best());
    renderStrip();
    await waitFor(() => expect(screen.getByText("First look")).toBeInTheDocument());
    expect(client.api.bestFrame).toHaveBeenCalledWith("M_42");
    expect(screen.getByText("M 42 →")).toHaveAttribute("href", "/targets/M_42");
    expect(screen.getByRole("img", { name: /sharpest sub/i }))
      .toHaveAttribute("src", expect.stringContaining("/frames/7/preview"));
  });

  it("renders nothing, and asks for no frame, once every target has a picture", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([target({ has_preview: true })]);
    const bestFrame = vi.spyOn(client.api, "bestFrame").mockResolvedValue(best());
    const { container } = renderStrip();
    await waitFor(() => expect(client.api.listTargets).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
    expect(bestFrame).not.toHaveBeenCalled();
  });

  it("renders nothing when the target list can't be read", async () => {
    vi.spyOn(client.api, "listTargets").mockRejectedValue(new Error("nope"));
    const { container } = renderStrip();
    await waitFor(() => expect(client.api.listTargets).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
