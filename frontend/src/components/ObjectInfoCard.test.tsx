import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ObjectInfoCard, describeObject } from "./ObjectInfoCard";
import * as client from "../api/client";

function renderCard(safe = "M_31") {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <ObjectInfoCard safe={safe} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("describeObject", () => {
  it("phrases a plain-language one-liner with the right article", () => {
    expect(describeObject("galaxy", "Andromeda")).toBe(
      "A galaxy in the constellation Andromeda.");
    expect(describeObject("emission nebula", "Orion")).toBe(
      "An emission nebula in the constellation Orion.");
    // Unknown constellation drops the "in the constellation …" clause.
    expect(describeObject("nebula", "")).toBe("A nebula.");
    // Missing type falls back to a generic noun.
    expect(describeObject("", "Cygnus")).toBe(
      "A deep-sky object in the constellation Cygnus.");
  });
});

describe("ObjectInfoCard", () => {
  it("renders the catalog card on a confident match", async () => {
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M31", name: "Andromeda Galaxy", type: "galaxy",
      constellation: "Andromeda", constellation_abbr: "And",
      ra_deg: 10, dec_deg: 41, matched_by: "name",
    });
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Andromeda Galaxy")).toBeInTheDocument());
    expect(screen.getByText("M31")).toBeInTheDocument();
    expect(
      screen.getByText("A galaxy in the constellation Andromeda."),
    ).toBeInTheDocument();
  });

  it("notes when the match came from the plate-solved position", async () => {
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "NGC 7000", name: "North America Nebula", type: "nebula",
      constellation: "Cygnus", constellation_abbr: "Cyg",
      ra_deg: 314, dec_deg: 44, matched_by: "coords",
    });
    renderCard();
    await waitFor(() =>
      expect(
        screen.getByText(/Identified from this target's plate-solved position/),
      ).toBeInTheDocument());
  });

  it("renders nothing when the target isn't recognised", async () => {
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue(null);
    const { container } = renderCard();
    // Give the query a tick to resolve, then assert the card stayed empty.
    await waitFor(() => expect(client.api.identifyTarget).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
