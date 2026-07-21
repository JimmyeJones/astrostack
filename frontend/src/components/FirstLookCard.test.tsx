import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FirstLookCard, firstLookCaption, firstLookMetrics } from "./FirstLookCard";
import type { BestFrame } from "../api/client";
import * as client from "../api/client";

function best(over: Partial<BestFrame> = {}): BestFrame {
  return {
    frame_id: 42,
    captured_utc: null,
    fwhm_px: 2.1,
    star_count: 480,
    n_accepted: 240,
    ...over,
  };
}

function renderCard(safe = "M_42") {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <FirstLookCard safe={safe} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("firstLookCaption", () => {
  it("names the sharpest sub out of the accepted count", () => {
    expect(firstLookCaption(best())).toBe("Your sharpest sub of 240");
  });
  it("drops the count when there's only one accepted sub", () => {
    expect(firstLookCaption(best({ n_accepted: 1 }))).toBe("Your sharpest sub");
  });
  it("appends the capture time when present", () => {
    const cap = firstLookCaption(best({ captured_utc: "2026-07-14T21:14:00+00:00" }));
    expect(cap).toMatch(/^Your sharpest sub of 240 — captured /);
  });
  it("ignores an unparseable capture time", () => {
    expect(firstLookCaption(best({ captured_utc: "not-a-date" }))).toBe(
      "Your sharpest sub of 240",
    );
  });
});

describe("firstLookMetrics", () => {
  it("formats FWHM and star count", () => {
    expect(firstLookMetrics(best())).toBe("FWHM 2.1 px · 480 stars");
  });
  it("shows only what's measured", () => {
    expect(firstLookMetrics(best({ star_count: null }))).toBe("FWHM 2.1 px");
    expect(firstLookMetrics(best({ fwhm_px: null }))).toBe("480 stars");
  });
  it("returns null when nothing is measured", () => {
    expect(firstLookMetrics(best({ fwhm_px: null, star_count: null }))).toBeNull();
  });
});

describe("FirstLookCard", () => {
  it("renders the sharpest sub's thumbnail and caption", async () => {
    vi.spyOn(client.api, "bestFrame").mockResolvedValue(best({ frame_id: 7 }));
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("First look")).toBeInTheDocument());
    expect(screen.getByText("Your sharpest sub of 240")).toBeInTheDocument();
    expect(screen.getByText("FWHM 2.1 px · 480 stars")).toBeInTheDocument();
    const img = screen.getByRole("img", { name: /sharpest sub/i });
    expect(img).toHaveAttribute("src", expect.stringContaining("/frames/7/preview"));
  });

  it("renders nothing before anything is QC'd (no best frame)", async () => {
    vi.spyOn(client.api, "bestFrame").mockResolvedValue(
      best({ frame_id: null, fwhm_px: null, star_count: null, n_accepted: 3 }),
    );
    const { container } = renderCard();
    await waitFor(() => expect(client.api.bestFrame).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
