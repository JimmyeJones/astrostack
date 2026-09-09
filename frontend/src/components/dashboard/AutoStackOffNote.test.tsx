import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AutoStackOffNote } from "./AutoStackOffNote";
import * as client from "../../api/client";
import type { LibrarySessionRecap, Settings, TargetNight } from "../../api/client";

function tgt(over: Partial<TargetNight> = {}): TargetNight {
  return {
    name: "M 31", safe: "M_31",
    n_frames: 42, n_kept: 42, n_set_aside: 0,
    exposure_s: 2520, kept_exposure_s: 2520,
    ...over,
  };
}

/** A night that really was captured and really was stacked into nothing. */
function recap(over: Partial<LibrarySessionRecap> = {}): LibrarySessionRecap {
  return {
    n_targets: 1, n_frames: 42, n_kept: 42, n_set_aside: 0,
    session_exposure_s: 2520, kept_exposure_s: 2520,
    start_utc: "2026-09-08T21:00:00+00:00", end_utc: "2026-09-09T03:00:00+00:00",
    night_date: "2026-09-08",
    targets: [tgt()],
    reject_buckets: {},
    new_pictures: [],
    ...over,
  };
}

function mock(settings: Record<string, unknown> | null,
              over: Partial<LibrarySessionRecap> = {}) {
  vi.spyOn(client.api, "getLastNight").mockResolvedValue(recap(over));
  if (settings === null) {
    vi.spyOn(client.api, "getSettings").mockRejectedValue(new Error("offline"));
  } else {
    vi.spyOn(client.api, "getSettings")
      .mockResolvedValue(settings as unknown as Settings);
  }
}

const OFF = { auto_stack: false, auto_stack_min_frames: 3 };

function renderNote() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><AutoStackOffNote /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("AutoStackOffNote", () => {
  it("offers the switch on a night the app captured and stacked nothing", async () => {
    mock(OFF);
    const note = await (renderNote(),
      screen.findByTestId("auto-stack-off-note"));
    expect(note.textContent).toContain("Hands-off auto-stack is switched off");
    // Names the way back out. The owner has been bitten by an on-by-default
    // reframing before (v0.226.0's auto-crop), so the escape is part of the
    // offer, not a follow-up.
    expect(note.textContent).toContain("Settings");
    expect(screen.getByRole("link", { name: /see what it does/i }))
      .toHaveAttribute("href", "/settings/automation");
  });

  it("turns it on with one click and says what happens next", async () => {
    mock(OFF);
    const put = vi.spyOn(client.api, "putSettings")
      .mockResolvedValue({} as unknown as Settings);
    renderNote();
    await screen.findByTestId("auto-stack-off-note");
    fireEvent.click(screen.getByRole("button", { name: /turn on auto-stack/i }));

    // The click gets an answer rather than the note merely vanishing: auto-stack
    // acts on the next scan, after the settle window — not instantly.
    const done = await screen.findByTestId("auto-stack-on-note");
    expect(done.textContent).toContain("next scan");
    expect(screen.queryByTestId("auto-stack-off-note")).not.toBeInTheDocument();
    // A *patch* of one key: `SettingsStore.update` merges, so nothing else moves.
    expect(put).toHaveBeenCalledWith({ auto_stack: true });
  });

  it("says nothing when auto-stack is already on", async () => {
    mock({ auto_stack: true, auto_stack_min_frames: 3 });
    renderNote();
    await waitFor(() => expect(client.api.getSettings).toHaveBeenCalled());
    expect(screen.queryByTestId("auto-stack-off-note")).not.toBeInTheDocument();
  });

  it("says nothing on a night the app did make a picture", async () => {
    mock(OFF, {
      new_pictures: [{ name: "M 31", safe: "M_31", run_id: 4,
        when_utc: "2026-09-09T04:00:00+00:00", n_frames: 42, previous_frames: 20 }],
    });
    renderNote();
    await waitFor(() => expect(client.api.getLastNight).toHaveBeenCalled());
    expect(screen.queryByTestId("auto-stack-off-note")).not.toBeInTheDocument();
  });

  it("says nothing on a night too thin to have been stacked anyway", async () => {
    mock(OFF, { targets: [tgt({ n_kept: 2 })] });
    renderNote();
    await waitFor(() => expect(client.api.getLastNight).toHaveBeenCalled());
    expect(screen.queryByTestId("auto-stack-off-note")).not.toBeInTheDocument();
  });

  it("stays gone once dismissed, across a reload", async () => {
    mock(OFF);
    const first = renderNote();
    await screen.findByTestId("auto-stack-off-note");
    fireEvent.click(screen.getByRole("button", { name: /not now/i }));
    await waitFor(() =>
      expect(screen.queryByTestId("auto-stack-off-note")).not.toBeInTheDocument());

    // The half a component-local flag would miss.
    first.unmount();
    renderNote();
    await waitFor(() => expect(client.api.getSettings).toHaveBeenCalled());
    expect(screen.queryByTestId("auto-stack-off-note")).not.toBeInTheDocument();
  });

  it("says where to do it by hand when the save fails", async () => {
    mock(OFF);
    vi.spyOn(client.api, "putSettings").mockRejectedValue(new Error("nope"));
    renderNote();
    await screen.findByTestId("auto-stack-off-note");
    fireEvent.click(screen.getByRole("button", { name: /turn on auto-stack/i }));
    expect(await screen.findByText(/Settings → Automation/)).toBeInTheDocument();
  });

  it("stays silent when the settings can't be read", async () => {
    // Not "assume off": an unresolved or failed query must not flash an offer
    // onto every Dashboard load and then withdraw it.
    mock(null);
    renderNote();
    await waitFor(() => expect(client.api.getSettings).toHaveBeenCalled());
    expect(screen.queryByTestId("auto-stack-off-note")).not.toBeInTheDocument();
  });

  it("stays silent against a backend with no last night at all", async () => {
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(null);
    vi.spyOn(client.api, "getSettings")
      .mockResolvedValue(OFF as unknown as Settings);
    renderNote();
    await waitFor(() => expect(client.api.getLastNight).toHaveBeenCalled());
    expect(screen.queryByTestId("auto-stack-off-note")).not.toBeInTheDocument();
  });
});
