import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  LatestPictureCard, inThisPictureSentence, latestPictureCaption,
} from "./LatestPictureCard";
import * as client from "../../api/client";
import type { FieldObject, StackAnnotations, StackRun } from "../../api/client";

function obj(over: Partial<FieldObject> = {}): FieldObject {
  return {
    catalog_id: "M42", name: "Orion Nebula", type: "nebula",
    ra_deg: 83.8, dec_deg: -5.4, x_px: 960, y_px: 540, ...over,
  };
}

function annotations(over: Partial<StackAnnotations> = {}): StackAnnotations {
  return { width: 1920, height: 1080, objects: [obj()], scale_bar: null, ...over };
}

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

describe("inThisPictureSentence", () => {
  it("names the objects, preferring the friendly name over the catalog id", () => {
    expect(inThisPictureSentence([obj(), obj({ catalog_id: "NGC 1977", name: "" })]))
      .toBe("In this picture: Orion Nebula, NGC 1977");
  });

  it("caps a rich field at one line and counts the rest", () => {
    const many = Array.from({ length: 9 }, (_, i) =>
      obj({ catalog_id: `NGC ${i}`, name: "" }));
    const s = inThisPictureSentence(many);
    expect(s).toContain("NGC 5");   // the 6th, still shown
    expect(s).not.toContain("NGC 6");
    expect(s).toContain("and 3 more");
  });

  it("says nothing at all for an empty field", () => {
    expect(inThisPictureSentence([])).toBe("");
  });
});

// "What's in my picture?" — the named-object overlay used to exist only on the
// History page, which most beginners never open. These pin it to the Target
// page's picture card: opt-in, lazily fetched, and honest about the pictures its
// geometry can't be placed on.
describe("LatestPictureCard — object labels", () => {
  it("does not ask the backend what's in the picture until the user asks", async () => {
    const spy = vi.spyOn(client.api, "stackAnnotations")
      .mockResolvedValue(annotations());
    renderCard(mkRun());
    await screen.findByAltText("Latest stacked picture of M42");
    expect(spy).not.toHaveBeenCalled();
    expect(screen.queryByTestId("identify-readout")).not.toBeInTheDocument();
  });

  it("names what's in the picture once asked", async () => {
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue(annotations({
      objects: [obj(), obj({ catalog_id: "NGC 1977", name: "Running Man Nebula" })],
    }));
    renderCard(mkRun());
    fireEvent.click(screen.getByTestId("identify-toggle"));
    const readout = await screen.findByTestId("identify-readout");
    await waitFor(() => expect(readout)
      .toHaveTextContent("In this picture: Orion Nebula, Running Man Nebula"));
    expect(screen.getByTestId("identify-toggle")).toHaveTextContent("Hide labels");
  });

  it("says so plainly when nothing catalogued landed in the frame", async () => {
    vi.spyOn(client.api, "stackAnnotations")
      .mockResolvedValue(annotations({ objects: [] }));
    renderCard(mkRun());
    fireEvent.click(screen.getByTestId("identify-toggle"));
    await waitFor(() => expect(screen.getByTestId("identify-readout"))
      .toHaveTextContent(/No catalog objects landed/));
  });

  it("doesn't offer labels on a run with no FITS to read a WCS from", () => {
    renderCard(mkRun({ has_fits: false }));
    expect(screen.queryByTestId("identify-toggle")).not.toBeInTheDocument();
  });

  it("refuses to place labels on a picture a past save rotated North-up", async () => {
    const spy = vi.spyOn(client.api, "stackAnnotations")
      .mockResolvedValue(annotations());
    renderCard(mkRun({ preview_north_up_deg: 12.5 }));
    fireEvent.click(screen.getByTestId("identify-toggle"));
    await waitFor(() => expect(screen.getByTestId("identify-readout"))
      .toHaveTextContent(/saved rotated so North is up/));
    expect(spy).toHaveBeenCalled();  // still asked; just not drawn on this render
  });

  it("refuses to place labels on a processed picture whose geometry can't be reconciled", async () => {
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue(annotations());
    renderCard(mkRun({ preview_geometry_unknown: true }));
    fireEvent.click(screen.getByTestId("identify-toggle"));
    await waitFor(() => expect(screen.getByTestId("identify-readout"))
      .toHaveTextContent(/reshaped when it was processed/));
  });

  it("drops an object the auto-edit's border trim cropped out of the picture", async () => {
    // The stored preview of a processed mosaic is a crop of the canvas; the
    // object pixels are measured on the un-cropped grid. NGC 1977 sits in the
    // trimmed-away left edge, so it is no longer in the picture being labelled.
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue(annotations({
      objects: [
        obj({ x_px: 960, y_px: 540 }),
        obj({ catalog_id: "NGC 1977", name: "Running Man Nebula", x_px: 20, y_px: 540 }),
      ],
    }));
    renderCard(mkRun({ preview_crop: { x0: 0.25, y0: 0, x1: 1, y1: 1 } }));
    fireEvent.click(screen.getByTestId("identify-toggle"));
    const readout = await screen.findByTestId("identify-readout");
    await waitFor(() => expect(readout).toHaveTextContent("Orion Nebula"));
    expect(readout).not.toHaveTextContent("Running Man");
  });

  it("offers to save the picture with the names baked in, once they're shown", async () => {
    // The names are drawn in the browser, so they vanish the moment the picture
    // leaves the app. The offer appears where the labels are — not as another
    // item in the page's already-long Save/share menu.
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue(annotations());
    renderCard(mkRun());
    expect(screen.queryByTestId("save-labelled")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("identify-toggle"));
    const link = await screen.findByTestId("save-labelled");
    expect(link).toHaveAttribute(
      "href", "/api/targets/M_42/stack-runs/7/jpeg?label_objects=true");
  });

  it("doesn't offer the labelled save where the server would refuse it", async () => {
    // A picture a past save rotated North-up can't carry the pins at all — the
    // server hands back the plain file — so offering the save would be a link
    // that quietly does nothing.
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue(annotations());
    renderCard(mkRun({ preview_north_up_deg: 12.5 }));
    fireEvent.click(screen.getByTestId("identify-toggle"));
    await screen.findByTestId("identify-readout");
    expect(screen.queryByTestId("save-labelled")).not.toBeInTheDocument();
  });

  it("doesn't offer the labelled save when nothing landed in the frame", async () => {
    vi.spyOn(client.api, "stackAnnotations")
      .mockResolvedValue(annotations({ objects: [] }));
    renderCard(mkRun());
    fireEvent.click(screen.getByTestId("identify-toggle"));
    await waitFor(() => expect(screen.getByTestId("identify-readout"))
      .toHaveTextContent(/No catalog objects landed/));
    expect(screen.queryByTestId("save-labelled")).not.toBeInTheDocument();
  });

  it("says it couldn't work it out rather than showing an empty line", async () => {
    vi.spyOn(client.api, "stackAnnotations").mockRejectedValue(new Error("nope"));
    renderCard(mkRun());
    fireEvent.click(screen.getByTestId("identify-toggle"));
    await waitFor(() => expect(screen.getByTestId("identify-readout"))
      .toHaveTextContent(/Couldn’t work out/));
  });

  it("puts the labels away again", async () => {
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue(annotations());
    renderCard(mkRun());
    fireEvent.click(screen.getByTestId("identify-toggle"));
    await screen.findByTestId("identify-readout");
    fireEvent.click(screen.getByTestId("identify-toggle"));
    expect(screen.queryByTestId("identify-readout")).not.toBeInTheDocument();
    expect(screen.getByTestId("identify-toggle")).toHaveTextContent("What’s in it?");
  });
});

