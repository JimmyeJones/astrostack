import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OneFrameVsStackCard } from "./OneFrameVsStackCard";
import * as client from "../api/client";

function renderCard(safe = "M_42", runId = 7) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <OneFrameVsStackCard safe={safe} runId={runId} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("OneFrameVsStackCard", () => {
  it("renders nothing when the reveal isn't available", async () => {
    vi.spyOn(client.api, "oneSubVsStack").mockResolvedValue({
      available: false, n_frames: null, sub_exposure_s: null, integration_s: null,
    });
    const { container } = renderCard();
    await waitFor(() => expect(client.api.oneSubVsStack).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });

  it("shows the caption and reveals the split comparison on click", async () => {
    vi.spyOn(client.api, "oneSubVsStack").mockResolvedValue({
      available: true, n_frames: 505, sub_exposure_s: 30, integration_s: 15150,
    });
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue(
      { ratio: 15.3, expected_verdict: "expected" });
    renderCard("M_42", 7);
    await waitFor(() =>
      expect(screen.getByText("One frame vs your stack")).toBeInTheDocument());
    // The caption is filled from the run's own provenance.
    expect(
      screen.getByText(/One 30-second frame vs your 505-frame stack/),
    ).toBeInTheDocument();
    // Collapsed: no image yet (History lists many runs — don't fetch each up front).
    expect(document.querySelector("img")).toBeNull();
    // The noise number isn't measured until the user reveals the comparison.
    expect(client.api.oneSubVsStackNoise).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /see the difference/i }));
    // Both halves load: the raw sub and the finished stack preview.
    const sub = await screen.findByAltText("A single raw sub");
    expect(sub).toHaveAttribute("src", "/api/targets/M_42/stack-runs/7/reference-sub");
    const stack = screen.getByAltText("Your finished stack");
    expect(stack).toHaveAttribute("src", "/api/targets/M_42/stack-runs/7/preview");
    // …and the concrete "cut your noise ~N×" badge appears once measured.
    expect(await screen.findByTestId("noise-badge")).toHaveTextContent(
      "Stacking your 505 subs cut the background noise about 15×.");
  });

  it("omits the noise badge when the ratio can't be measured", async () => {
    vi.spyOn(client.api, "oneSubVsStack").mockResolvedValue({
      available: true, n_frames: 505, sub_exposure_s: 30, integration_s: 15150,
    });
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue({ ratio: null });
    renderCard("M_42", 7);
    fireEvent.click(await screen.findByRole("button", { name: /see the difference/i }));
    await screen.findByAltText("A single raw sub");
    await waitFor(() =>
      expect(client.api.oneSubVsStackNoise).toHaveBeenCalled());
    expect(screen.queryByTestId("noise-badge")).toBeNull();
  });

  it("offers the composed before/after download once revealed", async () => {
    vi.spyOn(client.api, "oneSubVsStack").mockResolvedValue({
      available: true, n_frames: 505, sub_exposure_s: 30, integration_s: 15150,
    });
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue({ ratio: null });
    renderCard("M_42", 7);
    // Collapsed, the card is one button — the download appears with the reveal,
    // not before it.
    expect(screen.queryByRole("link", { name: /before\/after/i })).toBeNull();

    fireEvent.click(await screen.findByRole("button", { name: /see the difference/i }));
    const link = await screen.findByRole("link", { name: /before\/after/i });
    expect(link).toHaveAttribute(
      "href", "/api/targets/M_42/stack-runs/7/before-after.jpg");
    expect(link).toHaveAttribute("download");
  });

  it("degrades the caption when provenance is missing", async () => {
    vi.spyOn(client.api, "oneSubVsStack").mockResolvedValue({
      available: true, n_frames: null, sub_exposure_s: null, integration_s: null,
    });
    renderCard();
    await waitFor(() =>
      expect(screen.getByText(/One frame vs your stack —/)).toBeInTheDocument());
  });
});

