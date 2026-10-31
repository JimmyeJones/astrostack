import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter as Router, Route, Routes, useParams } from "react-router-dom";
import { SampleImageCard, sampleRunToEdit } from "./SampleImageCard";
import type { DashboardStats, SampleStatus, StackRun } from "../api/client";
import * as client from "../api/client";

function stats(nTargets: number): DashboardStats {
  return {
    n_targets: nTargets,
    n_frames: 0,
    n_frames_accepted: 0,
    total_exposure_s: 0,
    integration_hours: 0,
    acceptance_rate: null,
    n_stack_runs: 0,
    n_targets_with_stacks: 0,
    active_jobs: 0,
    recent_stacks: [],
    disk: {},
  };
}

function sample(over: Partial<SampleStatus> = {}): SampleStatus {
  return { loaded: false, safe: null, n_frames: 0, ...over };
}

function run(id: number, over: Partial<StackRun> = {}): StackRun {
  return {
    id, timestamp_utc: "2026-10-31T00:00:00Z", output_basename: `master_${id}`,
    n_frames_used: 6, canvas_w: 480, canvas_h: 320, coverage_min: 6, coverage_max: 6,
    has_fits: true, has_tiff: false, has_preview: true, notes: null, ...over,
  } as StackRun;
}

function EditorProbe() {
  const { safe, id } = useParams();
  return <div>{`editor: ${safe} / ${id}`}</div>;
}

/** A loaded sample whose target has `runs` (newest first, as the API returns). */
function loadedSample(runs: StackRun[]) {
  vi.spyOn(client.api, "getSampleStatus").mockResolvedValue(
    sample({ loaded: true, safe: "sample_orion", n_frames: 6 }),
  );
  vi.spyOn(client.api, "getStats").mockResolvedValue(stats(1));
  return vi.spyOn(client.api, "listStackRuns").mockResolvedValue(runs);
}

