import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GrainierNewestNote } from "./GrainierNewestNote";
import * as client from "../api/client";
import type { GrainierNewest } from "../api/client";

const NUDGE: GrainierNewest = {
  run_id: 3,
  newest_run_id: 12,
  noise_sigma: 0.008,
  newest_noise_sigma: 0.012,
  percent_grainier: 50,
  n_frames_used: 90,
  newest_n_frames_used: 22,
  timestamp_utc: "2026-05-09T02:00:00Z",
};

function renderNote() {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <GrainierNewestNote safe="m_42" />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("GrainierNewestNote", () => {
  it("names the regression in plain language, with the numbers behind it", async () => {
    vi.spyOn(client.api, "grainierNewest").mockResolvedValue(NUDGE);
    renderNote();

    await waitFor(() =>
      expect(screen.getByTestId("grainier-newest-note")).toBeInTheDocument());
    expect(screen.getByText(/about 50% more background grain/)).toBeInTheDocument();
    expect(screen.getByText(/combined 22 subs against 90/)).toBeInTheDocument();
    // Reassurance: nothing was lost, and this is an offer rather than an event.
    expect(screen.getByText(/still in this target's history/)).toBeInTheDocument();
  });

  it("blames the sky, not the sub count, when the grainy stack wasn't thinner", async () => {
    vi.spyOn(client.api, "grainierNewest")
      .mockResolvedValue({ ...NUDGE, newest_n_frames_used: 95 });
    renderNote();

    await waitFor(() =>
      expect(screen.getByTestId("grainier-newest-note")).toBeInTheDocument());
    expect(screen.getByText(/sky was probably hazier/)).toBeInTheDocument();
    expect(screen.queryByText(/subs against/)).toBeNull();
  });

  it("pins the earlier run through the same set-cover path History uses", async () => {
    vi.spyOn(client.api, "grainierNewest").mockResolvedValue(NUDGE);
    const setCover = vi.spyOn(client.api, "setTargetCover")
      .mockResolvedValue({} as never);
    renderNote();

    await waitFor(() =>
      expect(screen.getByTestId("grainier-newest-note")).toBeInTheDocument());
    fireEvent.click(
      screen.getByRole("button", { name: /Show the better one instead/ }));
    // The *earlier*, cleaner run — never the newest one.
    await waitFor(() => expect(setCover).toHaveBeenCalledWith("m_42", 3));
  });

  it("says nothing on an ordinary night, when the newest is the cleanest", async () => {
    const spy = vi.spyOn(client.api, "grainierNewest").mockResolvedValue(null);
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("grainier-newest-note")).toBeNull();
  });

  it("stays silent on an older backend or a failed fetch", async () => {
    const spy = vi.spyOn(client.api, "grainierNewest")
      .mockRejectedValue(new Error("404"));
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("grainier-newest-note")).toBeNull();
  });
});
