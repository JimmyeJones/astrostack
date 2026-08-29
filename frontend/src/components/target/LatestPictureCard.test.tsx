import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LatestPictureCard, latestPictureCaption } from "./LatestPictureCard";
import * as client from "../../api/client";
import type { StackRun } from "../../api/client";

function mkRun(over: Partial<StackRun> = {}): StackRun {
  return {
    id: 7, timestamp_utc: "2026-08-14T22:10:00Z", output_basename: "master",
    n_frames_used: 128, canvas_w: 1920, canvas_h: 1080,
    coverage_min: 128, coverage_max: 128, has_fits: true, has_tiff: false,
    has_preview: true, notes: null, total_exposure_s: 7560, ...over,
  };
}

/** Render and hand back the QueryClient, for tests that assert on invalidation. */
function renderCardWithClient(run: StackRun | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  renderWith(qc, run);
  return qc;
}

function renderCard(run: StackRun | null) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return renderWith(qc, run);
}

function renderWith(qc: QueryClient, run: StackRun | null) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <LatestPictureCard safe="M_42" name="M42" run={run} />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("latestPictureCaption", () => {
  it("says when it was stacked, out of how many subs, and how much light", () => {
    const cap = latestPictureCaption(mkRun());
    expect(cap).toMatch(/^Stacked /);
    expect(cap).toContain("128 frames");
    expect(cap).toContain("of light");
  });

  it("says 'frame' for a single-frame stack", () => {
    expect(latestPictureCaption(mkRun({ n_frames_used: 1 }))).toContain("1 frame ");
  });

  it("omits the integration when the run never recorded one", () => {
    expect(latestPictureCaption(mkRun({ total_exposure_s: null })))
      .not.toContain("of light");
  });

  it("names the month instead of numbering it", () => {
    // Found by dogfooding: the hero read "Stacked 8/16/2026" directly above the
    // Nights card's "15 Nov 2024", and half the world reads 8/16 as the 8th of
    // month 16. Every picture-dating surface now goes through formatStampDate.
    const cap = latestPictureCaption(mkRun({ timestamp_utc: "2026-08-16T12:00:00Z" }));
    expect(cap).toMatch(/Stacked .*2026/);
    expect(cap).toMatch(/Stacked [^·]*[A-Za-z]{3}/);
    expect(cap).not.toMatch(/\d{1,2}\/\d{1,2}\//);
  });

  it("omits an unparseable timestamp rather than printing 'Invalid Date'", () => {
    const cap = latestPictureCaption(mkRun({ timestamp_utc: "not-a-date" }));
    expect(cap).not.toMatch(/Stacked/);
    expect(cap).toContain("128 frames");
  });
});

describe("LatestPictureCard", () => {
  it("shows the finished picture with a route into the editor", async () => {
    renderCard(mkRun());
    const img = await screen.findByAltText("Latest stacked picture of M42");
    expect(img.getAttribute("src")).toContain("/stack-runs/7/preview");
    expect(screen.getByRole("link", { name: "Edit this picture" }))
      .toHaveAttribute("href", "/targets/M_42/edit/7");
    expect(screen.getByRole("link", { name: "All versions" }))
      .toHaveAttribute("href", "/targets/M_42/history");
  });

  it("renders nothing at all before there is a finished picture", () => {
    renderCard(null);
    expect(screen.queryByTestId("latest-picture")).not.toBeInTheDocument();
  });

  it("renders nothing for a run that produced no preview", () => {
    renderCard(mkRun({ has_preview: false }));
    expect(screen.queryByTestId("latest-picture")).not.toBeInTheDocument();
  });

  it("opens the same zoomable viewer the rest of the app uses when clicked", async () => {
    renderCard(mkRun());
    const img = await screen.findByAltText("Latest stacked picture of M42");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(img.parentElement!);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });
});

// The picture on this card is the run's baked preview. When the user saved an
// edit and never exported it, that preview is NOT the picture they made — so the
// card has to say so rather than quietly present the auto-stretch as theirs.
describe("LatestPictureCard — a saved edit that was never exported", () => {
  it("says nothing on an ordinary run", () => {
    renderCard(mkRun());
    expect(screen.queryByTestId("unexported-edit")).not.toBeInTheDocument();
  });

  it("tells the user their edit isn't in this picture, and offers both ways out", () => {
    renderCard(mkRun({ unexported_edit: true }));
    const note = screen.getByTestId("unexported-edit");
    expect(note).toHaveTextContent(/never exported it/);
    expect(note).toHaveTextContent(/still the un-edited version/);
    expect(screen.getByRole("button", { name: "Finish my edit" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the editor" }))
      .toHaveAttribute("href", "/targets/M_42/edit/7");
  });

  it("finishes the edit in one click, without the browser handling the recipe", async () => {
    const spy = vi.spyOn(client.api, "exportSavedEdit")
      .mockResolvedValue({ job_id: "job-9" });
    vi.spyOn(client.api, "getJob").mockResolvedValue(
      { id: "job-9", state: "done" } as client.Job);
    renderCard(mkRun({ unexported_edit: true }));
    fireEvent.click(screen.getByRole("button", { name: "Finish my edit" }));
    await waitFor(() => expect(spy).toHaveBeenCalledWith("M_42", 7, "M_42_edit"));
  });

  it("refreshes the picture when the export lands, so the promise it made holds", async () => {
    vi.spyOn(client.api, "exportSavedEdit").mockResolvedValue({ job_id: "job-9" });
    const getJob = vi.spyOn(client.api, "getJob")
      .mockResolvedValue({ id: "job-9", state: "done" } as client.Job);
    const qc = renderCardWithClient(mkRun({ unexported_edit: true }));
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    fireEvent.click(screen.getByRole("button", { name: "Finish my edit" }));
    await waitFor(() => expect(getJob).toHaveBeenCalledWith("job-9"));
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["runs", "M_42"] }));
  });
});