// The picture on this card is the run's baked preview. When the user saved an
// edit and never exported it, that preview is NOT the picture they made — so the
// card has to say so rather than quietly present the auto-stretch as theirs.
// "North up" used to be reachable only through History → Adjust → Save, which
// rewrites the stored preview on disk. These pin it as a *view*: nothing is
// written, it is off until asked for, and it is only offered where turning the
// picture would actually change it.
describe("LatestPictureCard — North up as a view", () => {
  const turned = () => annotations({ north_up_deg: 118.5 });

  afterEach(() => window.localStorage.clear());

  it("offers no turn until the picture is open, and none at all on a run with nothing to turn", async () => {
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue(annotations());
    renderCard(mkRun());
    // Not in the card's own header — the toggle belongs to the big view.
    expect(screen.queryByTestId("north-up-view")).not.toBeInTheDocument();
    fireEvent.click((await screen.findByAltText("Latest stacked picture of M42")).parentElement!);
    await screen.findByRole("dialog");
    // The run reports no correction, so a toggle here would visibly do nothing.
    await waitFor(() => expect(client.api.stackAnnotations).toHaveBeenCalled());
    expect(screen.queryByTestId("north-up-view")).not.toBeInTheDocument();
  });

  it("turns the picture on request and hands over what's on screen", async () => {
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue(turned());
    renderCard(mkRun());
    fireEvent.click((await screen.findByAltText("Latest stacked picture of M42")).parentElement!);
    const toggle = await screen.findByTestId("north-up-view");
    // Off by default: the saved orientation is the one the owner chose.
    const shown = () => screen.getByRole("dialog").querySelector("img")!;
    expect(shown()).toHaveAttribute("src", "/api/targets/M_42/stack-runs/7/preview");

    fireEvent.click(toggle);

    await waitFor(() => expect(shown())
      .toHaveAttribute("src", "/api/targets/M_42/stack-runs/7/preview?north_up=true"));
    // The downloads follow the view, so a picture you liked arrives that way…
    fireEvent.click(screen.getByLabelText("Download picture"));
    expect((await screen.findByText("Full-res PNG (native size)")).closest("a"))
      .toHaveAttribute("href", "/api/targets/M_42/stack-runs/7/full-res-png?north_up=true");
    expect(screen.getByText("JPEG (smaller — best for sharing)").closest("a"))
      .toHaveAttribute("href", "/api/targets/M_42/stack-runs/7/jpeg?north_up=true");
    // …except the raw data, which stays WCS-aligned.
    expect(screen.getByLabelText("Download raw data"))
      .toHaveAttribute("href", "/api/targets/M_42/stack-runs/7/fits");
  });

  it("remembers the choice for this viewer, and nothing on the run", async () => {
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue(turned());
    renderCard(mkRun());
    fireEvent.click((await screen.findByAltText("Latest stacked picture of M42")).parentElement!);
    fireEvent.click(await screen.findByTestId("north-up-view"));

    await waitFor(() => expect(window.localStorage.getItem("astrostack.northUpView"))
      .toBe("1"));
    // It is a viewing preference, so it must not have written to the picture.
    fireEvent.click(screen.getByTestId("north-up-view"));
    await waitFor(() => expect(window.localStorage.getItem("astrostack.northUpView"))
      .toBe("0"));
  });

  it("does not offer to turn a picture that was already saved turned", async () => {
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue(turned());
    renderCard(mkRun({ preview_north_up_deg: 118.5 }));
    fireEvent.click((await screen.findByAltText("Latest stacked picture of M42")).parentElement!);
    await screen.findByRole("dialog");
    await waitFor(() => expect(client.api.stackAnnotations).toHaveBeenCalled());
    expect(screen.queryByTestId("north-up-view")).not.toBeInTheDocument();
  });
});

