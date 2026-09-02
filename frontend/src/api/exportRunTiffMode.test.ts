import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";

/** The editor's "Export as new image" no longer asks Linear vs Auto-stretched,
 * because an editor export's TIFF is written from the recipe's already
 * tone-mapped result and the mode is never read (`_write_tiff` returns in its
 * `already_display` branch first). The field still has to go out on the wire:
 * the endpoint has always taken it, and an older backend deployed against a
 * newer frontend must keep receiving the value it has always received. */
describe("editor export — tiff_mode stays on the wire", () => {
  afterEach(() => vi.restoreAllMocks());

  function mockFetch() {
    const fetchMock = vi.fn(
      async (_path: string, _init?: RequestInit) =>
        new Response(JSON.stringify({ job_id: "j1" }),
          { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("posts the linear default when the caller doesn't name a mode", async () => {
    const fetchMock = mockFetch();
    await api.exportRun("M_31", 5, { ops: [] }, "M_31_edit");
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/targets/M_31/stack-runs/5/editor/export");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      recipe: { ops: [] }, output_name: "M_31_edit", tiff_mode: "linear",
    });
  });

  it("is the same mode the saved-edit export has always hardcoded, so the two "
    + "paths cannot disagree about what an export writes", async () => {
    const fetchMock = mockFetch();
    await api.exportRun("M_31", 5, { ops: [] }, "a");
    await api.exportSavedEdit("M_31", 5, "b");
    const sent = fetchMock.mock.calls.map(
      ([, init]) => JSON.parse(init?.body as string).tiff_mode);
    expect(sent).toEqual(["linear", "linear"]);
  });

  it("still passes an explicit mode through, so the endpoint's contract is "
    + "unchanged for any other caller", async () => {
    const fetchMock = mockFetch();
    await api.exportRun("M_31", 5, { ops: [] }, "a", "autostretch");
    expect(JSON.parse(fetchMock.mock.calls[0][1]?.body as string).tiff_mode)
      .toBe("autostretch");
  });
});
