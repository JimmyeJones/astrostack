import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Library, UNSTRETCHED_HINT, expo } from "./Library";
import { UNSTRETCHED_UNEXPORTED_HINT } from "../unstretched";
import { thinStackWarning } from "../components/target/thinStack";
import * as client from "../api/client";
import type { Target } from "../api/client";

function mk(name: string, tags: string[], exposure = 0, notes: string | null = null): Target {
  return {
    safe_name: name.replace(/\s/g, "_"), name, ra_deg: null, dec_deg: null,
    n_frames: 10, n_frames_accepted: 8, total_exposure_s: exposure,
    last_activity_utc: null, has_preview: false, notes, tags,
  };
}

function renderLibrary() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><Library /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

/** Where the router ended up, so a click can be asserted on rather than
 *  described. The wall is rendered without a `<Routes>`, so this is the only
 *  thing in the tree that knows the location. */
function LocationProbe() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function renderLibraryWatchingTheUrl() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/library"]}>
          <Library />
          <LocationProbe />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();  // filters persist to localStorage — isolate tests
});

describe("expo", () => {
  it("speaks the shared app-wide integration vocabulary (formatIntegration)", () => {
    // expo now delegates to formatIntegration so the Library card is consistent
    // with the Dashboard/Target/History surfaces (and shows sub-minute totals
    // honestly instead of rounding a real "20 s" down to "0m").
    expect(expo(0)).toBe("—");
    expect(expo(20)).toBe("20 s");
    expect(expo(90)).toBe("2 min");
    expect(expo(3600)).toBe("1.0 h");
    expect(expo(5400)).toBe("1.5 h");
  });
});