// "See what stacking removed" has existed on the History run card since
// v0.299.0, where it tints a 180 px thumbnail — at which size a satellite trail
// is a couple of cyan pixels. These pin it on the surface where a beginner
// actually studies the picture: offered only where there is a map, off until
// asked for, captioned, and in register with the North-up *view*.
describe("LatestPictureCard — what stacking removed, full screen", () => {
  afterEach(() => window.localStorage.clear());

  const openBig = async () => {
    fireEvent.click((await screen.findByAltText("Latest stacked picture of M42")).parentElement!);
    return screen.findByRole("dialog");
  };

  it("offers nothing on a run that recorded no map", async () => {
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue(annotations());
    renderCard(mkRun());
    await openBig();
    expect(screen.queryByTestId("show-removed-view")).not.toBeInTheDocument();
    expect(screen.queryByTestId("lightbox-overlay")).not.toBeInTheDocument();
  });

  it("tints the picture on request, and names the marks with the run's own number", async () => {
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue(annotations());
    const info = vi.spyOn(client.api, "stackRunInfo")
      .mockResolvedValue({ rejection: { mode: "sigma-clip", fraction: 0.004 } } as never);
    renderCard(mkRun({ has_rejection_map: true }));
    await openBig();
    const toggle = await screen.findByTestId("show-removed-view");
    // Off by default — the picture is the point; the tint answers a question
    // the viewer has to ask. Nothing is fetched until they do.
    expect(screen.queryByTestId("lightbox-overlay")).not.toBeInTheDocument();
    expect(info).not.toHaveBeenCalled();

    fireEvent.click(toggle);

    expect(await screen.findByTestId("lightbox-overlay")).toHaveAttribute(
      "src", "/api/targets/M_42/stack-runs/7/rejection-overlay");
    expect(await screen.findByText(/about 0\.4% of your samples/)).toBeInTheDocument();
  });

  it("turns the tint with the picture, so the two can't slide apart", async () => {
    vi.spyOn(client.api, "stackAnnotations")
      .mockResolvedValue(annotations({ north_up_deg: 118.5 }));
    vi.spyOn(client.api, "stackRunInfo")
      .mockResolvedValue({ rejection: { mode: "sigma-clip", fraction: 0.004 } } as never);
    renderCard(mkRun({ has_rejection_map: true }));
    await openBig();
    fireEvent.click(await screen.findByTestId("show-removed-view"));
    expect(await screen.findByTestId("lightbox-overlay")).toHaveAttribute(
      "src", "/api/targets/M_42/stack-runs/7/rejection-overlay");

    fireEvent.click(await screen.findByTestId("north-up-view"));

    // The picture takes the on-the-fly turn — and so does the tint, through the
    // same remainder the server computes for the bytes underneath it.
    await waitFor(() => expect(screen.getByTestId("lightbox-overlay")).toHaveAttribute(
      "src", "/api/targets/M_42/stack-runs/7/rejection-overlay?north_up=true"));
    expect(screen.getByRole("dialog").querySelector("img")).toHaveAttribute(
      "src", "/api/targets/M_42/stack-runs/7/preview?north_up=true");
  });

  it("still says what the marks are when the run's fraction can't be read", async () => {
    vi.spyOn(client.api, "stackAnnotations").mockResolvedValue(annotations());
    vi.spyOn(client.api, "stackRunInfo").mockRejectedValue(new Error("nope"));
    renderCard(mkRun({ has_rejection_map: true }));
    await openBig();
    fireEvent.click(await screen.findByTestId("show-removed-view"));
    // The lead sentence never depends on the number — an uncaptioned cyan
    // speckle reads as damage.
    expect(await screen.findByText(/cyan marks are what stacking removed/))
      .toBeInTheDocument();
  });
});

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
