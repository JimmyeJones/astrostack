import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ObjectInfoCard,
  describeObject,
  difficultyColor,
  framingColor,
  framingSentence,
  framingWithMosaic,
} from "./ObjectInfoCard";
import * as client from "../api/client";

function renderCard(safe = "M_31", hideFraming = false) {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <ObjectInfoCard safe={safe} hideFraming={hideFraming} />
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

  it("appends the panel count when the catalog can plan the mosaic", () => {
    const framing = { level: "mosaic" as const, text: "is bigger than one frame." };
    const plan = {
      cols: 3, rows: 2, panels: 6,
      text: "About a 3×2 mosaic (6 panels) covers all of it.",
    };
    expect(framingWithMosaic("M 31", framing, plan)).toBe(
      "M 31 is bigger than one frame. About a 3×2 mosaic (6 panels) covers all of it.",
    );
    // No plan (a target that fits, or an older backend) → the sentence the card
    // has always shown, unchanged.
    expect(framingWithMosaic("M 31", framing, null)).toBe("M 31 is bigger than one frame.");
    expect(framingWithMosaic("M 31", framing, undefined)).toBe("M 31 is bigger than one frame.");
    // …and no framing hint at all still renders nothing, plan or no plan.
    expect(framingWithMosaic("M 13", null, plan)).toBe("");
  });

  it("nudges to mosaic in a warmer colour for the too-big cases", () => {
    expect(framingColor("mosaic")).toBe("orange.6");
    expect(framingColor("tight")).toBe("yellow.7");
    expect(framingColor("fits")).toBe("dimmed");
  });
});

