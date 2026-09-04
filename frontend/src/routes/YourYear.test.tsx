import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { YourYearView } from "./YourYear";
import * as client from "../api/client";
import type { YearRecap } from "../api/client";

function recap(over: Partial<YearRecap>): YearRecap {
  return {
    year: 2026, has_anything: true,
    headline: "You were out under the stars on 12 nights in 2026 and collected "
      + "18 h of light on 3 targets.",
    empty_message: "",
    stats: [
      { value: "18 h", label: "of light collected" },
      { value: "12", label: "nights out" },
      { value: "3", label: "targets imaged" },
    ],
    first_light_line: "", n_nights: 12, total_exposure_s: 64800, n_frames: 720,
    n_targets: 3, target_names: ["M 31", "M 42", "NGC 7000"], first_lights: [],
    longest_night: null, sharpest_night: null, years_with_data: [2026],
    ...over,
  };
}

function renderPage(year: string) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[`/sky-so-far/${year}`]}>
          <Routes>
            <Route path="/sky-so-far/:year" element={<YourYearView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("YourYearView", () => {
  it("asks for the year in the address and leads with its headline", async () => {
    const spy = vi.spyOn(client.api, "getYearRecap")
      .mockResolvedValue(recap({ year: 2024, years_with_data: [2024] }));
    renderPage("2024");
    await waitFor(() =>
      expect(screen.getByText(/Your 2024 under the stars/)).toBeInTheDocument());
    expect(spy).toHaveBeenCalledWith(2024);
    expect(screen.getByText(/You were out under the stars/)).toBeInTheDocument();
  });

  it("shows the headline numbers as they came from the server", async () => {
    vi.spyOn(client.api, "getYearRecap").mockResolvedValue(recap({}));
    renderPage("2026");
    await waitFor(() => expect(screen.getByText("18 h")).toBeInTheDocument());
    expect(screen.getByText("of light collected")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("nights out")).toBeInTheDocument();
  });

  it("names the longest and sharpest nights when the server named them", async () => {
    vi.spyOn(client.api, "getYearRecap").mockResolvedValue(recap({
      longest_night: {
        date: "2026-02-14", exposure_s: 7200, n_frames: 120,
        targets: ["M 31"], median_fwhm_px: null, n_measured: 0,
      },
      sharpest_night: {
        date: "2026-03-03", exposure_s: 3600, n_frames: 60,
        targets: ["M 42"], median_fwhm_px: 2.4, n_measured: 40,
      },
    }));
    renderPage("2026");
    await waitFor(() =>
      expect(screen.getByText(/Longest night/)).toBeInTheDocument());
    expect(screen.getByText("2.0 h")).toBeInTheDocument();
    expect(screen.getByText(/Sharpest night/)).toBeInTheDocument();
    expect(screen.getByText("2.4 px stars")).toBeInTheDocument();
  });

  it("omits a standout night the server stayed silent about", async () => {
    // A one-night year has no "longest"; the page must not invent one.
    vi.spyOn(client.api, "getYearRecap").mockResolvedValue(recap({}));
    renderPage("2026");
    await waitFor(() => expect(screen.getByText("18 h")).toBeInTheDocument());
    expect(screen.queryByText(/Longest night/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Sharpest night/)).not.toBeInTheDocument();
  });

  it("links each first-light target to its own page", async () => {
    vi.spyOn(client.api, "getYearRecap").mockResolvedValue(recap({
      first_lights: [
        { name: "M 42", safe: "M_42" },
        { name: "Gone", safe: null },
      ],
    }));
    renderPage("2026");
    await waitFor(() =>
      expect(screen.getByTestId("first-lights")).toBeInTheDocument());
    // Scoped to the first-light card: the same name also appears in the
    // "what you pointed at" list below it, where it is not a link.
    const firsts = within(screen.getByTestId("first-lights"));
    expect(firsts.getByText("M 42").closest("a"))
      .toHaveAttribute("href", "/targets/M_42");
    // A target the registry no longer has is still named, just not linked.
    expect(firsts.getByText("Gone").closest("a")).toBeNull();
  });

  it("offers the years that do have data when this one is empty", async () => {
    vi.spyOn(client.api, "getYearRecap").mockResolvedValue(recap({
      year: 2026, has_anything: false, headline: "", stats: [],
      n_nights: 0, n_targets: 0, target_names: [], n_frames: 0,
      total_exposure_s: 0, years_with_data: [2024, 2025],
      empty_message: "Nothing from 2026 — but 2024 and 2025 have your nights in them.",
    }));
    renderPage("2026");
    await waitFor(() =>
      expect(screen.getByTestId("year-empty")).toBeInTheDocument());
    expect(screen.getByText(/Nothing from 2026/)).toBeInTheDocument();
    expect(screen.getByText("See 2025 instead").closest("a"))
      .toHaveAttribute("href", "/sky-so-far/2025");
    // …and no zeros anywhere.
    expect(screen.queryByText("nights out")).not.toBeInTheDocument();
  });

  it("offers a year picker once there is more than one year", async () => {
    vi.spyOn(client.api, "getYearRecap")
      .mockResolvedValue(recap({ year: 2026, years_with_data: [2025, 2026] }));
    renderPage("2026");
    await waitFor(() =>
      expect(screen.getByTestId("year-picker")).toBeInTheDocument());
    expect(screen.getByText("2025").closest("a"))
      .toHaveAttribute("href", "/sky-so-far/2025");
  });

  it("hides the picker on a library with a single year", async () => {
    vi.spyOn(client.api, "getYearRecap")
      .mockResolvedValue(recap({ years_with_data: [2026] }));
    renderPage("2026");
    await waitFor(() => expect(screen.getByText("18 h")).toBeInTheDocument());
    expect(screen.queryByTestId("year-picker")).not.toBeInTheDocument();
  });

  it("treats a nonsense year in the address as 'this year', not an error", async () => {
    const spy = vi.spyOn(client.api, "getYearRecap").mockResolvedValue(recap({}));
    renderPage("banana");
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy).toHaveBeenCalledWith(new Date().getFullYear());
  });

  it("offers the year as something to post, over its own best picture", async () => {
    vi.spyOn(client.api, "getYearRecap").mockResolvedValue(recap({
      year: 2026,
      caption: "2026 under the stars · 12 nights out",
      hero: {
        name: "M 31", safe: "M_31",
        thumbnail_url: "/api/targets/M_31/thumbnail", note: "",
      },
    }));
    renderPage("2026");
    const card = await screen.findByTestId("year-share");
    expect(within(card).getByRole("link", { name: /Download poster/ }))
      .toHaveAttribute("href", "/api/recap/year/2026.jpg");
    expect(within(card).getByAltText("Your picture of M 31")).toBeInTheDocument();
  });

  it("offers nothing to share on a year with no nights in it", async () => {
    vi.spyOn(client.api, "getYearRecap").mockResolvedValue(recap({
      has_anything: false, headline: "", stats: [], n_nights: 0,
      empty_message: "Nothing from 2026 — but 2025 has your nights in it.",
      years_with_data: [2025], caption: "",
    }));
    renderPage("2026");
    await waitFor(() =>
      expect(screen.getByTestId("year-empty")).toBeInTheDocument());
    expect(screen.queryByTestId("year-share")).not.toBeInTheDocument();
  });
});
