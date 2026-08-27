import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CleanestShotNote } from "./CleanestShotNote";
import * as client from "../api/client";
import type { CleanestShot } from "../api/client";

const SHOT: CleanestShot = {
  run_id: 12,
  cover_run_id: 3,
  noise_sigma: 0.008,
  cover_noise_sigma: 0.012,
  percent_cleaner: 33,
  n_frames_used: 90,
  cover_n_frames_used: 40,
  timestamp_utc: "2026-05-09T02:00:00Z",
};

function renderNote() {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <CleanestShotNote safe="m_42" />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("CleanestShotNote", () => {
  it("names the gap in plain language, with the numbers behind it", async () => {
    vi.spyOn(client.api, "cleanestShot").mockResolvedValue(SHOT);
    renderNote();

    await waitFor(() =>
      expect(screen.getByTestId("cleanest-shot-note")).toBeInTheDocument());
    expect(screen.getByText(/about 33% less background grain/)).toBeInTheDocument();
    expect(screen.getByText(/combined 90 subs against 40/)).toBeInTheDocument();
    // The reassurance that this is a suggestion, not something that happened.
    expect(screen.getByText(/only changes when you say so/)).toBeInTheDocument();
  });

  it("pins the offered run through the same set-cover path History uses", async () => {
    vi.spyOn(client.api, "cleanestShot").mockResolvedValue(SHOT);
    const setCover = vi.spyOn(client.api, "setTargetCover")
      .mockResolvedValue({} as never);
    renderNote();

    await waitFor(() =>
      expect(screen.getByTestId("cleanest-shot-note")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Make this the cover/ }));
    await waitFor(() => expect(setCover).toHaveBeenCalledWith("m_42", 12));
  });

  it("says nothing when there's no cleaner stack to offer", async () => {
    const spy = vi.spyOn(client.api, "cleanestShot").mockResolvedValue(null);
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("cleanest-shot-note")).toBeNull();
  });

  it("stays silent on an older backend or a failed fetch", async () => {
    const spy = vi.spyOn(client.api, "cleanestShot")
      .mockRejectedValue(new Error("404"));
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("cleanest-shot-note")).toBeNull();
  });
});
