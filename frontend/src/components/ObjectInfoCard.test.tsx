import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ObjectInfoCard,
  describeObject,
  framingColor,
  framingSentence,
} from "./ObjectInfoCard";
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

describe("framingSentence / framingColor", () => {
  it("prefixes the display name onto the backend verb phrase", () => {
    expect(
      framingSentence("M 31", { level: "mosaic", text: "is bigger than one frame." }),
    ).toBe("M 31 is bigger than one frame.");
    // No framing hint → empty string (card renders nothing).
    expect(framingSentence("M 13", null)).toBe("");
    expect(framingSentence("M 13", undefined)).toBe("");
  });

  it("nudges to mosaic in a warmer colour for the too-big cases", () => {
    expect(framingColor("mosaic")).toBe("orange.6");
    expect(framingColor("tight")).toBe("yellow.7");
    expect(framingColor("fits")).toBe("dimmed");
  });
});

describe("ObjectInfoCard", () => {
  it("renders the catalog card on a confident match", async () => {
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M31", name: "Andromeda Galaxy", type: "galaxy",
      constellation: "Andromeda", constellation_abbr: "And",
      ra_deg: 10, dec_deg: 41, matched_by: "name",
      size_arcmin: 178,
      framing: { level: "mosaic", text: "is bigger than the Seestar's single frame — shoot it in mosaic mode to capture all of it." },
    });
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Andromeda Galaxy")).toBeInTheDocument());
    expect(screen.getByText("M31")).toBeInTheDocument();
    expect(
      screen.getByText("A galaxy in the constellation Andromeda."),
    ).toBeInTheDocument();
    // The framing hint renders below, prefixed with the object's name.
    expect(
      screen.getByText(/Andromeda Galaxy is bigger than the Seestar's single frame/),
    ).toBeInTheDocument();
  });

  it("omits the framing line when the catalog has no size", async () => {
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M13", name: "", type: "globular cluster",
      constellation: "Hercules", constellation_abbr: "Her",
      ra_deg: 250, dec_deg: 36, matched_by: "name",
    });
    renderCard();
    await waitFor(() =>
      expect(screen.getAllByText("M13").length).toBeGreaterThan(0));
    expect(screen.queryByText(/mosaic mode/)).toBeNull();
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
