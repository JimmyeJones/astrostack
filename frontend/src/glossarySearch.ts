import type { GlossaryTerm } from "./api/client";

/**
 * Finding a word in the glossary.
 *
 * A reference page is only as good as its search box, and the search a beginner
 * actually runs is not "the heading, spelled correctly". It is the word they saw
 * on screen ("kappa", "hot pixel"), the expansion rather than the acronym ("full
 * width at half maximum" — which the heading carries in brackets, so a substring
 * match over the heading finds it), or — most often — the *problem* rather than
 * the term ("satellite", "green", "grainy"). So the body text is searched too,
 * and a match there still counts.
 *
 * Ranking exists for one reason: a body match is a much weaker signal than a
 * heading match, and burying "Drizzle" under three entries that merely mention
 * drizzle is how a search box stops being believed. Heading matches come first,
 * in document order; body-only matches follow, also in document order. No fuzzy
 * matching and no scoring beyond that — 38 entries is a list you can read, not a
 * corpus you have to rank.
 */

/** Where the query matched, strongest first. `null` means it didn't. */
export type GlossaryMatch = "term" | "body";

export function matchKind(term: GlossaryTerm, query: string): GlossaryMatch | null {
  const q = query.trim().toLowerCase();
  if (!q) return "term";
  if (term.term.toLowerCase().includes(q) || term.slug.includes(q)) return "term";
  if (term.body.toLowerCase().includes(q)) return "body";
  return null;
}

/** The terms to show for a query, in the order to show them. An empty query is
 *  the whole glossary, unreordered — the page's resting state is a list you can
 *  browse, not an empty box telling you to type. */
export function filterGlossary(terms: GlossaryTerm[], query: string): GlossaryTerm[] {
  if (!query.trim()) return terms;
  const named: GlossaryTerm[] = [];
  const mentioned: GlossaryTerm[] = [];
  for (const t of terms) {
    const kind = matchKind(t, query);
    if (kind === "term") named.push(t);
    else if (kind === "body") mentioned.push(t);
  }
  return [...named, ...mentioned];
}