describe("Library", () => {
  it("filters targets by search text and by tag", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([
      mk("Orion Nebula", ["nebula"]),
      mk("Andromeda", ["galaxy"]),
    ]);
    renderLibrary();

    await waitFor(() => expect(screen.getByText("Orion Nebula")).toBeInTheDocument());
    expect(screen.getByText("Andromeda")).toBeInTheDocument();

    const searchBox = screen.getByPlaceholderText("Search name, tag or note…");
    fireEvent.change(searchBox, { target: { value: "andro" } });
    await waitFor(() => expect(screen.queryByText("Orion Nebula")).not.toBeInTheDocument());
    expect(screen.getByText("Andromeda")).toBeInTheDocument();

    fireEvent.change(searchBox, { target: { value: "" } });
    await waitFor(() => expect(screen.getByText("Orion Nebula")).toBeInTheDocument());

    // Filter by the "nebula" tag chip (the Chip renders a checkbox input).
    fireEvent.click(screen.getByRole("checkbox", { name: "nebula" }));
    await waitFor(() => expect(screen.queryByText("Andromeda")).not.toBeInTheDocument());
    expect(screen.getByText("Orion Nebula")).toBeInTheDocument();
  });

  it("matches the search against a target's notes", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([
      mk("Orion Nebula", [], 0, "shot on a hazy night"),
      mk("Andromeda", [], 0, "crystal clear"),
    ]);
    renderLibrary();

    await waitFor(() => expect(screen.getByText("Orion Nebula")).toBeInTheDocument());
    const searchBox = screen.getByPlaceholderText("Search name, tag or note…");
    fireEvent.change(searchBox, { target: { value: "hazy" } });

    await waitFor(() => expect(screen.queryByText("Andromeda")).not.toBeInTheDocument());
    expect(screen.getByText("Orion Nebula")).toBeInTheDocument();
  });

  it("restores the saved search filter on remount", async () => {
    localStorage.setItem(
      "astrostack.library.filters",
      JSON.stringify({ search: "andro", sort: "recent", tags: [] }),
    );
    vi.spyOn(client.api, "listTargets").mockResolvedValue([
      mk("Orion Nebula", ["nebula"]),
      mk("Andromeda", ["galaxy"]),
    ]);
    renderLibrary();

    // The persisted "andro" search is applied immediately, hiding Orion.
    await waitFor(() => expect(screen.getByText("Andromeda")).toBeInTheDocument());
    expect(screen.queryByText("Orion Nebula")).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search name, tag or note…")).toHaveValue("andro");
  });

  it("points an empty library at upload, not an empty jobs page", async () => {
    // A brand-new user has zero targets *and* zero jobs. The empty state's only
    // prominent button used to be "View jobs", which sent them to an empty page
    // away from the upload card the copy points them at. The upload on-ramp must
    // be the CTA, with no misdirecting "View jobs" button.
    vi.spyOn(client.api, "listTargets").mockResolvedValue([]);
    renderLibrary();

    await waitFor(() => expect(screen.getByText("No targets yet.")).toBeInTheDocument());
    expect(screen.queryByRole("link", { name: "View jobs" })).not.toBeInTheDocument();
    // The upload card is present (its file picker button anchors it).
    expect(screen.getByRole("button", { name: /Choose FITS or \.zip/i })).toBeInTheDocument();
  });

  it("signposts Moon & Sun, so a lunar video doesn't read as 'you have nothing'",
    async () => {
      // A video capture never becomes a target (there are no subs to ingest), so
      // someone whose first night was the Moon lands on an empty Library with a
      // picture waiting one page away and no way to know it.
      vi.spyOn(client.api, "listTargets").mockResolvedValue([]);
      renderLibrary();

      await waitFor(() => expect(screen.getByText("No targets yet.")).toBeInTheDocument());
      const link = screen.getByRole("link", { name: /Moon & Sun/i });
      expect(link).toHaveAttribute("href", "/moon-sun");
    });

  it("doesn't clutter a library that has targets with the Moon & Sun signpost",
    async () => {
      vi.spyOn(client.api, "listTargets").mockResolvedValue([mk("Andromeda", ["galaxy"])]);
      renderLibrary();

      await waitFor(() => expect(screen.getByText("Andromeda")).toBeInTheDocument());
      expect(screen.queryByRole("link", { name: /Moon & Sun/i })).not.toBeInTheDocument();
    });

  it("shows the getting-started map on an empty library, and not once it has targets", async () => {
    // Library is as likely a first landing as the Dashboard (it's where the subs
    // go), so the "Your first image" checklist belongs on its empty state too.
    vi.spyOn(client.api, "getSystem").mockResolvedValue({
      version: "0.0.0", data_root: "/data", cpu_count: 4, cpu_workers: 3,
      gpu_available: false, disk: {}, memory: {}, watcher_enabled: true,
      astap: { found: false, path: null, star_db_found: false },
    } as never);
    vi.spyOn(client.api, "getStats").mockResolvedValue({
      n_targets: 0, n_frames: 0, n_frames_accepted: 0, total_exposure_s: 0,
      integration_hours: 0, acceptance_rate: null, n_stack_runs: 0,
      n_targets_with_stacks: 0, active_jobs: 0, recent_stacks: [], disk: {},
    } as never);
    vi.spyOn(client.api, "listTargets").mockResolvedValue([]);
    const { unmount } = renderLibrary();
    await waitFor(() =>
      expect(screen.getByTestId("first-image-card")).toBeInTheDocument());
    unmount();

    // With targets present the empty state (and the card with it) is gone.
    vi.spyOn(client.api, "listTargets").mockResolvedValue([mk("Andromeda", [])]);
    renderLibrary();
    await waitFor(() => expect(screen.getByText("Andromeda")).toBeInTheDocument());
    expect(screen.queryByTestId("first-image-card")).not.toBeInTheDocument();
  });
});

describe("Library card layout", () => {
  it("keeps the 'go to target' chevron on the title's own line", async () => {
    // Seen in a 1440 px screenshot: `<Group justify="space-between">` wraps by
    // default, so a name long enough to fill the card pushed the chevron down
    // and the card showed a stray "›" hanging alone below the title. jsdom has
    // no layout, so pin the cause — the row may not wrap, and the icon may not
    // shrink (which is what stops "nowrap" turning the wrap into a squeeze).
    vi.spyOn(client.api, "listTargets").mockResolvedValue([
      mk("Sample: Orion Nebula (M42)", []),
    ]);
    renderLibrary();

    const name = await screen.findByText("Sample: Orion Nebula (M42)");
    const row = name.parentElement as HTMLElement;
    // Mantine's `Group` drives its wrapping through a CSS variable, and jsdom
    // loads no stylesheet — so read the variable the component actually sets.
    expect(row.style.getPropertyValue("--group-wrap")).toBe("nowrap");
    const chevron = row.querySelector("svg") as SVGElement;
    expect(chevron).toHaveStyle({ flexShrink: "0" });
  });

  it("keeps a long target name readable even when the card truncates it", async () => {
    // The name truncates so the chevron always fits; the full text has to stay
    // recoverable on hover, exactly as the Gallery card's name already is.
    vi.spyOn(client.api, "listTargets").mockResolvedValue([
      mk("Sample: Orion Nebula (M42)", []),
    ]);
    renderLibrary();

    const name = await screen.findByText("Sample: Orion Nebula (M42)");
    expect(name).toHaveAttribute("title", "Sample: Orion Nebula (M42)");
  });
});

