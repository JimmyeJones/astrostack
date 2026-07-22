import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AutoFeedback } from "./AutoFeedback";
import * as client from "../../api/client";

function wrap(onRerun = () => {}, scope?: { safe: string; runId: number }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <AutoFeedback onRerun={onRerun} safe={scope?.safe} runId={scope?.runId} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("AutoFeedback", () => {
  it("sends the matching cue and re-runs Auto when a chip is tapped", async () => {
    vi.spyOn(client.api, "getAutoPreferences")
      .mockResolvedValue({ biases: {}, note: null, neutral: true });
    const send = vi.spyOn(client.api, "sendAutoFeedback")
      .mockResolvedValue({ biases: { brightness: 1 }, note: "Auto is running a bit brighter for you, based on your recent feedback.", neutral: false });
    const onRerun = vi.fn();

    wrap(onRerun);
    fireEvent.click(await screen.findByRole("button", { name: "Too dark" }));

    // With no run context the cue updates the global taste (no ctx argument).
    await waitFor(() => expect(send).toHaveBeenCalledWith("too_dark", undefined));
    await waitFor(() => expect(onRerun).toHaveBeenCalled());
    // The "why" note surfaces once the profile is non-neutral.
    await screen.findByText(/running a bit brighter/);
  });

  it("scopes feedback to the run's archetype when given safe/runId", async () => {
    const getRun = vi.spyOn(client.api, "getRunAutoPreferences")
      .mockResolvedValue({ biases: {}, note: null, neutral: true });
    const send = vi.spyOn(client.api, "sendAutoFeedback")
      .mockResolvedValue({ biases: { brightness: 1 }, note: "Auto is running a bit brighter for your galaxies, based on your recent feedback.", neutral: false });

    wrap(() => {}, { safe: "M31", runId: 7 });
    fireEvent.click(await screen.findByRole("button", { name: "Too dark" }));

    // The run-scoped profile is queried, and the cue carries the run context.
    await waitFor(() => expect(getRun).toHaveBeenCalledWith("M31", 7));
    await waitFor(() =>
      expect(send).toHaveBeenCalledWith("too_dark", { safe: "M31", runId: 7 }));
    // The archetype-scoped "why" note surfaces.
    await screen.findByText(/for your galaxies/);
  });

  it("shows the why-note and Reset only when the profile is non-neutral", async () => {
    vi.spyOn(client.api, "getAutoPreferences")
      .mockResolvedValue({ biases: { sharpen: -1 }, note: "Auto is running softer for you, based on your recent feedback.", neutral: false });
    const reset = vi.spyOn(client.api, "resetAutoPreferences")
      .mockResolvedValue({ biases: {}, note: null, neutral: true });
    const onRerun = vi.fn();

    wrap(onRerun);
    fireEvent.click(await screen.findByText("Reset"));

    await waitFor(() => expect(reset).toHaveBeenCalled());
    await waitFor(() => expect(onRerun).toHaveBeenCalled());
  });

  it("offers no Reset link when neutral", async () => {
    vi.spyOn(client.api, "getAutoPreferences")
      .mockResolvedValue({ biases: {}, note: null, neutral: true });
    wrap();
    // Chips render, but there's no why-note/Reset for a neutral profile.
    await screen.findByRole("button", { name: "Too dark" });
    expect(screen.queryByText("Reset")).toBeNull();
  });
});
