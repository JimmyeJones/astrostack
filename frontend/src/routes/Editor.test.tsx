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
  proxy_safe: false, is_stretch: false, help: "heavy",
  params: [{ key: "psf_sigma", label: "PSF σ (px)", type: "float", group: "simple",
             default: 1.5, min: 0.5, max: 5, step: 0.1, options: null, help: null,
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

    await waitFor(() => expect(maskUrl).toHaveBeenCalledWith("M_42", 3));
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
      ops: [{ uid: "a1", id: "tone.stretch", enabled: true, params: {} }], base_run_id: 3,
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
  });

  it("flags a preview-only (export-only) op so the user knows why the preview doesn't change", async () => {
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

    // The op row carries an "export only" badge...
    expect(await screen.findByText("export only")).toBeInTheDocument();
    // ...and selecting it explains why the live preview stays unchanged.
    fireEvent.click(screen.getByText("Deconvolution"));
    await waitFor(() =>
      expect(screen.getByText(/live preview doesn't show this effect/i)).toBeInTheDocument());
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

  it("shows an error message when the preview render fails (not a blank panel)", async () => {
    mockEditorQueries();
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false, status: 500, json: async () => ({ detail: "boom while rendering" }),
    })));

    renderEditor();

    await waitFor(() => expect(screen.getByText(/Preview failed/)).toBeInTheDocument());
    expect(screen.getByText(/boom while rendering/)).toBeInTheDocument();
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
