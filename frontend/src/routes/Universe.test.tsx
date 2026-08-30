import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { UniverseLegend, UniverseObjectCard } from "./Universe";
import type { UniverseData, UniverseObject } from "../sky/universe";

const OBJ: UniverseObject = {
  safe: "M_31", name: "M 31", object_id: "M31", object_name: "Andromeda Galaxy",
  type: "galaxy", ra_deg: 10.68, dec_deg: 41.27, distance_ly: 2_500_000,
  distance_text: "2.5 million ly", years_text: "2.5 million years", depth: 0.82,
};

const DATA: UniverseData = {
  objects: [
    { ...OBJ, safe: "M_42", name: "M 42", object_id: "M42", distance_ly: 1344,
      distance_text: "1,340 ly", years_text: "1,340 years", depth: 0.12 },
    OBJ,
  ],
  shells: [
    { distance_ly: 1e3, depth: 0.08, label: "1,000 ly" },
    { distance_ly: 1e6, depth: 0.75, label: "1 million ly" },
  ],
  unplaced: [{ safe: "Backyard", name: "Backyard test", reason: "no distance for it" }],
  near_ly: 700, far_ly: 4e6,
  provenance: "Your own pictures decide which objects are here. How far away "
    + "each one is comes from a published catalogue.",
};

function renderLegend(data: UniverseData = DATA) {
  return render(
    <MantineProvider>
      <MemoryRouter><UniverseLegend data={data} /></MemoryRouter>
    </MantineProvider>,
  );
}

describe("UniverseLegend", () => {
  it("says where the distances come from — every time", () => {
    // The one claim this feature must never let a beginner get wrong: the app
    // did not measure these distances.
    renderLegend();
    expect(screen.getByText(/published catalogue/)).toBeTruthy();
  });

  it("reads out the span and what the rings mean", () => {
    renderLegend();
    expect(screen.getByText(/From M 42 at 1,340 ly out to M 31 at 2.5 million ly/)).toBeTruthy();
    expect(screen.getByText(/Rings mark 1,000 ly out to 1 million ly/)).toBeTruthy();
    expect(screen.getByText("2 placed")).toBeTruthy();
  });

  it("names the targets it could not place, on request — never silently drops them", () => {
    renderLegend();
    expect(screen.queryByText(/Backyard test/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "1 not placed" }));
    expect(screen.getByText(/Backyard test — no distance for it/)).toBeTruthy();
  });

  it("has no 'not placed' control when everything was placed", () => {
    renderLegend({ ...DATA, unplaced: [] });
    expect(screen.queryByRole("button", { name: /not placed/ })).toBeNull();
  });

  it("points back at the Sky Map, so the two views explain each other", () => {
    renderLegend();
    expect(screen.getByRole("link", { name: "Sky Map" })).toHaveAttribute("href", "/sky");
  });

  it("claims no span or scale when there is nothing placed", () => {
    renderLegend({ ...DATA, objects: [], shells: [] });
    expect(screen.getByText("0 placed")).toBeTruthy();
    expect(screen.queryByText(/^From /)).toBeNull();
    expect(screen.queryByText(/^Rings mark/)).toBeNull();
  });
});

describe("UniverseObjectCard", () => {
  it("reads the object out in distance and in light-travel time", () => {
    render(
      <MantineProvider>
        <UniverseObjectCard object={OBJ} onOpen={() => {}} onClose={() => {}} />
      </MantineProvider>,
    );
    expect(screen.getByText("M 31")).toBeTruthy();
    expect(screen.getByText("Andromeda Galaxy · galaxy")).toBeTruthy();
    expect(screen.getByText("2.5 million ly away")).toBeTruthy();
    expect(screen.getByText(/left about 2.5 million years ago/)).toBeTruthy();
  });

  it("says what the object is when the catalogue has a blurb", () => {
    render(
      <MantineProvider>
        <UniverseObjectCard
          object={{ ...OBJ, blurb: "The nearest big galaxy to our own." }}
          onOpen={() => {}} onClose={() => {}} />
      </MantineProvider>,
    );
    expect(screen.getByText("The nearest big galaxy to our own.")).toBeTruthy();
  });

  it("shows no sentence at all when the catalogue has none", () => {
    // "" and a missing field both read as nothing — never an empty line.
    for (const blurb of ["", undefined]) {
      const { unmount } = render(
        <MantineProvider>
          <UniverseObjectCard object={{ ...OBJ, blurb }} onOpen={() => {}}
            onClose={() => {}} />
        </MantineProvider>,
      );
      expect(screen.getByText("2.5 million ly away")).toBeTruthy();
      unmount();
    }
  });

  it("opens the target it belongs to", () => {
    const onOpen = vi.fn();
    render(
      <MantineProvider>
        <UniverseObjectCard object={OBJ} onOpen={onOpen} onClose={() => {}} />
      </MantineProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open target" }));
    expect(onOpen).toHaveBeenCalledWith("M_31");
  });
});
