import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EditorView } from "./Editor";
import * as client from "../api/client";
import type { EditOp } from "../api/client";

const STRETCH: EditOp = {
  id: "tone.stretch", label: "Stretch", group: "tone", stage: "any",
  proxy_safe: true, is_stretch: true, help: "tone map",
  params: [{ key: "stretch", label: "Strength", type: "float", group: "simple",
             default: 0.5, min: 0, max: 1, step: 0.01, options: null, help: null,
             depends_on: null }],
};
const CURVES: EditOp = {
  id: "tone.curves", label: "Curves", group: "tone", stage: "nonlinear",
  proxy_safe: true, is_stretch: false, help: null,
  params: [{ key: "points", label: "Curve", type: "curve", group: "simple",
             default: [[0, 0], [1, 1]], min: null, max: null, step: null,
             options: null, help: null, depends_on: null }],
};
const DECONVOLVE: EditOp = {
  id: "detail.deconvolve", label: "Deconvolution", group: "detail", stage: "linear",
  proxy_safe: true, is_stretch: false, heavy: true, help: "heavy",
  params: [{ key: "psf_sigma", label: "PSF σ (px)", type: "float", group: "simple",
             default: 1.5, min: 0.5, max: 5, step: 0.1, options: null, help: null,
             depends_on: null }],
};

const SHARPEN: EditOp = {
  id: "detail.sharpen", label: "Sharpen", group: "detail", stage: "nonlinear",
  proxy_safe: true, is_stretch: false, help: null,
  params: [{ key: "radius", label: "Radius (px)", type: "float", group: "simple",
             default: 2.0, min: 0.5, max: 10, step: 0.5, options: null, help: null,
             depends_on: null }],
};

const LEVELS: EditOp = {
  id: "tone.levels", label: "Levels", group: "tone", stage: "nonlinear",
  proxy_safe: true, is_stretch: false, help: null,
  params: [
    { key: "black", label: "Black point", type: "float", group: "simple", default: 0,
      min: 0, max: 1, step: 0.01, options: null, help: null, depends_on: null },
    { key: "white", label: "White point", type: "float", group: "simple", default: 1,
      min: 0, max: 1, step: 0.01, options: null, help: null, depends_on: null },
    { key: "gamma", label: "Midtones (gamma)", type: "float", group: "simple", default: 1,
      min: 0.1, max: 5, step: 0.05, options: null, help: null, depends_on: null },
  ],
};

const LEVEL_COVERAGE: EditOp = {
  id: "background.level_coverage", label: "Coverage leveling", group: "background",
  stage: "linear", proxy_safe: true, is_stretch: false,
  help: "Equalize sky across mosaic panels with different frame coverage.",
  params: [{ key: "object_sigma", label: "Object σ", type: "float", group: "advanced",
             default: 2.0, min: 1, max: 5, step: 0.1, options: null, help: null,
             depends_on: null }],
};

const CROP: EditOp = {
  id: "geometry.crop", label: "Crop", group: "stars_geometry", stage: "nonlinear",
  proxy_safe: true, is_stretch: false, help: "Crop to a fractional rectangle.",
  params: [
    { key: "x0", label: "Left", type: "float", group: "simple", default: 0,
      min: 0, max: 1, step: 0.01, options: null, help: null, depends_on: null },
    { key: "y0", label: "Top", type: "float", group: "simple", default: 0,
      min: 0, max: 1, step: 0.01, options: null, help: null, depends_on: null },
    { key: "x1", label: "Right", type: "float", group: "simple", default: 1,
      min: 0, max: 1, step: 0.01, options: null, help: null, depends_on: null },
    { key: "y1", label: "Bottom", type: "float", group: "simple", default: 1,
      min: 0, max: 1, step: 0.01, options: null, help: null, depends_on: null },
  ],
};

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    qc,
    ...render(
      <MantineProvider>
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={["/targets/M_42/edit/3"]}>
            <Routes>
              <Route path="/targets/:safe/edit/:runId" element={<EditorView />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </MantineProvider>,
    ),
  };
}

afterEach(() => vi.restoreAllMocks());

beforeEach(() => {
  // jsdom lacks object-URL APIs the blob preview uses.
  vi.stubGlobal("URL", Object.assign(URL, {
    createObjectURL: vi.fn(() => "blob:mock"),
    revokeObjectURL: vi.fn(),
  }));
});