describe("difficultyColor", () => {
  it("uses reassuring→amber colours, never an alarming red", () => {
    expect(difficultyColor("easy")).toBe("green");
    expect(difficultyColor("moderate")).toBe("blue");
    expect(difficultyColor("challenging")).toBe("orange");
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
      blurb: "The nearest large spiral galaxy to our own, about 2.5 million light-years away.",
    });
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Andromeda Galaxy")).toBeInTheDocument());
    expect(screen.getByText("M31")).toBeInTheDocument();
    expect(
      screen.getByText("A galaxy in the constellation Andromeda."),
    ).toBeInTheDocument();
    // The curated beginner blurb renders below the one-liner.
    expect(
      screen.getByText(/nearest large spiral galaxy to our own/),
    ).toBeInTheDocument();
    // The framing hint renders below, prefixed with the object's name.
    expect(
      screen.getByText(/Andromeda Galaxy is bigger than the Seestar's single frame/),
    ).toBeInTheDocument();
  });

  it("says how big a mosaic on the same line as the framing hint", async () => {
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M31", name: "Andromeda Galaxy", type: "galaxy",
      constellation: "Andromeda", constellation_abbr: "And",
      ra_deg: 10, dec_deg: 41, matched_by: "name",
      size_arcmin: 178,
      framing: { level: "mosaic", text: "is bigger than the Seestar's single frame — shoot it in mosaic mode to capture all of it." },
      mosaic: { cols: 3, rows: 2, panels: 6, text: "About a 3×2 mosaic (6 panels) covers all of it." },
    });
    renderCard();
    // One sentence, not a second banner: "shoot it in mosaic mode" and "how big
    // a mosaic" belong together.
    await waitFor(() =>
      expect(
        screen.getByText(/mosaic mode to capture all of it\. About a 3×2 mosaic \(6 panels\)/),
      ).toBeInTheDocument());
  });

  it("drops only the framing line when the page already measured it", async () => {
    // A page showing FramingVerdictNote for a finished picture already says
    // "…is bigger than one frame" — and says it about the picture that exists,
    // not the catalogue. The prediction steps aside; the rest of the card stays.
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M31", name: "Andromeda Galaxy", type: "galaxy",
      constellation: "Andromeda", constellation_abbr: "And",
      ra_deg: 10, dec_deg: 41, matched_by: "name",
      size_arcmin: 178,
      framing: { level: "mosaic", text: "is bigger than the Seestar's single frame — shoot it in mosaic mode to capture all of it." },
      blurb: "The nearest large spiral galaxy to our own, about 2.5 million light-years away.",
    });
    const { container } = renderCard("M_31", true);
    await waitFor(() =>
      expect(screen.getByText("Andromeda Galaxy")).toBeInTheDocument());
    expect(container.textContent).not.toContain("bigger than the Seestar's single frame");
    // Everything else the card exists for is untouched.
    expect(screen.getByText("A galaxy in the constellation Andromeda.")).toBeInTheDocument();
    expect(screen.getByText(/nearest large spiral galaxy/)).toBeInTheDocument();
  });

  it("renders the difficulty badge and honest sentence when vetted", async () => {
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M33", name: "Triangulum Galaxy", type: "galaxy",
      constellation: "Triangulum", constellation_abbr: "Tri",
      ra_deg: 23, dec_deg: 30, matched_by: "name",
      size_arcmin: 71,
      difficulty: {
        level: "challenging", label: "Challenging",
        text: "Faint and low-contrast — it rewards a darker sky and several hours.",
      },
    });
    renderCard("M_33");
    await waitFor(() =>
      expect(screen.getByText("Triangulum Galaxy")).toBeInTheDocument());
    expect(screen.getByText("Challenging for a Seestar")).toBeInTheDocument();
    expect(
      screen.getByText(/Faint and low-contrast/),
    ).toBeInTheDocument();
  });

  it("lets the difficulty sentence take a line of its own on a narrow screen", async () => {
    // Measured on a real phone-width browser before this: the sentence rendered
    // 194 px of a 336 px row (58 %) and four lines, because the badge beside it
    // never shrinks and the row was `nowrap`. jsdom has no layout, so what a test
    // can hold is the mechanism that stops it — the row wraps, and the sentence
    // asks for a width worth keeping on one line before it gives up and drops
    // below the badge (measured after: 336 px, two lines; a desktop row is still
    // one line).
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M33", name: "Triangulum Galaxy", type: "galaxy",
      constellation: "Triangulum", constellation_abbr: "Tri",
      ra_deg: 23, dec_deg: 30, matched_by: "name",
      difficulty: {
        level: "challenging", label: "Challenging",
        text: "Faint and low-contrast — it rewards a darker sky and several hours.",
      },
    });
    renderCard("M_33");
    const sentence = await screen.findByText(/Faint and low-contrast/);
    expect(sentence).toHaveStyle({ flex: "1 1 240px" });
    // Mantine drives a Group's wrapping through its own custom property rather
    // than a plain `flex-wrap`, so that is what there is to assert.
    const row = sentence.parentElement as HTMLElement;
    expect(row.style.getPropertyValue("--group-wrap")).toBe("wrap");
    // The badge still refuses to shrink — that is what makes the wrap necessary
    // rather than optional.
    const badge = screen.getByText("Challenging for a Seestar")
      .closest(".mantine-Badge-root") as HTMLElement;
    expect(badge).toHaveStyle({ flexShrink: "0" });
  });

  it("omits the difficulty badge when the object isn't vetted", async () => {
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "NGC 4449", name: "", type: "galaxy",
      constellation: "Canes Venatici", constellation_abbr: "CVn",
      ra_deg: 187, dec_deg: 44, matched_by: "name",
      // no `difficulty` field — old backend / uncurated object
    });
    const { container } = renderCard("NGC_4449");
    await waitFor(() =>
      expect(screen.getAllByText("NGC 4449").length).toBeGreaterThan(0));
    expect(container.textContent).not.toContain("for a Seestar");
  });

  it("omits the blurb line when the catalog has none", async () => {
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "NGC 663", name: "", type: "open cluster",
      constellation: "Cassiopeia", constellation_abbr: "Cas",
      ra_deg: 26, dec_deg: 61, matched_by: "name",
    });
    const { container } = renderCard();
    await waitFor(() =>
      expect(screen.getAllByText("NGC 663").length).toBeGreaterThan(0));
    // Only the one dimmed type/constellation line — no extra blurb paragraph.
    expect(
      screen.getByText("An open cluster in the constellation Cassiopeia."),
    ).toBeInTheDocument();
    expect(container.textContent).not.toContain("light-years");
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

  it("renders the light-travel line, and nothing when there's no vetted distance", async () => {
    // The one line on the card that's pure wonder rather than advice. The
    // backend hands over the finished sentence, so the card only decides
    // whether to show it.
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M31", name: "Andromeda Galaxy", type: "galaxy",
      constellation: "Andromeda", constellation_abbr: "And",
      ra_deg: 10, dec_deg: 41, matched_by: "name",
      light_travel: {
        distance_ly: 2500000, years: "2.5 million years",
        text: "The light in this picture left about 2.5 million years ago — before our species existed.",
      },
    });
    renderCard();
    await waitFor(() =>
      expect(screen.getByText(/before our species existed/)).toBeInTheDocument());
  });

  it("shows no light-travel line for an object with no vetted distance", async () => {
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "NGC 663", name: "NGC 663", type: "open cluster",
      constellation: "Cassiopeia", constellation_abbr: "Cas",
      ra_deg: 26, dec_deg: 61, matched_by: "name",
    });
    const { container } = renderCard();
    await waitFor(() =>
      expect(screen.getAllByText("NGC 663").length).toBeGreaterThan(0));
    expect(container.textContent).not.toContain("The light in this picture");
  });

  it("renders the full-Moon size line, and nothing when the object is small", async () => {
    // "178 arcmin" means nothing to a beginner; "6 full Moons" lands instantly.
    // The backend hands over the finished sentence, so the card only decides
    // whether to show it — and self-hides for an object too small to compare.
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M31", name: "Andromeda Galaxy", type: "galaxy",
      constellation: "Andromeda", constellation_abbr: "And",
      ra_deg: 10, dec_deg: 41, matched_by: "name",
      angular_size: {
        size_arcmin: 178, moons: 5.74,
        text: "In the sky it's about as wide as 6 full Moons.",
      },
    });
    renderCard();
    await waitFor(() =>
      expect(screen.getByText(/about as wide as 6 full Moons/)).toBeInTheDocument());
  });

  it("shows no size line for an object below Moon-scale", async () => {
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue({
      id: "M57", name: "Ring Nebula", type: "planetary nebula",
      constellation: "Lyra", constellation_abbr: "Lyr",
      ra_deg: 283, dec_deg: 33, matched_by: "name",
    });
    const { container } = renderCard();
    await waitFor(() =>
      expect(screen.getAllByText("Ring Nebula").length).toBeGreaterThan(0));
    expect(container.textContent).not.toContain("full Moon");
  });

  it("renders nothing when the target isn't recognised", async () => {
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue(null);
    const { container } = renderCard();
    // Give the query a tick to resolve, then assert the card stayed empty.
    await waitFor(() => expect(client.api.identifyTarget).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
