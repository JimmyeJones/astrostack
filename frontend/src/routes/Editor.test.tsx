import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
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

function renderEditor() {
  const qc = new QueryClient();
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

describe("EditorView", () => {
  it("loads the saved recipe and renders its operations", async () => {
    vi.spyOn(client.api, "editorOps").mockResolvedValue([STRETCH, CURVES]);
    vi.spyOn(client.api, "getRecipe").mockResolvedValue({
      ops: [{ uid: "x1", id: "tone.stretch", enabled: true, params: { stretch: 0.6 } }],
      base_run_id: 3,
    });
    vi.spyOn(client.api, "listPresets").mockResolvedValue({ builtin: [], user: [] });
    vi.spyOn(client.api, "getHistogram").mockResolvedValue(
      { bins: 4, edges: [0, 0.25, 0.5, 0.75], r: [1, 2, 3, 4], g: [0, 0, 0, 0], b: [0, 0, 0, 0] });

    renderEditor();

    await waitFor(() => expect(screen.getByText("Add operation")).toBeInTheDocument());
    // The saved stretch op shows in the pipeline list.
    expect(screen.getByText("Stretch")).toBeInTheDocument();
    expect(screen.getByText("Export as new image")).toBeInTheDocument();
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