describe("Library — the \"Not stretched yet\" chip", () => {
  // A stack straight out of the stacker is linear: on a 160px card it is a
  // dark square, and so is the finished version of the same data. The wall
  // could not tell them apart and neither can a beginner — observer issue #903
  // left 44 of the owner's targets in exactly that state at once, with nothing
  // anywhere saying so.

  it("chips only the targets whose picture is still a flat linear stack", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([
      mk("Orion Nebula", []), mk("Andromeda", []),
    ]);
    vi.spyOn(client.api, "getUnstretchedPictures").mockResolvedValue({
      count: 1,
      items: [{ safe: "Andromeda", target_name: "Andromeda", run_id: 7 }],
    });
    renderLibrary();

    await waitFor(() =>
      expect(screen.getByText("Not stretched yet")).toBeInTheDocument());
    // Exactly one — a "Finished" chip on every other card would be a wall of
    // badges saying nothing.
    expect(screen.getAllByText("Not stretched yet")).toHaveLength(1);
  });

  it("says what to do about it, in plain language", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([mk("Andromeda", [])]);
    vi.spyOn(client.api, "getUnstretchedPictures").mockResolvedValue({
      count: 1,
      items: [{ safe: "Andromeda", target_name: "Andromeda", run_id: 7 }],
    });
    renderLibrary();

    const chip = await screen.findByText("Not stretched yet");
    // Mantine's Badge puts the label in a child span, so the tooltip lives on
    // the badge root the label sits inside.
    expect(chip.closest("[title]")).toHaveAttribute("title", UNSTRETCHED_HINT);
    // It names the one click the chip now *is*, and the Auto the editor runs on
    // arrival. The sentence used to say "Open it and press Auto", which had been
    // stale since v0.390.0 made the editor seed Auto by itself — and vaguer than
    // the Gallery's hint for the identical state, which has named its own
    // control since v0.448.2.
    expect(UNSTRETCHED_HINT).toContain("Click this chip");
    expect(UNSTRETCHED_HINT).toContain("editor");
    expect(UNSTRETCHED_HINT).toContain("Auto");
    expect(UNSTRETCHED_HINT).toContain("reversible");
  });

  it("stops telling someone with a saved edit to press Auto", async () => {
    // Auto *replaces* the recipe in the editor, so the standing hint's advice is
    // the one thing to withhold from a card that is unstretched because its
    // owner's edit was never exported — they did stretch this picture; what is
    // missing is the export. Same state History and the Gallery label
    // "edit not exported".
    vi.spyOn(client.api, "listTargets").mockResolvedValue([mk("Andromeda", [])]);
    vi.spyOn(client.api, "getUnstretchedPictures").mockResolvedValue({
      count: 1,
      items: [{ safe: "Andromeda", target_name: "Andromeda", run_id: 7,
                unexported_edit: true }],
    });
    renderLibrary();

    const chip = await screen.findByText("Not stretched yet");
    const title = chip.closest("[title]")?.getAttribute("title") ?? "";
    expect(title).toBe(UNSTRETCHED_UNEXPORTED_HINT);
    expect(title).toContain("never exported it");
    expect(title).not.toContain("press Auto to stretch");
    expect(title).toContain("don't press Auto");
  });

  it("keeps the ordinary hint when an older backend omits the flag", async () => {
    // The field is additive, so its absence has to read as "an ordinary
    // unstretched card" rather than as either kind of guess.
    vi.spyOn(client.api, "listTargets").mockResolvedValue([mk("Andromeda", [])]);
    vi.spyOn(client.api, "getUnstretchedPictures").mockResolvedValue({
      count: 1,
      items: [{ safe: "Andromeda", target_name: "Andromeda", run_id: 7 }],
    });
    renderLibrary();

    const chip = await screen.findByText("Not stretched yet");
    expect(chip.closest("[title]")).toHaveAttribute("title", UNSTRETCHED_HINT);
  });

  it("takes one click from the chip to that picture's own editor", async () => {
    // The point of the chip is the fix, and until now the card could only
    // offer the target page — the editor's own button is a screen further in,
    // past a phone page ~3,300 px tall. The run the chip is about is the one
    // the endpoint already names, so the link costs nothing on the wire.
    vi.spyOn(client.api, "listTargets").mockResolvedValue([mk("Andromeda", [])]);
    vi.spyOn(client.api, "getUnstretchedPictures").mockResolvedValue({
      count: 1,
      items: [{ safe: "Andromeda", target_name: "Andromeda", run_id: 7 }],
    });
    renderLibraryWatchingTheUrl();

    const chip = await screen.findByText("Not stretched yet");
    // A real button, so it is reachable by keyboard and announced as a control
    // — the chip is no longer only a label.
    const control = chip.closest("button");
    expect(control).not.toBeNull();
    fireEvent.click(control!);
    await waitFor(() => expect(screen.getByTestId("where"))
      .toHaveTextContent("/targets/Andromeda/edit/7"));
  });

  it("leaves the rest of the card going to the target, as it always did", async () => {
    // The chip stops its own click (the card is one <Link>); nothing else about
    // the card changes, which is the whole constraint here — the owner's rule is
    // that nothing may be removed or moved out from under him.
    vi.spyOn(client.api, "listTargets").mockResolvedValue([mk("Andromeda", [])]);
    vi.spyOn(client.api, "getUnstretchedPictures").mockResolvedValue({
      count: 1,
      items: [{ safe: "Andromeda", target_name: "Andromeda", run_id: 7 }],
    });
    renderLibraryWatchingTheUrl();

    const name = await screen.findByText("Andromeda");
    expect(name.closest("a")).toHaveAttribute("href", "/targets/Andromeda");
    fireEvent.click(name);
    await waitFor(() => expect(screen.getByTestId("where"))
      .toHaveTextContent("/targets/Andromeda"));
    expect(screen.getByTestId("where")).not.toHaveTextContent("/edit/");
  });

  it("sends a never-exported edit to the same run, to export rather than re-Auto", async () => {
    // Same destination, different job once you are there: the editor stands
    // aside for a saved recipe (v0.390.0), so this lands on their own look.
    vi.spyOn(client.api, "listTargets").mockResolvedValue([mk("Andromeda", [])]);
    vi.spyOn(client.api, "getUnstretchedPictures").mockResolvedValue({
      count: 1,
      items: [{ safe: "Andromeda", target_name: "Andromeda", run_id: 12,
                unexported_edit: true }],
    });
    renderLibraryWatchingTheUrl();

    const chip = await screen.findByText("Not stretched yet");
    fireEvent.click(chip.closest("button")!);
    await waitFor(() => expect(screen.getByTestId("where"))
      .toHaveTextContent("/targets/Andromeda/edit/12"));
  });

  it("stays a plain label when the response carries no usable run id", async () => {
    // An older backend, or a field that failed to serialise: the chip must read
    // exactly as it did before rather than become a link to `…/edit/0`.
    vi.spyOn(client.api, "listTargets").mockResolvedValue([mk("Andromeda", [])]);
    vi.spyOn(client.api, "getUnstretchedPictures").mockResolvedValue({
      count: 1,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      items: [{ safe: "Andromeda", target_name: "Andromeda" } as any],
    });
    renderLibraryWatchingTheUrl();

    const chip = await screen.findByText("Not stretched yet");
    expect(chip.closest("button")).toBeNull();
    expect(chip.closest("[title]")).toHaveAttribute("title", UNSTRETCHED_HINT);
  });

  it("shows no chips on a library where every picture is finished", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([mk("Orion Nebula", [])]);
    vi.spyOn(client.api, "getUnstretchedPictures").mockResolvedValue({
      count: 0, items: [],
    });
    renderLibrary();

    await waitFor(() =>
      expect(screen.getByText("Orion Nebula")).toBeInTheDocument());
    expect(screen.queryByText("Not stretched yet")).not.toBeInTheDocument();
  });

  it("renders the wall exactly as before when the endpoint isn't there", async () => {
    // An older backend, or a failed read: the wall must be the wall, not an
    // error and not a chip on everything.
    vi.spyOn(client.api, "listTargets").mockResolvedValue([mk("Orion Nebula", [])]);
    vi.spyOn(client.api, "getUnstretchedPictures")
      .mockRejectedValue(new Error("404 Not Found"));
    renderLibrary();

    await waitFor(() =>
      expect(screen.getByText("Orion Nebula")).toBeInTheDocument());
    expect(screen.queryByText("Not stretched yet")).not.toBeInTheDocument();
  });
});