function renderCard() {
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <SampleImageCard />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("SampleImageCard", () => {
  it("offers the sample on an empty library and loads it on click", async () => {
    vi.spyOn(client.api, "getSampleStatus").mockResolvedValue(sample());
    vi.spyOn(client.api, "getStats").mockResolvedValue(stats(0));
    const load = vi.spyOn(client.api, "loadSample").mockResolvedValue(
      sample({ loaded: true, safe: "sample_orion", n_frames: 6 }),
    );
    renderCard();

    await waitFor(() =>
      expect(screen.getByText(/Try it with a sample image/i)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Try it/i }));
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
  });

  it("shows a ready + remove state once the sample is loaded", async () => {
    loadedSample([]);
    const remove = vi.spyOn(client.api, "removeSample").mockResolvedValue(sample());
    renderCard();

    await waitFor(() =>
      expect(screen.getByText(/Your sample target is ready/i)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Remove/i }));
    await waitFor(() => expect(remove).toHaveBeenCalledTimes(1));
  });

  it("stacks the sample in one tap and navigates to its target", async () => {
    loadedSample([]);
    const trigger = vi.spyOn(client.api, "triggerStack").mockResolvedValue({ job_id: "j1" });
    renderCard();

    await waitFor(() =>
      expect(screen.getByText(/Your sample target is ready/i)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Stack it/i }));
    await waitFor(() => expect(trigger).toHaveBeenCalledTimes(1));
    expect(trigger).toHaveBeenCalledWith("sample_orion", {});
  });

  it("lets the buttons drop to their own line instead of crushing the words", async () => {
    // Found by dogfooding at 420 px: `wrap="nowrap"` on the row, a `minWidth: 0`
    // wording column and a `flexShrink: 0` three-button group left the text ~50
    // px, so "Your sample target is ready" rendered one word per line as a
    // ~25-line ribbon on the Dashboard a beginner sees first. jsdom has no
    // layout, so pin the cause: the row may wrap, and the wording column is
    // based on its content width rather than zero.
    loadedSample([]);
    renderCard();

    const heading = await screen.findByText(/Your sample target is ready/i);
    // Text -> Stack -> the wording Group.
    const wording = heading.parentElement!.parentElement as HTMLElement;
    expect(wording).toHaveStyle({ flex: "1 1 240px" });
    const row = wording.parentElement as HTMLElement;
    expect(getComputedStyle(row).flexWrap).not.toBe("nowrap");
  });

  it("hides entirely when there's real data and no sample", async () => {
    vi.spyOn(client.api, "getSampleStatus").mockResolvedValue(sample());
    vi.spyOn(client.api, "getStats").mockResolvedValue(stats(3));
    const { container } = renderCard();

    // Give the queries a tick to resolve, then assert nothing rendered.
    await waitFor(() => expect(client.api.getSampleStatus).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByText(/sample image/i)).not.toBeInTheDocument(),
    );
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });

  it("asks for the run list of the loaded sample only", async () => {
    const list = loadedSample([]);
    renderCard();
    await screen.findByText(/Your sample target is ready/i);
    expect(list).toHaveBeenCalledWith("sample_orion");
  });

  it("does not ask for runs while no sample is loaded", async () => {
    vi.spyOn(client.api, "getSampleStatus").mockResolvedValue(sample());
    vi.spyOn(client.api, "getStats").mockResolvedValue(stats(0));
    const list = vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    renderCard();
    await screen.findByText(/Try it with a sample image/i);
    expect(list).not.toHaveBeenCalled();
  });

  // Found by dogfooding (2026-10-31): with the sample already stacked, the
  // Dashboard still said "Your sample target is ready" and led with "Stack it",
  // which only makes a duplicate of the picture he already has.
  it("points a stacked sample at the editor instead of stacking it again", async () => {
    loadedSample([run(2), run(1)]);
    render(
      <MantineProvider>
        <Notifications />
        <QueryClientProvider client={new QueryClient()}>
          <Router initialEntries={["/"]}>
            <Routes>
              <Route path="/" element={<SampleImageCard />} />
              <Route path="/targets/:safe/edit/:id"
                     element={<EditorProbe />} />
            </Routes>
          </Router>
        </QueryClientProvider>
      </MantineProvider>,
    );

    await screen.findByText(/Your sample is stacked — try the editor next/i);
    expect(screen.queryByText(/Your sample target is ready/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Stack it$/i })).not.toBeInTheDocument();
    // Stacking stays reachable — nothing is removed, it just stops leading.
    expect(screen.getByRole("button", { name: /Stack again/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Remove/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Edit it/i }));
    // The newest run with a picture — run 2 — on the sample's own target.
    await screen.findByText("editor: sample_orion / 2");
  });

  it("Stack again still stacks the sample", async () => {
    loadedSample([run(1)]);
    const trigger = vi.spyOn(client.api, "triggerStack").mockResolvedValue({ job_id: "j1" });
    renderCard();
    fireEvent.click(await screen.findByRole("button", { name: /Stack again/i }));
    await waitFor(() => expect(trigger).toHaveBeenCalledWith("sample_orion", {}));
  });

  it("keeps the Stack it wording when the run list cannot be read", async () => {
    vi.spyOn(client.api, "getSampleStatus").mockResolvedValue(
      sample({ loaded: true, safe: "sample_orion", n_frames: 6 }),
    );
    vi.spyOn(client.api, "getStats").mockResolvedValue(stats(1));
    vi.spyOn(client.api, "listStackRuns").mockRejectedValue(new Error("offline"));
    renderCard();
    await screen.findByText(/Your sample target is ready/i);
    expect(screen.getByRole("button", { name: /^Stack it$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Edit it/i })).not.toBeInTheDocument();
  });
});

describe("sampleRunToEdit", () => {
  it("is null with no runs or an unknown list", () => {
    expect(sampleRunToEdit(undefined)).toBeNull();
    expect(sampleRunToEdit([])).toBeNull();
  });

  it("takes the newest run that has a picture, else the newest", () => {
    expect(sampleRunToEdit([run(3, { has_preview: false }), run(2), run(1)])?.id).toBe(2);
    expect(sampleRunToEdit([run(3, { has_preview: false })])?.id).toBe(3);
  });
});
