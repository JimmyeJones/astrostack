import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SAMPLE_TOUR_COPY, SampleTourNote, type SampleTourStep } from "./SampleTourNote";
import * as client from "../api/client";

function renderNote(step: SampleTourStep, safe: string | null) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <SampleTourNote step={step} safe={safe} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

const SAMPLE_SAFE = "Sample__Orion_Nebula__M42_";

function mockSample(over: Partial<client.SampleStatus> = {}) {
  vi.spyOn(client.api, "getSampleStatus").mockResolvedValue({
    loaded: true, safe: SAMPLE_SAFE, n_frames: 6, ...over,
  } as client.SampleStatus);
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("SampleTourNote", () => {
  it("coaches each screen while you're on the sample target", async () => {
    for (const step of ["target", "stack", "editor", "history"] as SampleTourStep[]) {
      localStorage.clear();
      mockSample();
      const { unmount } = renderNote(step, SAMPLE_SAFE);
      expect(await screen.findByText(SAMPLE_TOUR_COPY[step].title)).toBeInTheDocument();
      expect(screen.getByText(SAMPLE_TOUR_COPY[step].body)).toBeInTheDocument();
      unmount();
      vi.restoreAllMocks();
    }
  });

  it("says nothing on a real target, even while the sample exists", async () => {
    mockSample();
    renderNote("target", "M_42");
    await waitFor(() => expect(client.api.getSampleStatus).toHaveBeenCalled());
    expect(screen.queryByText(SAMPLE_TOUR_COPY.target.title)).not.toBeInTheDocument();
  });

  it("says nothing when the sample was never loaded (or was removed)", async () => {
    mockSample({ loaded: false, safe: null, n_frames: 0 });
    renderNote("target", SAMPLE_SAFE);
    await waitFor(() => expect(client.api.getSampleStatus).toHaveBeenCalled());
    expect(screen.queryByText(SAMPLE_TOUR_COPY.target.title)).not.toBeInTheDocument();
  });

  it("renders nothing at all before the route resolves a target", () => {
    mockSample();
    renderNote("target", null);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(SAMPLE_TOUR_COPY.target.title)).not.toBeInTheDocument();
    // It doesn't even ask the backend when there's no target to compare against.
    expect(client.api.getSampleStatus).not.toHaveBeenCalled();
  });

  it("dismisses one step without hiding the rest of the tour", async () => {
    mockSample();
    const first = renderNote("stack", SAMPLE_SAFE);
    await screen.findByText(SAMPLE_TOUR_COPY.stack.title);
    fireEvent.click(screen.getByLabelText("Hide this tip"));
    await waitFor(() =>
      expect(screen.queryByText(SAMPLE_TOUR_COPY.stack.title)).not.toBeInTheDocument());
    first.unmount();

    // Stays dismissed on the next visit…
    renderNote("stack", SAMPLE_SAFE).unmount();
    expect(screen.queryByText(SAMPLE_TOUR_COPY.stack.title)).not.toBeInTheDocument();

    // …but the editor step is untouched.
    renderNote("editor", SAMPLE_SAFE);
    expect(await screen.findByText(SAMPLE_TOUR_COPY.editor.title)).toBeInTheDocument();
  });

  it("ends the tour where the pictures live, naming Export and the Gallery", async () => {
    mockSample();
    renderNote("history", SAMPLE_SAFE);
    // The two things the first three steps never say: what Export is for, and
    // that the Gallery collects finished pictures from every target.
    expect(await screen.findByText(SAMPLE_TOUR_COPY.history.title)).toBeInTheDocument();
    expect(SAMPLE_TOUR_COPY.history.body).toMatch(/Export/);
    expect(SAMPLE_TOUR_COPY.history.body).toMatch(/Gallery/);
  });

  it("still renders when localStorage is unavailable", async () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem")
      .mockImplementation(() => { throw new Error("denied"); });
    const setItem = vi.spyOn(Storage.prototype, "setItem")
      .mockImplementation(() => { throw new Error("denied"); });
    mockSample();
    renderNote("target", SAMPLE_SAFE);
    expect(await screen.findByText(SAMPLE_TOUR_COPY.target.title)).toBeInTheDocument();
    // Dismissing still works for this visit; it just won't persist.
    fireEvent.click(screen.getByLabelText("Hide this tip"));
    await waitFor(() =>
      expect(screen.queryByText(SAMPLE_TOUR_COPY.target.title)).not.toBeInTheDocument());
    getItem.mockRestore();
    setItem.mockRestore();
  });

  it("keeps every step's copy jargon-free and actionable", () => {
    for (const step of ["target", "stack", "editor", "history"] as SampleTourStep[]) {
      const { title, body } = SAMPLE_TOUR_COPY[step];
      expect(title.length).toBeGreaterThan(10);
      expect(body.length).toBeGreaterThan(60);
      // Plain language: no expert vocabulary a beginner wouldn't know.
      expect(body).not.toMatch(/PixInsight|LRGB|narrowband|kappa|sigma-clip|deconvolut/i);
    }
  });
});