describe("Library — the \"Thin — keep shooting\" chip", () => {
  // The other thing a Library card could not say about itself. The only number
  // on it is the target's *total* frame count, which on a mosaic says nothing
  // about what one patch of sky got: thirty subs over a 3x3 raster is three
  // everywhere. The Gallery card of the very same run already turns its frame
  // badge orange; the wall said nothing at all.

  it("chips a mosaic whose total flatters it, and not a deep single field", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([
      mk("Orion Nebula", []), mk("Andromeda", []),
    ]);
    vi.spyOn(client.api, "getUnstretchedPictures").mockResolvedValue({
      count: 0, items: [], thin_count: 1,
      thin: [{ safe: "Andromeda", target_name: "Andromeda", run_id: 7,
               n_frames_used: 30, field_fulls: 9 }],
    });
    renderLibrary();

    await waitFor(() =>
      expect(screen.getByText("Thin — keep shooting")).toBeInTheDocument());
    expect(screen.getAllByText("Thin — keep shooting")).toHaveLength(1);
  });

  it("says both numbers, so the card and the Gallery agree about one picture", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([mk("Andromeda", [])]);
    vi.spyOn(client.api, "getUnstretchedPictures").mockResolvedValue({
      count: 0, items: [], thin_count: 1,
      thin: [{ safe: "Andromeda", target_name: "Andromeda", run_id: 7,
               n_frames_used: 30, field_fulls: 9 }],
    });
    renderLibrary();

    const chip = await screen.findByText("Thin — keep shooting");
    const title = chip.closest("[title]")?.getAttribute("title") ?? "";
    // `thinStackWarning`'s own sentence, word for word — not a second one.
    expect(title).toBe(
      thinStackWarning(30, 9, "open-it")?.message);
    expect(title).toContain("Your 30 subs are spread across about 9 fields of sky");
    expect(title).toContain("only about 3 subs on it");
    // A wall card carries no "rejected" count for the sentence to point at.
    expect(title).toContain('open it and check the "rejected" count');
    expect(title).not.toContain("count above");
  });

  it("gives depth the slot when a card is both thin and unstretched", async () => {
    // "Press Auto" cannot make a one-sub stack anything but a stretched one-sub
    // stack — stretching noise only makes it easier to see. The upstream
    // problem is the one worth naming, and one chip rather than two because
    // clutter is the owner's standing complaint.
    vi.spyOn(client.api, "listTargets").mockResolvedValue([mk("Andromeda", [])]);
    vi.spyOn(client.api, "getUnstretchedPictures").mockResolvedValue({
      count: 1,
      items: [{ safe: "Andromeda", target_name: "Andromeda", run_id: 7 }],
      thin_count: 1,
      thin: [{ safe: "Andromeda", target_name: "Andromeda", run_id: 7,
               n_frames_used: 1, field_fulls: null }],
    });
    renderLibrary();

    await waitFor(() =>
      expect(screen.getByText("Thin — keep shooting")).toBeInTheDocument());
    expect(screen.queryByText("Not stretched yet")).not.toBeInTheDocument();
  });

  it("renders the wall exactly as before when the backend omits the list", async () => {
    // Additive fields: an older backend must read as "nothing to chip", never
    // as a chip on everything.
    vi.spyOn(client.api, "listTargets").mockResolvedValue([mk("Orion Nebula", [])]);
    vi.spyOn(client.api, "getUnstretchedPictures").mockResolvedValue({
      count: 0, items: [],
    });
    renderLibrary();

    await waitFor(() =>
      expect(screen.getByText("Orion Nebula")).toBeInTheDocument());
    expect(screen.queryByText("Thin — keep shooting")).not.toBeInTheDocument();
  });
});
