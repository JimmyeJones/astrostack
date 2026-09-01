import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RestackGainNote } from "./RestackGainNote";
import * as client from "../api/client";
import type { RestackGain } from "../api/client";

function gain(over: Partial<RestackGain> = {}): RestackGain {
  return {
    run_id: 4,
    timestamp_utc: "2026-08-30T14:32:05Z",
    n_frames_used: 200,
    n_frames_ready: 512,
    missing_capture_window: true,
    missing_night_count: false,
    ...over,
  };
}

function renderNote() {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <RestackGainNote safe="m_42" />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("RestackGainNote", () => {
  it("names the gain and the cost, never a version number", async () => {
    vi.spyOn(client.api, "restackGain").mockResolvedValue(gain());
    renderNote();

    await waitFor(() =>
      expect(screen.getByTestId("restack-gain-note")).toBeInTheDocument());
    expect(screen.getByText(/before AstroStack recorded when your subs were shot/))
      .toBeInTheDocument();
    // The cost half: "stack 5,000 subs again" must never be a blind click.
    expect(screen.getByText(/re-combine 512 subs \(the picture you have was made from 200\)/))
      .toBeInTheDocument();
    // Reassurance — the picture they have is not replaced or lost.
    expect(screen.getByText(/stays in this target's history/)).toBeInTheDocument();
    // ...and no version number anywhere: "yours is old" is not an actionable reason.
    expect(screen.queryByText(/version/i)).toBeNull();
  });

  it("has a different, smaller thing to say when only the night count is missing", async () => {
    vi.spyOn(client.api, "restackGain").mockResolvedValue(gain({
      missing_capture_window: false, missing_night_count: true,
    }));
    renderNote();
    await waitFor(() =>
      expect(screen.getByTestId("restack-gain-note")).toBeInTheDocument());
    expect(screen.getByText(/but not how many nights they came from/))
      .toBeInTheDocument();
  });

  it("only ever offers — the re-stack starts on the click, never before", async () => {
    vi.spyOn(client.api, "restackGain").mockResolvedValue(gain());
    const proc = vi.spyOn(client.api, "processTarget")
      .mockResolvedValue({ job_id: "j1" });
    renderNote();
    await waitFor(() =>
      expect(screen.getByTestId("restack-gain-note")).toBeInTheDocument());
    expect(proc).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Stack it again/ }));
    await waitFor(() => expect(proc).toHaveBeenCalledWith("m_42"));
  });

  it("says nothing when the picture already records its nights", async () => {
    const spy = vi.spyOn(client.api, "restackGain").mockResolvedValue(null);
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("restack-gain-note")).toBeNull();
  });

  it("stays silent on an older backend or a failed fetch", async () => {
    const spy = vi.spyOn(client.api, "restackGain")
      .mockRejectedValue(new Error("404"));
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("restack-gain-note")).toBeNull();
  });
});
