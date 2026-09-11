import { describe, expect, it } from "vitest";
import type { GlossaryTerm } from "./api/client";
import { filterGlossary, matchKind } from "./glossarySearch";

function term(over: Partial<GlossaryTerm>): GlossaryTerm {
  return { slug: "x", term: "X", body: "", ...over };
}

const DRIZZLE = term({
  slug: "drizzle", term: "Drizzle",
  body: "Higher resolution from dithered frames. Needs 200+ frames.",
});
const FWHM = term({
  slug: "fwhm", term: "FWHM (full width at half maximum)",
  body: "How sharp a star looks.",
});
const SIGMA = term({
  slug: "sigma-clipping", term: "Sigma clipping",
  body: "Removes satellite trails and cosmic rays from the stack.",
});

describe("matchKind", () => {
  it("matches the heading, case-insensitively", () => {
    expect(matchKind(DRIZZLE, "DRIZ")).toBe("term");
  });

  it("matches the expansion a beginner actually read on screen", () => {
    // They saw "full width at half maximum" in a tooltip, not "FWHM" — and the
    // heading carries the expansion in its brackets, which is exactly why there
    // is no separate alias list to keep in step with it.
    expect(matchKind(FWHM, "half maximum")).toBe("term");
  });

  it("matches the slug, so a pasted anchor finds its own entry", () => {
    expect(matchKind(SIGMA, "sigma-clipping")).toBe("term");
  });

  it("matches the explanation, which is how you search for a problem", () => {
    // Nothing is *called* "satellite"; the entry that solves it is the answer.
    expect(matchKind(SIGMA, "satellite")).toBe("body");
  });

  it("says so when nothing matches", () => {
    expect(matchKind(DRIZZLE, "narrowband")).toBeNull();
  });

  it("treats an empty query as every term matching by name", () => {
    expect(matchKind(DRIZZLE, "   ")).toBe("term");
  });
});

describe("filterGlossary", () => {
  it("is the whole list, in order, with no query", () => {
    expect(filterGlossary([DRIZZLE, FWHM, SIGMA], "")).toEqual([DRIZZLE, FWHM, SIGMA]);
  });

  it("puts a named match above one that merely mentions the word", () => {
    // "Drizzle" the entry must beat "…dithered frames" mentioning it — burying
    // the definition under three mentions is how a search box loses trust.
    const mentions = term({
      slug: "dithering", term: "Dithering",
      body: "It is what makes drizzle possible.",
    });
    expect(filterGlossary([mentions, DRIZZLE], "drizzle")).toEqual([DRIZZLE, mentions]);
  });

  it("keeps document order within each rank", () => {
    const a = term({ slug: "a", term: "A", body: "mentions kappa" });
    const b = term({ slug: "b", term: "B", body: "mentions kappa too" });
    expect(filterGlossary([a, b], "kappa")).toEqual([a, b]);
  });

  it("returns nothing for a word the glossary does not carry", () => {
    expect(filterGlossary([DRIZZLE, FWHM], "zzzz")).toEqual([]);
  });
});
