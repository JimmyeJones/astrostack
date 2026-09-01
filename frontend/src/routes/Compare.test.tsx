import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CompareView, parseRef, compareHref, noiseComparison, panelComparison,
  nightsComparison, compareDateLabel,
} from "./Compare";
import * as client from "../api/client";
import type { GalleryItem } from "../api/client";

function item(run_id: number, safe: string, target_name = safe): GalleryItem {
  return {
    safe, target_name, run_id, output_basename: `out${run_id}`,
    timestamp_utc: "2026-05-02T00:00:00Z", n_frames_used: 5, canvas_w: 100, canvas_h: 80,
    total_exposure_s: 300, has_preview: true, has_fits: true, has_tiff: false,
    preview_url: `/p/${safe}/${run_id}`, options: {},
  };
}

function renderCompare(qs: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[`/compare${qs}`]}>
          <Routes>
            <Route path="/compare" element={<CompareView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("parseRef", () => {
  it("parses a safe:run_id reference", () => {
    expect(parseRef("M_42:3")).toEqual({ safe: "M_42", run_id: 3 });
  });
  it("splits on the last colon so a safe key could (defensively) contain one", () => {
    expect(parseRef("a:b:7")).toEqual({ safe: "a:b", run_id: 7 });
  });
  it("rejects malformed or missing references", () => {
    expect(parseRef(null)).toBeNull();
    expect(parseRef("")).toBeNull();
    expect(parseRef("M_42")).toBeNull();
    expect(parseRef(":3")).toBeNull();
    expect(parseRef("M_42:x")).toBeNull();
  });
});

describe("compareHref", () => {
  it("builds a bookmarkable compare URL for two items", () => {
    expect(compareHref(item(3, "M_42"), item(7, "NGC_7000"))).toBe(
      "/compare?a=M_42:3&b=NGC_7000:7",
    );
  });
});

describe("compareDateLabel", () => {
  it("dates a picture by when its subs were SHOT, not when the stack ran", () => {
    // The page's question is "did it get better?", and the usual answer is "it
    // has more nights in it" — which the processing stamp cannot show.
    const it2 = item(3, "M_42");
    it2.capture_night_start = "2024-11-15";
    it2.capture_night_end = "2024-11-18";
    it2.capture_nights = 4;
    const out = compareDateLabel(it2);
    expect(out).toContain("Shot");
    expect(out).toContain("4 nights");
    expect(out).toContain("2024");
    expect(out).not.toContain("2026");
  });

  it("falls back to a LABELLED processing date for an older run", () => {
    // Never a bare date: a bare one reads as "the night I took this".
    // Locale-dependent day/month order, but the label and year are fixed.
    const out = compareDateLabel(item(3, "M_42"));
    expect(out).toMatch(/^Stacked /);
    expect(out).toContain("2026");
  });

  it("returns an empty string when neither date is usable", () => {
    const broken = item(3, "M_42");
    broken.timestamp_utc = "not-a-date";
    expect(compareDateLabel(broken)).toBe("");
  });
});

describe("nightsComparison", () => {
  const withNights = (run_id: number, nights: number | null, safe = "M_42") => {
    const g = item(run_id, safe);
    g.capture_nights = nights;
    return g;
  };

  it("names the deeper stack and both counts", () => {
    expect(nightsComparison(withNights(1, 2), withNights(2, 4)))
      .toEqual({ winner: "B", more: 4, fewer: 2 });
    expect(nightsComparison(withNights(1, 5), withNights(2, 1)))
      .toEqual({ winner: "A", more: 5, fewer: 1 });
  });

  it("says nothing when the two are equally deep", () => {
    expect(nightsComparison(withNights(1, 3), withNights(2, 3))).toBeNull();
  });

  it("says nothing when a run never recorded its night count", () => {
    expect(nightsComparison(withNights(1, null), withNights(2, 4))).toBeNull();
    expect(nightsComparison(item(1, "M_42"), withNights(2, 4))).toBeNull();
  });

  it("never compares the depth of two different targets", () => {
    // "M 42 has more nights than NGC 7000" compares nothing at all.
    expect(nightsComparison(withNights(1, 2), withNights(2, 4, "NGC_7000")))
      .toBeNull();
  });
});

describe("noiseComparison", () => {
  const withNoise = (run_id: number, sigma: number | null, safe = "M_42") => {
    const it = item(run_id, safe);
    it.noise_sigma = sigma;
    return it;
  };
  it("reports which stack is cleaner and by how much", () => {
    // A=0.04, B=0.05 → A is (1 - 0.04/0.05) = 20% lower.
    expect(noiseComparison(withNoise(1, 0.04), withNoise(2, 0.05)))
      .toEqual({ winner: "A", loser: "B", pct: 20, sameTarget: true });
    expect(noiseComparison(withNoise(1, 0.05), withNoise(2, 0.04)))
      .toEqual({ winner: "B", loser: "A", pct: 20, sameTarget: true });
  });
  it("returns null when a σ is missing, non-positive, or equal", () => {
    expect(noiseComparison(withNoise(1, null), withNoise(2, 0.05))).toBeNull();
    expect(noiseComparison(withNoise(1, 0.05), withNoise(2, 0.05))).toBeNull();
    expect(noiseComparison(withNoise(1, 0), withNoise(2, 0.05))).toBeNull();
  });
  it("flags a cross-target comparison, so the caller can drop the verdict", () => {
    // Normalising for gain/exposure makes σ comparable between two stacks of the
    // same field — not between two different objects, where the figure is mostly
    // about how bright and busy that patch of sky is. The number still stands;
    // "the cleaner stack" does not.
    const v = noiseComparison(withNoise(1, 0.05), withNoise(2, 0.04, "NGC_7000"));
    expect(v).toEqual({ winner: "B", loser: "A", pct: 20, sameTarget: false });
  });
});

describe("panelComparison", () => {
  const withSeams = (run_id: number, verdict: string | null) => {
    const it = item(run_id, "M_42");
    it.seam_verdict = verdict;
    return it;
  };
  it("names which mosaic's panels evened out when the two verdicts differ", () => {
    expect(panelComparison(withSeams(1, "flat"), withSeams(2, "check")))
      .toEqual({ winner: "A", loser: "B" });
    expect(panelComparison(withSeams(1, "check"), withSeams(2, "flat")))
      .toEqual({ winner: "B", loser: "A" });
  });
  it("stays silent when the verdicts agree — the two chips already say it", () => {
    expect(panelComparison(withSeams(1, "flat"), withSeams(2, "flat"))).toBeNull();
    expect(panelComparison(withSeams(1, "check"), withSeams(2, "check"))).toBeNull();
  });
  it("stays silent unless both sides carry a verdict", () => {
    // A single-field stack, a pre-v0.233 run, or the deliberately silent middle
    // band all serve null — there is nothing to weigh against.
    expect(panelComparison(withSeams(1, null), withSeams(2, "flat"))).toBeNull();
    expect(panelComparison(withSeams(1, "flat"), withSeams(2, null))).toBeNull();
  });
  it("stays silent for a verdict word it doesn't know", () => {
    // Same rule as the chip: a future third verdict must not make an older
    // frontend guess which way it points.
    expect(panelComparison(withSeams(1, "flat"), withSeams(2, "sort-of"))).toBeNull();
  });
});

describe("CompareView", () => {
  it("prompts to pick two stacks when refs are missing", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [] });
    renderCompare("");
    expect(await screen.findByText(/Pick two stacks to compare/)).toBeInTheDocument();
  });

  it("renders both stacks side by side", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [item(3, "M_42", "Orion"), item(7, "NGC_7000", "Pelican")],
    });
    renderCompare("?a=M_42:3&b=NGC_7000:7");
    await waitFor(() => expect(screen.getByText("Orion")).toBeInTheDocument());
    expect(screen.getByText("Pelican")).toBeInTheDocument();
    // Both A and B tags present.
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
  });

  it("gives each side's target name a line of its own, so the badges can't squeeze it", async () => {
    // Same squeeze the Gallery card had, and it matters more here: on a phone
    // the two cards stack full-width and this name is the only thing saying
    // which object you are looking at. It shared a no-wrap row with a
    // `flexShrink: 0` badge group, so the name absorbed all of the squeeze.
    // Pinned structurally (jsdom can't measure): the name's parent now holds the
    // card's other lines — the dated provenance line — instead of being a row
    // that held only the name and the badges.
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [
        item(3, "M_42", "Sample: Orion Nebula (M42)"),
        item(7, "NGC_7000", "North America Nebula"),
      ],
    });
    renderCompare("?a=M_42:3&b=NGC_7000:7");

    const name = await screen.findByText("Sample: Orion Nebula (M42)");
    expect(name.parentElement).toContainElement(screen.getAllByText(/^Stacked /)[0]);
    // Nothing removed to make room — the frame-count badge still renders.
    expect(screen.getAllByText("5 frames")).toHaveLength(2);
  });

  it("shows each mosaic's panel-flatness verdict, the third axis of \"did it get better?\"", async () => {
    // Noise and star size are already comparable here; panel flatness is the one
    // a mosaic shooter can't judge by eye from two thumbnails.
    const a = item(3, "M_42", "Orion");
    const b = item(7, "M_42", "OrionV2");
    a.seam_verdict = "check";
    b.seam_verdict = "flat";
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [a, b] });
    renderCompare("?a=M_42:3&b=M_42:7");
    await waitFor(() => expect(screen.getByText("Panels: check")).toBeInTheDocument());
    expect(screen.getByText("Panels even")).toBeInTheDocument();
    // ...and the page says which is which out loud, in the same voice it uses
    // for noise, rather than leaving two chips to be decoded.
    expect(screen.getByText(/mosaic panels evened out/)).toBeInTheDocument();
  });

  it("says nothing about panels when both mosaics landed on the same verdict", async () => {
    const a = item(3, "M_42", "Orion");
    const b = item(7, "M_42", "OrionV2");
    a.seam_verdict = "flat";
    b.seam_verdict = "flat";
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [a, b] });
    renderCompare("?a=M_42:3&b=M_42:7");
    // Both chips still render; the sentence would only repeat them.
    await waitFor(() => expect(screen.getAllByText("Panels even")).toHaveLength(2));
    expect(screen.queryByText(/mosaic panels evened out/)).not.toBeInTheDocument();
  });

  it("says out loud which stack has more nights in it", async () => {
    // The usual honest answer to "did it get better?" — and the one fact the
    // two thumbnails, the frame counts and the noise figure can't supply.
    const a = item(3, "M_42", "Orion");
    const b = item(7, "M_42", "OrionV2");
    a.capture_night_start = "2024-11-15";
    a.capture_night_end = "2024-11-16";
    a.capture_nights = 2;
    b.capture_night_start = "2024-11-15";
    b.capture_night_end = "2024-11-19";
    b.capture_nights = 4;
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [a, b] });
    renderCompare("?a=M_42:3&b=M_42:7");
    await waitFor(() =>
      expect(screen.getByText(/is made of subs from/)).toBeInTheDocument());
    // ...and each side is dated by when it was shot, labelled, not by when the
    // stack happened to run.
    expect(screen.getAllByText(/Shot over 4 nights/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Shot over 2 nights/).length).toBeGreaterThan(0);
  });

  it("says nothing about depth when the runs never recorded their nights", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [item(3, "M_42", "Orion"), item(7, "M_42", "OrionV2")],
    });
    renderCompare("?a=M_42:3&b=M_42:7");
    await waitFor(() => expect(screen.getByText("Orion")).toBeInTheDocument());
    expect(screen.queryByText(/is made of subs from/)).not.toBeInTheDocument();
    // The date is still labelled rather than bare, so it can't read as a
    // capture date on a re-stack of a back catalogue.
    expect(screen.getAllByText(/^Stacked /).length).toBe(2);
  });

  it("shows no panel chip when neither stack is a mosaic", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({
      items: [item(3, "M_42", "Orion"), item(7, "M_42", "OrionV2")],
    });
    renderCompare("?a=M_42:3&b=M_42:7");
    await waitFor(() => expect(screen.getByText("Orion")).toBeInTheDocument());
    expect(screen.queryByText(/Panels/)).not.toBeInTheDocument();
  });

  it("badges each stack's combine method", async () => {
    const a = item(3, "M_42", "Orion");
    const b = item(7, "M_42", "OrionV2");
    a.options = { sigma_clip: true, sigma_kappa: 3 };
    b.options = { min_max_reject: true };
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [a, b] });
    renderCompare("?a=M_42:3&b=M_42:7");
    await waitFor(() => expect(screen.getByText("σ-clip κ3")).toBeInTheDocument());
    expect(screen.getByText("min-max")).toBeInTheDocument();
  });

  it("shows a which-is-cleaner verdict when both stacks carry a noise σ", async () => {
    const a = item(3, "M_42", "Orion");
    const b = item(7, "M_42", "OrionV2");
    a.noise_sigma = 0.05;
    b.noise_sigma = 0.04; // B is 20% lower.
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [a, b] });
    renderCompare("?a=M_42:3&b=M_42:7");
    await waitFor(() => expect(screen.getByText(/20% lower/)).toBeInTheDocument());
    expect(screen.getByText(/it's the cleaner stack/)).toBeInTheDocument();
  });

  it("never calls one stack cleaner when the two are different objects", async () => {
    // The Gallery lets you select any two pictures, so this comparison is easy
    // to land on by accident — and a darker, emptier field reads quieter than a
    // bright nebula however well either was stacked. Keep the measurement, name
    // both objects, drop the verdict.
    const a = item(3, "M_42", "Orion");
    const b = item(7, "NGC_7000", "North America");
    a.noise_sigma = 0.05;
    b.noise_sigma = 0.04;
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [a, b] });
    renderCompare("?a=M_42:3&b=NGC_7000:7");
    await waitFor(() => expect(screen.getByTestId("noise-verdict")).toBeInTheDocument());
    const line = screen.getByTestId("noise-verdict").textContent ?? "";
    expect(line).toContain("20% lower");
    expect(line).not.toContain("cleaner stack");
    expect(line).toContain("two different objects");
    // Both objects are named in the sentence, so the reader can see why.
    expect(line).toContain("Orion");
    expect(line).toContain("North America");
  });

  it("offers a Split mode that overlays A over B under one draggable divider", async () => {
    const a = item(3, "M_42", "Orion");
    const b = item(7, "M_42", "OrionV2");
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [a, b] });
    renderCompare("?a=M_42:3&b=M_42:7");
    // Switch to Split mode.
    await waitFor(() => expect(screen.getByText("Split")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Split"));
    // Both stacks are rendered as overlaid images in one frame (A over B).
    await waitFor(() => expect(screen.getByAltText("A: out3")).toBeInTheDocument());
    expect(screen.getByAltText("B: out7")).toBeInTheDocument();
    // Plain-language drag hint naming both stacks.
    expect(screen.getByText(/Drag the divider/)).toBeInTheDocument();
  });

  it("shows each side's provenance strip in Split mode, so A/B isn't ambiguous", async () => {
    const a = item(3, "M_42", "Orion");
    const b = item(7, "M_42", "OrionV2");
    a.n_frames_used = 412;
    b.n_frames_used = 690;
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [a, b] });
    renderCompare("?a=M_42:3&b=M_42:7");
    await waitFor(() => expect(screen.getByText("Split")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Split"));
    // The A and B provenance columns each name their stack + frame count.
    const sideA = await screen.findByTestId("ab-side-A");
    const sideB = screen.getByTestId("ab-side-B");
    expect(sideA).toHaveTextContent("out3");
    expect(sideA).toHaveTextContent("412 frames");
    expect(sideB).toHaveTextContent("out7");
    expect(sideB).toHaveTextContent("690 frames");
  });

  it("shows the provenance strip in Blink mode too", async () => {
    const a = item(3, "M_42", "Orion");
    const b = item(7, "M_42", "OrionV2");
    a.n_frames_used = 412;
    b.n_frames_used = 690;
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [a, b] });
    renderCompare("?a=M_42:3&b=M_42:7");
    await waitFor(() => expect(screen.getByText("Blink")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Blink"));
    const sideA = await screen.findByTestId("ab-side-A");
    expect(sideA).toHaveTextContent("412 frames");
    expect(screen.getByTestId("ab-side-B")).toHaveTextContent("690 frames");
  });

  it("Split falls back with guidance when a stack has no preview", async () => {
    const a = item(3, "M_42", "Orion");
    const b = item(7, "M_42", "OrionV2");
    b.has_preview = false;
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [a, b] });
    renderCompare("?a=M_42:3&b=M_42:7");
    await waitFor(() => expect(screen.getByText("Split")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Split"));
    expect(await screen.findByText(/Split needs a preview image for both stacks/)).toBeInTheDocument();
  });

  it("warns when a referenced stack was deleted", async () => {
    vi.spyOn(client.api, "getGallery").mockResolvedValue({ items: [item(3, "M_42")] });
    renderCompare("?a=M_42:3&b=M_42:999");
    expect(await screen.findByText(/no longer exists/)).toBeInTheDocument();
  });
});
