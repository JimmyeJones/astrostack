import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AutoEditOffNote } from "./AutoEditOffNote";
import * as client from "../../api/client";
import type { LibrarySessionRecap, Settings } from "../../api/client";

/** A night the hands-off scan stacked three targets and finished none of them. */
function recap(over: Partial<LibrarySessionRecap> = {}): LibrarySessionRecap {
  return {
    n_targets: 3, n_frames: 300, n_kept: 290, n_set_aside: 10,
    session_exposure_s: 18000, kept_exposure_s: 17400,
    start_utc: "2026-09-10T21:00:00+00:00", end_utc: "2026-09-11T03:00:00+00:00",
    night_date: "2026-09-10",
    targets: [],
    reject_buckets: {},
    new_pictures: [],
    auto_stacked: 3,
    auto_edited: 0,
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

const OFF = { auto_stack: true, auto_edit_on_autostack: false };

function renderNote() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><AutoEditOffNote /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("AutoEditOffNote", () => {
  it("offers the switch when the scan left its pictures unfinished", async () => {
    mock(OFF);
    const note = await (renderNote(),
      screen.findByTestId("auto-edit-off-note"));
    expect(note.textContent).toContain("stacked 3 of your targets");
    expect(note.textContent).toContain("plain stacks");
    expect(screen.getByRole("link", { name: /see what it does/i }))
      .toHaveAttribute("href", "/settings/automation");
  });

  it("turns it on with one click and says what happens next", async () => {
    mock(OFF);
    const put = vi.spyOn(client.api, "putSettings")
      .mockResolvedValue({} as unknown as Settings);
    renderNote();
    await screen.findByTestId("auto-edit-off-note");
    fireEvent.click(screen.getByRole("button", { name: /turn on auto-editing/i }));

    // The click gets an answer rather than the note merely vanishing — and the
    // answer is honest about the pictures already on disk, which this does not
    // retroactively finish.
    const done = await screen.findByTestId("auto-edit-on-note");
    expect(done.textContent).toContain("next scan");
    expect(done.textContent).toContain("already have are untouched");
    expect(screen.queryByTestId("auto-edit-off-note")).not.toBeInTheDocument();
    // A *patch* of one key: `SettingsStore.update` merges, so nothing else
    // moves — and `auto_stack` is deliberately not sent with it.
    expect(put).toHaveBeenCalledWith({ auto_edit_on_autostack: true });
  });

  it("says nothing when auto-editing is already on", async () => {
    mock({ auto_stack: true, auto_edit_on_autostack: true });
    renderNote();
    await waitFor(() => expect(client.api.getSettings).toHaveBeenCalled());
    expect(screen.queryByTestId("auto-edit-off-note")).not.toBeInTheDocument();
  });

  it("says nothing when the scan stacked nothing by itself", async () => {
    // Auto-stack off, or a night every target was held back: this switch would
    // have changed nothing, and `AutoStackOffNote` is the note that fits.
    mock(OFF, { auto_stacked: 0, auto_edited: 0 });
    renderNote();
    await waitFor(() => expect(client.api.getLastNight).toHaveBeenCalled());
    expect(screen.queryByTestId("auto-edit-off-note")).not.toBeInTheDocument();
  });

  it("says nothing when every stacked target was finished anyway", async () => {
    mock(OFF, { auto_stacked: 2, auto_edited: 2 });
    renderNote();
    await waitFor(() => expect(client.api.getLastNight).toHaveBeenCalled());
    expect(screen.queryByTestId("auto-edit-off-note")).not.toBeInTheDocument();
  });

  it("stays gone once dismissed, across a reload", async () => {
    mock(OFF);
    const first = renderNote();
    await screen.findByTestId("auto-edit-off-note");
    fireEvent.click(screen.getByRole("button", { name: /not now/i }));
    await waitFor(() =>
      expect(screen.queryByTestId("auto-edit-off-note")).not.toBeInTheDocument());

    // The half a component-local flag would miss.
    first.unmount();
    renderNote();
    await waitFor(() => expect(client.api.getSettings).toHaveBeenCalled());
    expect(screen.queryByTestId("auto-edit-off-note")).not.toBeInTheDocument();
  });

  it("says where to do it by hand when the save fails", async () => {
    mock(OFF);
    vi.spyOn(client.api, "putSettings").mockRejectedValue(new Error("nope"));
    renderNote();
    await screen.findByTestId("auto-edit-off-note");
    fireEvent.click(screen.getByRole("button", { name: /turn on auto-editing/i }));
    expect(await screen.findByText(/Settings → Automation/)).toBeInTheDocument();
  });

  it("stays silent when the settings can't be read", async () => {
    mock(null);
    renderNote();
    await waitFor(() => expect(client.api.getSettings).toHaveBeenCalled());
    expect(screen.queryByTestId("auto-edit-off-note")).not.toBeInTheDocument();
  });

  it("stays silent against a backend that doesn't send the tallies", async () => {
    // An older backend omits both fields; that must read as "nothing to say".
    const older = recap();
    delete older.auto_stacked;
    delete older.auto_edited;
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(older);
    vi.spyOn(client.api, "getSettings")
      .mockResolvedValue(OFF as unknown as Settings);
    renderNote();
    await waitFor(() => expect(client.api.getLastNight).toHaveBeenCalled());
    expect(screen.queryByTestId("auto-edit-off-note")).not.toBeInTheDocument();
  });

  it("stays silent against a backend with no last night at all", async () => {
    vi.spyOn(client.api, "getLastNight").mockResolvedValue(null);
    vi.spyOn(client.api, "getSettings")
      .mockResolvedValue(OFF as unknown as Settings);
    renderNote();
    await waitFor(() => expect(client.api.getLastNight).toHaveBeenCalled());
    expect(screen.queryByTestId("auto-edit-off-note")).not.toBeInTheDocument();
  });
});