describe("OneFrameVsStackCard — is that number any good?", () => {
  it("puts the √N yardstick beside a healthy stack's measured reduction", async () => {
    vi.spyOn(client.api, "oneSubVsStack").mockResolvedValue({
      available: true, n_frames: 505, sub_exposure_s: 30, integration_s: 15150,
    });
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue(
      { ratio: 21, expected_verdict: "expected" });
    renderCard("M_42", 7);
    fireEvent.click(await screen.findByRole("button", { name: /see the difference/i }));
    expect(await screen.findByTestId("noise-expected")).toHaveTextContent(
      "That's about what 505 subs should give (√505 ≈ 22×).");
  });

  it("says so when a stack came in well under what its subs should give", async () => {
    vi.spyOn(client.api, "oneSubVsStack").mockResolvedValue({
      available: true, n_frames: 400, sub_exposure_s: 30, integration_s: 12000,
    });
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue(
      { ratio: 8, expected_verdict: "low" });
    renderCard("M_42", 7);
    fireEvent.click(await screen.findByRole("button", { name: /see the difference/i }));
    const note = await screen.findByTestId("noise-expected");
    expect(note).toHaveTextContent(/400 subs should cut the noise about 20×/);
    expect(note).toHaveTextContent(/checking focus and alignment/);
  });

  it("says nothing about expectations when there's nothing to measure", async () => {
    vi.spyOn(client.api, "oneSubVsStack").mockResolvedValue({
      available: true, n_frames: 505, sub_exposure_s: 30, integration_s: 15150,
    });
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue({ ratio: null });
    renderCard("M_42", 7);
    fireEvent.click(await screen.findByRole("button", { name: /see the difference/i }));
    await screen.findByAltText("A single raw sub");
    await waitFor(() => expect(client.api.oneSubVsStackNoise).toHaveBeenCalled());
    expect(screen.queryByTestId("noise-expected")).toBeNull();
  });

  it("names no frame count anywhere on a mosaic's card", async () => {
    // The badge and the yardstick sit one above the other, and on a mosaic the
    // run's own 400 frames are the wrong denominator for *both*: the ratio was
    // measured over a central crop only 100 subs deep. The yardstick names the
    // panel depth; the badge — the card's one celebratory line — simply drops
    // the count rather than repeating the caveat.
    vi.spyOn(client.api, "oneSubVsStack").mockResolvedValue({
      available: true, n_frames: 400, sub_exposure_s: 30, integration_s: 12000,
    });
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue({
      ratio: 10, expected_verdict: "expected", expected_frames: 100,
      expected_basis: "mosaic_centre", is_mosaic: true,
    });
    renderCard("M_42", 7);
    fireEvent.click(await screen.findByRole("button", { name: /see the difference/i }));
    expect(await screen.findByTestId("noise-badge")).toHaveTextContent(
      "Stacking your subs cut the background noise about 10×.");
    expect(screen.getByTestId("noise-expected")).toHaveTextContent(
      "That's about what the 100 subs covering the middle of this mosaic " +
      "should give (√100 ≈ 10×).");
    for (const id of ["noise-badge", "noise-expected"]) {
      expect(screen.getByTestId(id)).not.toHaveTextContent("400");
    }
  });

  it("doesn't judge a stack too thin for √N to mean anything", async () => {
    // The server withholds a verdict below its 10-frame floor (measured and
    // pinned in tests/test_stackhealth.py) — the card just renders the badge.
    vi.spyOn(client.api, "oneSubVsStack").mockResolvedValue({
      available: true, n_frames: 6, sub_exposure_s: 30, integration_s: 180,
    });
    vi.spyOn(client.api, "oneSubVsStackNoise").mockResolvedValue(
      { ratio: 1.6, expected_verdict: null });
    renderCard("M_42", 7);
    fireEvent.click(await screen.findByRole("button", { name: /see the difference/i }));
    expect(await screen.findByTestId("noise-badge")).toBeInTheDocument();
    expect(screen.queryByTestId("noise-expected")).toBeNull();
  });
});