function mockEditorQueries() {
  vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, CURVES]);
  vi.spyOn(client.api, "getRecipe").mockResolvedValue({
    ops: [{ uid: "x1", id: "tone.stretch", enabled: true, params: { stretch: 0.6 } }],
    base_run_id: 3,
  });
  vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
  vi.spyOn(client.api, "getHistogram").mockResolvedValue(
    { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
}

describe("EditorView", () => {
  it("loads the saved recipe and renders its operations", async () => {
    mockEditorQueries();
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    // Wait on the recipe-dependent text, not the static toolbar: "Add operation"
    // renders before the saved-recipe query resolves, so gating on it (then
    // checking "Stretch" synchronously) raced and flaked in slower CI.
    expect(await screen.findByText("Stretch")).toBeInTheDocument();
    expect(screen.getByText("Add operation")).toBeInTheDocument();
    expect(screen.getByText("Export as new image")).toBeInTheDocument();
    expect(screen.getByText("Download full-res PNG")).toBeInTheDocument();
  });

  it("seeds the recipe only once — a refetch (e.g. after Save) does not re-seed and wipe edits", async () => {
    mockEditorQueries();
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    const getRecipe = client.api.getRecipe as unknown as ReturnType<typeof vi.fn>;
    const { qc } = renderEditor();
    expect(await screen.findByText("Stretch")).toBeInTheDocument();
    const callsAfterMount = getRecipe.mock.calls.length;

    // Simulate the refetch a save triggers: the recipe query now resolves a
    // structurally-different snapshot. Before the fix, the seeding effect re-ran
    // and replaced the working ops (clobbering edits / undo history); after the
    // fix, the already-seeded pipeline is left untouched.
    getRecipe.mockResolvedValue({
      ops: [{ uid: "y9", id: "tone.curves", enabled: true,
              params: { points: [[0, 0], [1, 1]] } }],
      base_run_id: 3,
    });
    await qc.invalidateQueries({ queryKey: ["recipe", "M_42", 3] });
    await waitFor(() =>
      expect(getRecipe.mock.calls.length).toBeGreaterThan(callsAfterMount));

    // The originally-seeded Stretch op stays; the refetched Curves op is ignored.
    expect(screen.getByText("Stretch")).toBeInTheDocument();
    expect(screen.queryByText("Curves")).not.toBeInTheDocument();
  });

  it("shows render progress while the full-res PNG job is polling", async () => {
    mockEditorQueries();
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));
    vi.spyOn(client.api, "exportPng").mockResolvedValue({ job_id: "png1" });
    // First poll: still rendering with progress → the label shows; second: done.
    const runningJob = { id: "png1", kind: "editor_png", target: "M_42", state: "running",
      phase: "Rendering", done: 1, total: 2, detail: "", created_utc: null, started_utc: null,
      finished_utc: null, error: null, result: null };
    let polls = 0;
    vi.spyOn(client.api, "getJob").mockImplementation(async () => {
      polls += 1;
      return polls === 1 ? runningJob : { ...runningJob, state: "done" };
    });

    renderEditor();

    const btn = await screen.findByText("Download full-res PNG");
    fireEvent.click(btn);
    await waitFor(() => expect(screen.getByText("Rendering — 50%")).toBeInTheDocument());
  });

  it("threads an AbortSignal into the live-preview fetch so stale renders can be cancelled", async () => {
    mockEditorQueries();
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    renderEditor();

    await screen.findByText("Stretch");
    // The preview fetch must be called with an options object carrying an
    // AbortSignal, so react-query can abort a superseded render when the recipe
    // changes (the "heavy ops lag" hold-out) instead of running it to completion.
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const previewCall = fetchMock.mock.calls.find(
      (c) => typeof c[0] === "string" && c[0].includes("/editor/preview"));
    expect(previewCall).toBeDefined();
    expect(previewCall![1]?.signal).toBeInstanceOf(AbortSignal);
  });

  it("shows a 'Measured' data-context chip built from the suggestion queries", async () => {
    mockEditorQueries();
    vi.spyOn(client.api, "psfSuggestion").mockResolvedValue({ fwhm_px: 3.2, psf_sigma: 1.36 });
    vi.spyOn(client.api, "denoiseSuggestion")
      .mockResolvedValue({ noise_sigma: 0.021, strength: 0.4 });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    await screen.findByText("Stretch");
    expect(await screen.findByText(
      "Measured: stars ≈ 3.2 px FWHM · background noise σ 0.021")).toBeInTheDocument();
  });

  it("keeps the old preview with an 'Updating…' badge while a fresh render is in flight", async () => {
    mockEditorQueries();
    // Start with a fetch that resolves so the editor settles to a shown image and
    // no in-flight render; then swap to a never-resolving fetch and trigger a new
    // render — keepPreviousData keeps the old image and the badge should appear.
    const okResponse = () =>
      ({ ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }) });
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => okResponse());
    vi.stubGlobal("fetch", fetchMock);

    renderEditor();

    await screen.findByText("Stretch");
    await waitFor(() => expect(screen.getByAltText("preview")).toBeInTheDocument());
    // Settled: nothing rendering, so no badge.
    await waitFor(() => expect(screen.queryByText("Updating…")).not.toBeInTheDocument());

    // Next render never resolves; an edit changes the recipe → new fetch pends.
    fetchMock.mockImplementation(() => new Promise(() => {}) as never);
    fireEvent.click(screen.getByText("Add operation"));
    fireEvent.click(await screen.findByText("Curves"));

    // The old image is still shown (not a black Loader) and the badge appears.
    expect(await screen.findByText("Updating…")).toBeInTheDocument();
    expect(screen.getByAltText("preview")).toBeInTheDocument();
  });

  it("toggles the star-mask overlay and fetches the mask", async () => {
    mockEditorQueries();
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));
    const maskUrl = vi.spyOn(client.api, "editStarMaskUrl");

    renderEditor();

    const btn = await screen.findByRole("button", { name: "Star mask" });
    await waitFor(() => expect(btn).not.toBeDisabled());
    btn.click();

    // No star op is selected, so the overlay uses the endpoint default size (undefined)
    // and no star-op uid — but it now passes the recipe so the mask is computed on the
    // display-space image the ops gate on, not the raw linear proxy.
    await waitFor(() => expect(maskUrl).toHaveBeenCalled());
    const calls = maskUrl.mock.calls;
    const call = calls[calls.length - 1];
    expect(call.slice(0, 3)).toEqual(["M_42", 3, undefined]);
    expect(call[3]).toBeTypeOf("object");   // the current recipe
    expect(call[4]).toBeUndefined();          // no star op selected → no uid
    // The overlay label switches to "Star mask" and the button flips to "Hide mask".
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Hide mask" })).toBeInTheDocument());
  });

  it("titles the zoom lightbox from the active overlay, not 'edited'", async () => {
    // Regression: the lightbox titled whatever was shown as 'edited' unless
    // Compare was on, so zooming the star-mask overlay mislabelled the mask.
    mockEditorQueries();
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    const btn = await screen.findByRole("button", { name: "Star mask" });
    await waitFor(() => expect(btn).not.toBeDisabled());
    btn.click();
    await screen.findByRole("button", { name: "Hide mask" });

    // Open the zoom lightbox by clicking the shown (overlay) image.
    const shown = await screen.findByAltText("preview");
    shown.click();
    // The lightbox image is titled from the overlay ("Star mask"), never "edited".
    await waitFor(() =>
      expect(screen.getByAltText(/Star mask/)).toBeInTheDocument());
    expect(screen.queryByAltText(/— edited/)).not.toBeInTheDocument();
  });

  it("surfaces an overlay fetch error instead of showing the edited image under the overlay's label", async () => {
    mockEditorQueries();
    // Preview succeeds, but the star-mask endpoint fails — previously the panel
    // silently showed the edited preview captioned "Star mask" (A/B against
    // itself); now it shows an error and no mislabeled caption.
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (typeof url === "string" && url.includes("/editor/star-mask")) {
        return { ok: false, status: 500, json: async () => ({ detail: "mask boom" }) };
      }
      return { ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }) };
    }));

    renderEditor();

    const btn = await screen.findByRole("button", { name: "Star mask" });
    await waitFor(() => expect(btn).not.toBeDisabled());
    btn.click();

    await waitFor(() =>
      expect(screen.getByText(/star mask overlay failed to load/i)).toBeInTheDocument());
    // The button has flipped to "Hide mask" and the mislabeled "Star mask" caption
    // is suppressed, so no "Star mask" text remains on the panel. The caption is
    // torn down on a separate render tick from the error message, so wait for it
    // to actually disappear rather than asserting synchronously (which raced the
    // suppression under slow-CI load).
    await waitFor(() =>
      expect(screen.queryByText("Star mask")).not.toBeInTheDocument());
  });

  it("reveals a before/after split overlay (Original clipped + divider) when toggled", async () => {
    mockEditorQueries();
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    const btn = await screen.findByRole("button", { name: "Split" });
    await waitFor(() => expect(btn).not.toBeDisabled());
    btn.click();

    // The button flips and the Original overlay appears over the edited preview,
    // clipped to the left half by default (divider at 50%), with a draggable
    // divider. The drag math itself is covered by splitCompare.test.ts.
    await screen.findByRole("button", { name: "Hide split" });
    const original = await screen.findByAltText("original");
    expect((original as HTMLElement).style.clipPath).toBe("inset(0 50% 0 0)");
    expect(screen.getByLabelText("split divider")).toBeInTheDocument();
    // Split is its own mode: the plain Compare toggle is disabled while it's on.
    expect(screen.getByRole("button", { name: "Compare" })).toBeDisabled();

    // Toggling it off removes the overlay and re-enables Compare.
    screen.getByRole("button", { name: "Hide split" }).click();
    await waitFor(() =>
      expect(screen.queryByAltText("original")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Compare" })).not.toBeDisabled();
  });

  it("offers a Coverage overlay on a mosaic and toggles it", async () => {
    mockEditorQueries();
    // is_mosaic:true → the coverage overlay button is offered.
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0],
        b: [0, 0, 0, 0], is_mosaic: true });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));
    const covUrl = vi.spyOn(client.api, "editCoverageMapUrl");

    renderEditor();

    const btn = await screen.findByRole("button", { name: "Coverage" });
    await waitFor(() => expect(btn).not.toBeDisabled());
    btn.click();

    await waitFor(() =>
      expect(covUrl).toHaveBeenCalledWith("M_42", 3, expect.objectContaining({ ops: expect.any(Array) })));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Hide coverage" })).toBeInTheDocument());
    expect(screen.getByText("Coverage map")).toBeInTheDocument();
    // The colour heatmap carries a "fewer ↔ more frames" legend caption.
    await waitFor(() => expect(screen.getByText("more frames")).toBeInTheDocument());
    expect(screen.getByText("fewer")).toBeInTheDocument();
  });

  it("passes the recipe so the coverage overlay follows the crop geometry", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, CROP]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [{ uid: "c1", id: "geometry.crop", enabled: true,
              params: { x0: 0.1, y0: 0.1, x1: 0.9, y1: 0.9 } }],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0],
        b: [0, 0, 0, 0], is_mosaic: true });
    vi.spyOn(client.api, "trimSuggestion").mockResolvedValue({ is_mosaic: false, crop: null });
    const covUrl = vi.spyOn(client.api, "editCoverageMapUrl");
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    const btn = await screen.findByRole("button", { name: "Coverage" });
    await waitFor(() => expect(btn).not.toBeDisabled());
    btn.click();

    // The overlay now tracks the recipe's geometry, so the URL carries the recipe
    // (with the enabled crop op) — not a bare full-frame request — and the caption
    // no longer disclaims "shown for the uncropped frame".
    await waitFor(() =>
      expect(covUrl).toHaveBeenCalledWith("M_42", 3, expect.objectContaining({
        ops: expect.arrayContaining([expect.objectContaining({ id: "geometry.crop" })]),
      })));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Hide coverage" })).toBeInTheDocument());
    expect(screen.getByText("Coverage map")).toBeInTheDocument();
    expect(screen.queryByText(/uncropped frame/)).not.toBeInTheDocument();
  });

  it("flags an enabled crop with the kept-fraction caption and removes it in one click", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, CROP]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [{ uid: "c1", id: "geometry.crop", enabled: true,
              params: { x0: 0.1, y0: 0.1, x1: 0.9, y1: 0.9 } }],  // 80% × 80% = 64%
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    vi.spyOn(client.api, "trimSuggestion").mockResolvedValue({ is_mosaic: false, crop: null });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    expect(await screen.findByText(/Cropped view — showing 64% of the frame/))
      .toBeInTheDocument();
    // One click drops the crop → the caption clears (and there's no crop op left).
    screen.getByRole("button", { name: "Remove crop" }).click();
    await waitFor(() =>
      expect(screen.queryByText(/Cropped view/)).not.toBeInTheDocument());
  });

  it("hides the Coverage overlay button on a single-field stack", async () => {
    mockEditorQueries();  // histogram has no is_mosaic flag → single-field
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    await screen.findByText("Stretch");
    expect(screen.queryByRole("button", { name: "Coverage" })).not.toBeInTheDocument();
  });

  it("undoes the last op with Ctrl+Z", async () => {
    mockEditorQueries();
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    // Pipeline seeds one op ("Stretch"). Add a "Curves" op to create undo history.
    await screen.findByText("Stretch");
    fireEvent.click(screen.getByText("Add operation"));
    fireEvent.click(await screen.findByText("Curves"));
    await waitFor(() => expect(screen.getAllByText("Curves").length).toBeGreaterThan(0));

    // Ctrl+Z removes the just-added op.
    fireEvent.keyDown(window, { key: "z", ctrlKey: true });
    await waitFor(() => expect(screen.queryByText("Curves")).not.toBeInTheDocument());
    // The earlier op survives — undo popped only the last change.
    expect(screen.getByText("Stretch")).toBeInTheDocument();
  });

  it("nudges a first-timer with an empty pipeline toward Auto-process", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, CURVES]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({ ops: [], base_run_id: 3 });
    vi.spyOn(client.api, "previousRecipe").mockResolvedValue(
      { run_id: null, ops: [], count: 0 });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    const autoProcess = vi.spyOn(client.api, "autoProcess").mockResolvedValue({
      ops: [{ uid: "a1", id: "tone.stretch", enabled: true,
              params: { mode: "stf", target_bg: 0.2 } }], base_run_id: 3,
    });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    // The empty pipeline shows a guided nudge with its own Auto-process button.
    expect(await screen.findByText(/build a good starting recipe from/i))
      .toBeInTheDocument();
    // Clicking it (the in-panel one) kicks off auto-process.
    fireEvent.click(screen.getAllByRole("button", { name: /Auto-process/ })[1]);
    await waitFor(() => expect(autoProcess).toHaveBeenCalledWith("M_42", 3));
    // ...and a plain-language note explains what Auto did.
    expect(await screen.findByText("What Auto-process did")).toBeInTheDocument();
    expect(screen.getByText("Applied a natural stretch.")).toBeInTheDocument();
    // ...and names the data-driven value it chose (the STF sky level).
    expect(screen.getByText("Tuned to your data: sky level 0.2.")).toBeInTheDocument();

    // Editing the pipeline (removing the op) drops the note so it can't
    // misdescribe the current recipe.
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    await waitFor(() =>
      expect(screen.queryByText("What Auto-process did")).not.toBeInTheDocument());
  });

  it("offers to carry over a previous run's edit when this run has none", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, CURVES]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({ ops: [], base_run_id: 3 });
    vi.spyOn(client.api, "previousRecipe").mockResolvedValue({
      run_id: 2, count: 2,
      ops: [
        { uid: "p1", id: "tone.stretch", enabled: true, params: { stretch: 0.7 } },
        { uid: "p2", id: "tone.curves", enabled: true, params: { points: [[0, 0], [1, 1]] } },
      ],
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    const fetchMock = vi.fn(async (_url?: string) => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    renderEditor();

    // The empty pipeline offers a one-click carry-over naming the step count.
    const carry = await screen.findByRole("button", { name: /Use my previous edit \(2\)/ });
    fireEvent.click(carry);

    // Both ops land in the working pipeline...
    expect(await screen.findByText("Stretch")).toBeInTheDocument();
    expect(screen.getByText("Curves")).toBeInTheDocument();
    // ...and a preview fetch fires carrying exactly those ops.
    await waitFor(() => {
      const applied = fetchMock.mock.calls.some((call) => {
        const q = new URL("http://x" + String(call[0])).searchParams.get("recipe");
        if (!q) return false;
        const decoded = JSON.parse(atob(q.replace(/-/g, "+").replace(/_/g, "/")));
        return decoded.ops.map((o: { id: string }) => o.id).join(",")
          === "tone.stretch,tone.curves";
      });
      expect(applied).toBe(true);
    });
    // The nudge (and its carry-over button) is gone now the pipeline is non-empty.
    expect(screen.queryByRole("button", { name: /Use my previous edit/ })).toBeNull();
  });

  it("flags a heavy op so the user knows the preview updates after a pause", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, CURVES, DECONVOLVE]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [{ uid: "d1", id: "detail.deconvolve", enabled: true, params: { psf_sigma: 1.5 } }],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    // The op row carries a "slower preview" badge...
    expect(await screen.findByText("slower preview")).toBeInTheDocument();
    // ...and selecting it explains why the live preview lags behind the sliders.
    fireEvent.click(screen.getByText("Deconvolution"));
    await waitFor(() =>
      expect(screen.getByText(/preview waits for a short/i)).toBeInTheDocument());
  });

  it("hides advanced ops behind 'More operations' in the Add menu", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, CURVES, DECONVOLVE]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({ ops: [], base_run_id: 3 });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    fireEvent.click(await screen.findByText("Add operation"));
    // The curated "Common" section is shown; the non-common Deconvolution op isn't.
    expect(await screen.findByText("Common")).toBeInTheDocument();
    expect(screen.getByText("Stretch")).toBeInTheDocument();
    expect(screen.queryByText("Deconvolution")).not.toBeInTheDocument();
    // Expanding "More operations" reveals the full grouped list including Deconvolution.
    fireEvent.click(screen.getByText("More operations"));
    expect(await screen.findByText("Deconvolution")).toBeInTheDocument();
    // The heavy op advertises its slow preview right in the menu, before it's added.
    expect(screen.getByText("slower preview")).toBeInTheDocument();
  });

  it("previews the recipe without the selected op via 'Without this op'", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, CURVES]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [
        { uid: "s1", id: "tone.stretch", enabled: true, params: { stretch: 0.5 } },
        { uid: "c1", id: "tone.curves", enabled: true, params: { points: [[0, 0], [1, 1]] } },
      ],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    // Select the Curves op, then toggle the per-op "without this op" compare.
    fireEvent.click(await screen.findByText("Curves"));
    const btn = await screen.findByRole("button", { name: "Without this op" });
    fireEvent.click(btn);

    // The overlay names the isolated op and the button flips to the active label.
    expect(await screen.findByText("Without: Curves")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Showing without" })).toBeInTheDocument();
  });

  it("applies data-driven defaults across the pipeline in one click", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, SHARPEN]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [{ uid: "sh1", id: "detail.sharpen", enabled: true, params: { radius: 2.0 } }],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    // The sharpen op's radius suggestion diverges from the current 2.0.
    vi.spyOn(client.api, "sharpenSuggestion").mockResolvedValue({ fwhm_px: 8, radius: 3.5 });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    // The toolbar surfaces the one-click "Use data defaults" action once a present
    // op diverges from its measured suggestion.
    const btn = await screen.findByRole("button", { name: /Use data defaults/ });
    fireEvent.click(btn);
    // After applying, nothing diverges any more, so the button disappears.
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /Use data defaults/ })).not.toBeInTheDocument());
  });

  it("seeds a built-in preset's sizes from the target's data on apply", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, SHARPEN]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({ ops: [], base_run_id: 3 });
    // A built-in preset carrying the generic default sharpen radius (2.0)...
    vi.spyOn(client.api, "listPresets").mockResolvedValue({
      builtin: [{
        id: "galaxy", label: "Galaxy", group: "Built-in",
        ops: [{ id: "detail.sharpen", enabled: true, params: { radius: 2.0 } }],
      }],
      user: [],
    });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    // ...and a data-driven sharpen radius that differs from the preset default.
    vi.spyOn(client.api, "sharpenSuggestion").mockResolvedValue({ fwhm_px: 8, radius: 3.5 });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    // Apply the built-in "Galaxy" preset (empty pipeline → no confirm).
    fireEvent.click(await screen.findByRole("button", { name: /Presets/ }));
    fireEvent.click(await screen.findByText("Galaxy"));

    // Select the added Sharpen op; its radius should have been seeded to the
    // measured 3.5, so the "From your data" button reads as already-applied.
    fireEvent.click(await screen.findByText("Sharpen"));
    const btn = await screen.findByLabelText("Set Radius (px) from your data");
    await waitFor(() => expect(btn).toBeDisabled());
    expect(btn).toHaveTextContent("✓");
  });

  it("prepends Coverage leveling when a built-in preset is applied on a mosaic", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, SHARPEN, LEVEL_COVERAGE]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({ ops: [], base_run_id: 3 });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({
      builtin: [{
        id: "galaxy", label: "Galaxy", group: "Built-in",
        ops: [{ id: "detail.sharpen", enabled: true, params: { radius: 2.0 } }],
      }],
      user: [],
    });
    // is_mosaic:true → applying a built-in preset should flatten the panels.
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0],
        b: [0, 0, 0, 0], is_mosaic: true });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    fireEvent.click(await screen.findByRole("button", { name: /Presets/ }));
    fireEvent.click(await screen.findByText("Galaxy"));

    // The pipeline now leads with a Coverage-leveling pass (added because the run
    // is a mosaic), ahead of the preset's own Sharpen op.
    expect(await screen.findByText("Coverage leveling")).toBeInTheDocument();
    expect(screen.getByText("Sharpen")).toBeInTheDocument();
  });

  it("offers 'From your image' black/white points on the Levels op", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, LEVELS]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [
        { uid: "s1", id: "tone.stretch", enabled: true, params: { stretch: 0.6 } },
        { uid: "lv1", id: "tone.levels", enabled: true, params: { black: 0, white: 1 } },
      ],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    // Data-driven points measured from the image entering the Levels op.
    vi.spyOn(client.api, "levelsSuggestion").mockResolvedValue({ black: 0.12, white: 0.85 });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    // Select the Levels op; its black-point suggestion diverges from the current 0.
    fireEvent.click(await screen.findByText("Levels"));
    const btn = await screen.findByLabelText("Set Black point from your data");
    // Each button names only its own point (black here), matching what it sets.
    expect(btn).toHaveTextContent("black 0.12");
    expect(btn).not.toHaveTextContent("white");
    const whiteBtn = await screen.findByLabelText("Set White point from your data");
    expect(whiteBtn).toHaveTextContent("white 0.85");
    fireEvent.click(btn);
    // After applying, the black point matches the suggestion, so the button reads
    // as already-applied (disabled + ✓).
    await waitFor(() => expect(btn).toBeDisabled());
    expect(btn).toHaveTextContent("✓");
  });

  it("sets both black and white points at once via 'Auto levels'", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, LEVELS]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [
        { uid: "s1", id: "tone.stretch", enabled: true, params: { stretch: 0.6 } },
        { uid: "lv1", id: "tone.levels", enabled: true, params: { black: 0, white: 1, gamma: 1 } },
      ],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    // Suggestion carries a midtone gamma lift too; Auto levels applies all three.
    vi.spyOn(client.api, "levelsSuggestion").mockResolvedValue(
      { black: 0.12, white: 0.85, gamma: 1.6, gamma_target: 0.25 });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    fireEvent.click(await screen.findByText("Levels"));
    // Wait for the data-driven suggestion to load — the per-param buttons render
    // (draining the pending renders so the header button node stays live).
    await screen.findByLabelText("Set Black point from your data");
    await screen.findByLabelText("Set White point from your data");
    // The gamma button names the goal it solves for (the target grey), not just
    // the bare number, so the provenance is visible.
    expect(screen.getByLabelText("Set Midtones (gamma) from your data"))
      .toHaveTextContent("~25% grey");
    // One click on the header "Auto levels" button applies black, white and gamma.
    fireEvent.click(screen.getByRole("button", { name: /Auto levels/ }));
    // All three per-param buttons now read as already-applied (disabled + ✓),
    // proving black, white *and* the midtone gamma were set together.
    await waitFor(() => {
      expect(screen.getByLabelText("Set Black point from your data")).toBeDisabled();
      expect(screen.getByLabelText("Set White point from your data")).toBeDisabled();
      expect(screen.getByLabelText("Set Midtones (gamma) from your data")).toBeDisabled();
    });
    expect(screen.getByLabelText("Set Black point from your data")).toHaveTextContent("✓");
    expect(screen.getByLabelText("Set White point from your data")).toHaveTextContent("✓");
    expect(screen.getByLabelText("Set Midtones (gamma) from your data")).toHaveTextContent("✓");
  });

  it("offers data-driven Strength + Black point on the asinh Stretch op", async () => {
    // A fuller Stretch op with the asinh strength/black sliders + the mode enum.
    const STRETCH_FULL: EditOp = {
      id: "tone.stretch", label: "Stretch", group: "tone", stage: "any",
      proxy_safe: true, is_stretch: true, help: "tone map",
      params: [
        { key: "mode", label: "Curve", type: "enum", group: "simple", default: "asinh",
          min: null, max: null, step: null, options: ["asinh", "stf"], help: null,
          depends_on: null },
        { key: "stretch", label: "Strength", type: "float", group: "simple", default: 0.5,
          min: 0, max: 1, step: 0.01, options: null, help: null, depends_on: "mode=asinh" },
        { key: "black", label: "Black point", type: "float", group: "simple", default: 0.35,
          min: 0, max: 1, step: 0.01, options: null, help: null, depends_on: "mode=asinh" },
      ],
    };
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH_FULL, LEVELS]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [
        { uid: "s1", id: "tone.stretch", enabled: true,
          params: { mode: "asinh", stretch: 0.5, black: 0.35 } },
      ],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    // Data-driven asinh values measured from the linear image entering the op.
    vi.spyOn(client.api, "stretchSuggestion").mockResolvedValue(
      { stretch: 0.8, black: 0.05, target_bg: 0.1 });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    fireEvent.click(await screen.findByText("Stretch"));
    // The Strength button names the goal it solves for (the target sky grey).
    const strengthBtn = await screen.findByLabelText("Set Strength from your data");
    expect(strengthBtn).toHaveTextContent("strength 0.8");
    expect(strengthBtn).toHaveTextContent("~10% grey");
    // The Black-point button names just its own value.
    const blackBtn = await screen.findByLabelText("Set Black point from your data");
    expect(blackBtn).toHaveTextContent("black 0.05");
    // One click on the header "Auto stretch" applies both strength and black, so
    // both per-param buttons read as already-applied (disabled + ✓). Use findBy so
    // the click waits for the header button's render rather than racing it.
    fireEvent.click(await screen.findByRole("button", { name: /Auto stretch/ }));
    await waitFor(() => {
      expect(screen.getByLabelText("Set Strength from your data")).toBeDisabled();
      expect(screen.getByLabelText("Set Black point from your data")).toBeDisabled();
    });
    expect(screen.getByLabelText("Set Strength from your data")).toHaveTextContent("✓");
    expect(screen.getByLabelText("Set Black point from your data")).toHaveTextContent("✓");
  });

  it("hides the Stretch suggestion when the op is in STF (auto) mode", async () => {
    const STRETCH_FULL: EditOp = {
      id: "tone.stretch", label: "Stretch", group: "tone", stage: "any",
      proxy_safe: true, is_stretch: true, help: "tone map",
      params: [
        { key: "mode", label: "Curve", type: "enum", group: "simple", default: "asinh",
          min: null, max: null, step: null, options: ["asinh", "stf"], help: null,
          depends_on: null },
        { key: "stretch", label: "Strength", type: "float", group: "simple", default: 0.5,
          min: 0, max: 1, step: 0.01, options: null, help: null, depends_on: "mode=asinh" },
        { key: "black", label: "Black point", type: "float", group: "simple", default: 0.35,
          min: 0, max: 1, step: 0.01, options: null, help: null, depends_on: "mode=asinh" },
      ],
    };
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH_FULL, LEVELS]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [
        { uid: "s1", id: "tone.stretch", enabled: true,
          params: { mode: "stf", stretch: 0.5, black: 0.35 } },
      ],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    const sug = vi.spyOn(client.api, "stretchSuggestion").mockResolvedValue(
      { stretch: 0.8, black: 0.05, target_bg: 0.1 });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    fireEvent.click(await screen.findByText("Stretch"));
    // In STF (auto) mode there's no manual strength/black to suggest, so neither the
    // header button nor the per-param buttons appear, and the endpoint isn't hit.
    await screen.findByText("Export full resolution");
    expect(screen.queryByRole("button", { name: /Auto stretch/ })).toBeNull();
    expect(screen.queryByLabelText("Set Strength from your data")).toBeNull();
    expect(sug).not.toHaveBeenCalled();
  });

  it("sets a gentle starting curve via the header 'Auto curve'", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, CURVES]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [
        { uid: "s1", id: "tone.stretch", enabled: true, params: { stretch: 0.6 } },
        { uid: "cv1", id: "tone.curves", enabled: true,
          params: { points: [[0, 0], [1, 1]] } },
      ],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    const SUGGESTED: [number, number][] = [[0, 0], [0.15, 0.2], [0.9, 0.9], [1, 1]];
    vi.spyOn(client.api, "curveSuggestion").mockResolvedValue(
      { points: SUGGESTED, target_bg: 0.25 });
    const fetchMock = vi.fn(async (_url?: string) => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    renderEditor();

    // Selecting the Curves op surfaces the data-driven "Auto curve" header button,
    // which names the grey it lifts the midtones toward (from the suggestion's
    // target_bg) rather than being an opaque "Auto curve".
    fireEvent.click(await screen.findByText("Curves"));
    const autoCurve = await screen.findByRole("button", { name: /Auto curve \(lifts to ~25% grey\)/ });
    fireEvent.click(autoCurve);

    // The suggested points reach the pipeline: a preview fetch fires with the
    // curve op carrying exactly the suggested points in the encoded recipe.
    await waitFor(() => {
      const applied = fetchMock.mock.calls.some((call) => {
        const q = new URL("http://x" + String(call[0])).searchParams.get("recipe");
        if (!q) return false;
        const decoded = JSON.parse(atob(q.replace(/-/g, "+").replace(/_/g, "/")));
        const cv = decoded.ops.find((o: { id: string }) => o.id === "tone.curves");
        return cv && JSON.stringify(cv.params.points) === JSON.stringify(SUGGESTED);
      });
      expect(applied).toBe(true);
    });

    // Once applied, the button dims to a "✓" so re-clicking a no-op isn't invited,
    // consistent with the rest of the data-driven family.
    await waitFor(() => {
      const done = screen.getByRole("button", { name: /Auto curve ✓/ });
      expect(done).toBeDisabled();
    });
  });

  it("shows the auto-contrast ghost curve + Bake, hides the header 'Auto curve', and bakes on click", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, CURVES]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [
        { uid: "s1", id: "tone.stretch", enabled: true, params: { stretch: 0.6 } },
        // Auto-contrast on, points still identity → the derived curve is applied at
        // render time and the widget should preview it as a ghost.
        { uid: "cv1", id: "tone.curves", enabled: true,
          params: { points: [[0, 0], [1, 1]], auto: true } },
      ],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    const SUGGESTED: [number, number][] = [[0, 0], [0.15, 0.2], [0.9, 0.9], [1, 1]];
    vi.spyOn(client.api, "curveSuggestion").mockResolvedValue(
      { points: SUGGESTED, target_bg: 0.25 });
    const fetchMock = vi.fn(async (_url?: string) => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    renderEditor();

    fireEvent.click(await screen.findByText("Curves"));
    // The ghost curve + its caption appear; the redundant header "Auto curve" button
    // is hidden while auto is engaged (Bake is the single control).
    expect(await screen.findByLabelText("auto contrast preview curve")).toBeInTheDocument();
    expect(screen.getByText(/Auto contrast is on/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Auto curve/ })).toBeNull();

    // Baking writes the derived points into the recipe and clears `auto`, so a
    // preview fetch fires with the curve carrying exactly the suggested points.
    fireEvent.click(screen.getByRole("button", { name: /Bake to edit/ }));
    await waitFor(() => {
      const applied = fetchMock.mock.calls.some((call) => {
        const q = new URL("http://x" + String(call[0])).searchParams.get("recipe");
        if (!q) return false;
        const decoded = JSON.parse(atob(q.replace(/-/g, "+").replace(/_/g, "/")));
        const cv = decoded.ops.find((o: { id: string }) => o.id === "tone.curves");
        return cv && JSON.stringify(cv.params.points) === JSON.stringify(SUGGESTED)
          && cv.params.auto === false;
      });
      expect(applied).toBe(true);
    });
    // Ghost is gone now that points are non-identity (auto no longer engaged).
    await waitFor(() =>
      expect(screen.queryByLabelText("auto contrast preview curve")).toBeNull());
  });

  it("resets an over-dragged Levels op to neutral via the header 'Reset points'", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, LEVELS]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [
        { uid: "lv1", id: "tone.levels", enabled: true,
          params: { black: 0.3, white: 0.6, gamma: 2.0 } },
      ],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    vi.spyOn(client.api, "levelsSuggestion").mockResolvedValue({ black: 0.12, white: 0.85 });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    fireEvent.click(await screen.findByText("Levels"));
    // With the points moved off identity the reset button is offered (enabled).
    const reset = await screen.findByRole("button", { name: "Reset points" });
    await waitFor(() => expect(reset).not.toBeDisabled());
    fireEvent.click(reset);
    // One click returns to neutral, so the button dims (nothing left to reset).
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Reset points" })).toBeDisabled());
  });

  it("shows black/white guide labels on the histogram when the Levels op is selected", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, LEVELS]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [
        { uid: "s1", id: "tone.stretch", enabled: true, params: { stretch: 0.6 } },
        { uid: "lv1", id: "tone.levels", enabled: true, params: { black: 0.1, white: 0.8 } },
      ],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    vi.spyOn(client.api, "levelsSuggestion").mockResolvedValue({ black: 0.12, white: 0.85 });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    // No Levels op selected yet → no guide caption under the histogram.
    await screen.findByText("Levels");
    expect(screen.queryByText(/mark your black/)).not.toBeInTheDocument();
    // Selecting the Levels op surfaces the B/W guide caption (the guide lines are
    // SVG; the caption is the user-visible proof the overlay is active).
    fireEvent.click(screen.getByText("Levels"));
    expect(await screen.findByText(/mark your black/)).toBeInTheDocument();
  });

  it("shows the curve-point guide caption when the Curves op is selected", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, CURVES]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [
        { uid: "s1", id: "tone.stretch", enabled: true, params: { stretch: 0.6 } },
        { uid: "cv1", id: "tone.curves", enabled: true,
          params: { points: [[0, 0], [0.3, 0.4], [1, 1]] } },
      ],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    // Not selected yet → no curve-guide caption.
    await screen.findByText("Curves");
    expect(screen.queryByText(/where your curve's points sit/)).not.toBeInTheDocument();
    // Selecting the Curves op surfaces the guide caption.
    fireEvent.click(screen.getByText("Curves"));
    expect(await screen.findByText(/where your curve's points sit/)).toBeInTheDocument();
  });

  it("previews the proposed crop then adds a Crop op on Apply", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, CROP]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [{ uid: "s1", id: "tone.stretch", enabled: true, params: { stretch: 0.6 } }],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    // A mosaic with a well-covered rectangle worth cropping to.
    vi.spyOn(client.api, "trimSuggestion").mockResolvedValue({
      is_mosaic: true, crop: { x0: 0.2, y0: 0.1, x1: 0.8, y1: 0.9 },
    });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    const btn = await screen.findByRole("button", { name: /Trim border/ });
    fireEvent.click(btn);
    // First click only previews: a dashed outline + a "Proposed crop" caption, and
    // no Crop op is committed yet.
    await waitFor(() =>
      expect(screen.getByText(/Proposed crop — keeps the central 60% × 80%/)).toBeInTheDocument());
    expect(screen.queryByText("Left")).not.toBeInTheDocument();
    // Apply commits the crop: it's inserted after the stretch and selected, so
    // "Crop" shows in both the pipeline row and the selected-op panel header...
    fireEvent.click(screen.getByRole("button", { name: /Apply crop/ }));
    await waitFor(() => expect(screen.getAllByText("Crop").length).toBeGreaterThan(1));
    // ...and its adjustable bounds panel is shown; the preview caption is gone.
    expect(screen.getByText("Left")).toBeInTheDocument();
    expect(screen.queryByText(/Proposed crop/)).not.toBeInTheDocument();
  });

  it("warns about a second enabled Stretch and disables the extra on click", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, SHARPEN]);
    // Two enabled Stretch ops — they compound and wash the image out.
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [
        { uid: "s1", id: "tone.stretch", enabled: true, params: { stretch: 0.5 } },
        { uid: "sh1", id: "detail.sharpen", enabled: true, params: { radius: 2 } },
        { uid: "s2", id: "tone.stretch", enabled: true, params: { stretch: 0.6 } },
      ],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    // The redundant-stretch advisory shows...
    expect(await screen.findByText(/More than one/)).toBeInTheDocument();
    // ...and clicking the fix disables the extra stretch, clearing the warning.
    fireEvent.click(screen.getByRole("button", { name: /Disable the extra stretch/ }));
    await waitFor(() =>
      expect(screen.queryByText(/More than one/)).not.toBeInTheDocument());
  });

  it("warns about a degenerate Levels op and resets its range on click", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, LEVELS]);
    // A Levels op with white below black — its range is empty (does nothing).
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [
        { uid: "s1", id: "tone.stretch", enabled: true, params: { stretch: 0.5 } },
        { uid: "lv1", id: "tone.levels", enabled: true, params: { black: 0.6, white: 0.4 } },
      ],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    // The empty-range advisory shows...
    expect(await screen.findByText(/white point at or below its black point/)).toBeInTheDocument();
    // ...and clicking the fix resets black/white, clearing the warning.
    fireEvent.click(screen.getByRole("button", { name: /Reset the black/ }));
    await waitFor(() =>
      expect(screen.queryByText(/white point at or below its black point/)).not.toBeInTheDocument());
  });

  it("shows the proposed crop over the coverage heatmap on a mosaic", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, CROP]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [{ uid: "s1", id: "tone.stretch", enabled: true, params: { stretch: 0.6 } }],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    // A mosaic (is_mosaic:true) so both the Coverage overlay and Trim border show.
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0],
        b: [0, 0, 0, 0], is_mosaic: true });
    vi.spyOn(client.api, "trimSuggestion").mockResolvedValue({
      is_mosaic: true, crop: { x0: 0.2, y0: 0.1, x1: 0.8, y1: 0.9 },
    });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    // Coverage overlay starts hidden.
    expect(await screen.findByRole("button", { name: "Coverage" })).toBeInTheDocument();
    // Entering trim preview auto-enables the coverage heatmap (button flips to
    // "Hide coverage") and the caption notes the crop is drawn over it.
    fireEvent.click(await screen.findByRole("button", { name: /Trim border/ }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Hide coverage" })).toBeInTheDocument());
    expect(screen.getByText(/Proposed crop over coverage — keeps the central 60% × 80%/))
      .toBeInTheDocument();
    // Cancel restores the prior overlay state (coverage hidden again).
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Coverage" })).toBeInTheDocument());
  });

  it("hides the 'Trim border' button on a single-field stack (no crop)", async () => {
    mockEditorQueries();
    vi.spyOn(client.api, "trimSuggestion").mockResolvedValue({ is_mosaic: false, crop: null });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    await screen.findByText("Stretch");
    await waitFor(() => expect(client.api.trimSuggestion).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /Trim border/ })).not.toBeInTheDocument();
  });

  it("warns when the recipe clips highlights (from the live histogram)", async () => {
    mockEditorQueries();
    // A histogram with a big pile in the top bin (pure white) → highlight clip.
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 40], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    await screen.findByText("Stretch");
    expect(await screen.findByText(/Highlights are clipping/i)).toBeInTheDocument();
  });

  it("shows an error message when the preview render fails (not a blank panel)", async () => {
    mockEditorQueries();
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false, status: 500, json: async () => ({ detail: "boom while rendering" }),
    })));

    renderEditor();

    await waitFor(() => expect(screen.getByText(/Preview failed/)).toBeInTheDocument());
    expect(screen.getByText(/boom while rendering/)).toBeInTheDocument();
  });

  it("warns that Coverage leveling is a no-op on a single-field (non-mosaic) stack", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, LEVEL_COVERAGE]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [{ uid: "lc1", id: "background.level_coverage", enabled: true, params: { object_sigma: 2 } }],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    // is_mosaic:false → the run has uniform coverage, so the op does nothing.
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0],
        b: [0, 0, 0, 0], is_mosaic: false });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    // Selecting the op surfaces the "no effect on a single-field image" note.
    fireEvent.click(await screen.findByText("Coverage leveling"));
    expect(await screen.findByText(/No effect on this stack/i)).toBeInTheDocument();
  });

  it("does not warn about Coverage leveling on a mosaic stack", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, LEVEL_COVERAGE]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [{ uid: "lc1", id: "background.level_coverage", enabled: true, params: { object_sigma: 2 } }],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    // is_mosaic:true → the op is meaningful, so no no-op warning.
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0],
        b: [0, 0, 0, 0], is_mosaic: true });
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true, blob: async () => new Blob([new Uint8Array([1])], { type: "image/png" }),
    })));

    renderEditor();

    fireEvent.click(await screen.findByText("Coverage leveling"));
    // The op panel opens (help shows in both the row and the panel), the
    // histogram resolves with is_mosaic:true, and the no-op note must not appear.
    await waitFor(() =>
      expect(screen.getAllByText(/Equalize sky across mosaic panels/i).length).toBeGreaterThan(1));
    await waitFor(() => expect(client.api.getHistogram).toHaveBeenCalled());
    expect(screen.queryByText(/No effect on this stack/i)).not.toBeInTheDocument();
  });
});

describe("editPreviewUrl", () => {
  it("encodes the recipe as a decodable base64url query param", () => {
    const recipe: client.Recipe = {
      ops: [{ uid: "a", id: "tone.stretch", enabled: true, params: { stretch: 0.7 } }],
      base_run_id: 5,
    };
    const url = client.api.editPreviewUrl("M_42", 5, recipe);
    const q = new URL("http://x" + url).searchParams.get("recipe")!;
    const json = atob(q.replace(/-/g, "+").replace(/_/g, "/"));
    const decoded = JSON.parse(json);
    expect(decoded.ops[0].id).toBe("tone.stretch");
    expect(decoded.ops[0].params.stretch).toBe(0.7);
  });
});
