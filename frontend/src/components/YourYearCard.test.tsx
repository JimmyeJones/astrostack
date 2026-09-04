import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { YourYearCard } from "./YourYearCard";
import * as client from "../api/client";
import type { YearRecap } from "../api/client";

function recap(over: Partial<YearRecap>): YearRecap {
  return {
    year: new Date().getFullYear(), has_anything: true, headline: "",
    empty_message: "", stats: [], first_light_line: "", n_nights: 0,
    total_exposure_s: 0, n_frames: 0, n_targets: 0, target_names: [],
    first_lights: [], longest_night: null, sharpest_night: null,
    years_with_data: [], ...over,
  };
}

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><YourYearCard /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("YourYearCard", () => {
  it("links to the most recent year that has nights, not the calendar year", async () => {
    // Clicking in on 3 January should land on the season you just finished.
    const thisYear = new Date().getFullYear();
    vi.spyOn(client.api, "getYearRecap").mockResolvedValue(recap({
      year: thisYear, has_anything: false,
      years_with_data: [thisYear - 2, thisYear - 1],
    }));
    renderCard();
    await waitFor(() =>
      expect(screen.getByTestId("your-year")).toBeInTheDocument());
    expect(screen.getByTestId("your-year"))
      .toHaveAttribute("href", `/sky-so-far/${thisYear - 1}`);
    expect(screen.getByText(`Your ${thisYear - 1} under the stars`))
      .toBeInTheDocument();
  });

  it("shows the year's own headline when it is the year it links to", async () => {
    const thisYear = new Date().getFullYear();
    vi.spyOn(client.api, "getYearRecap").mockResolvedValue(recap({
      year: thisYear, has_anything: true, years_with_data: [thisYear],
      headline: "You were out under the stars on 9 nights this year.",
    }));
    renderCard();
    await waitFor(() =>
      expect(screen.getByText(/out under the stars on 9 nights/))
        .toBeInTheDocument());
  });

  it("does not put another year's headline on a different year's link", async () => {
    const thisYear = new Date().getFullYear();
    vi.spyOn(client.api, "getYearRecap").mockResolvedValue(recap({
      year: thisYear, has_anything: false, years_with_data: [thisYear - 1],
      headline: "",
    }));
    renderCard();
    await waitFor(() =>
      expect(screen.getByTestId("your-year")).toBeInTheDocument());
    expect(screen.getByText(new RegExp(`Look back at ${thisYear - 1}`)))
      .toBeInTheDocument();
  });

  it("self-hides on a library with no nights at all", async () => {
    const spy = vi.spyOn(client.api, "getYearRecap")
      .mockResolvedValue(recap({ has_anything: false, years_with_data: [] }));
    renderCard();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("your-year")).not.toBeInTheDocument();
  });

  it("self-hides against a backend that doesn't have the endpoint", async () => {
    const spy = vi.spyOn(client.api, "getYearRecap")
      .mockRejectedValue(new Error("404"));
    renderCard();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("your-year")).not.toBeInTheDocument();
  });
});
