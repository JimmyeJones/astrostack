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

const LEVEL_COVERAGE: EditOp = {
  id: "background.level_coverage", label: "Coverage leveling", group: "background",
  stage: "linear", proxy_safe: true, is_stretch: false,
  help: "Equalize sky across mosaic panels with different frame coverage.",
  params: [{ key: "object_sigma", label: "Object σ", type: "float", group: "advanced",
             default: 2.0, min: 1, max: 5, step: 0.1, options: null, help: null,
             depends_on: null }],
};

function renderEditor() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/targets/M_42/edit/3"]}>
          <Routes>
            <Route path="/targets/:safe/edit/:runId" element={<EditorView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
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

    // No star op is selected, so the overlay uses the endpoint default (size undefined).
    await waitFor(() => expect(maskUrl).toHaveBeenCalledWith("M_42", 3, undefined));
    // The overlay label switches to "Star mask" and the button flips to "Hide mask".
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Hide mask" })).toBeInTheDocument());
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
