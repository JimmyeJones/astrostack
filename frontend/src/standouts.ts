/**
 * "Your sky, so far" — the two standout cards, and the one decision they share.
 *
 * The page ranks the library twice: by integration ("your biggest project") and
 * by frames kept ("most-imaged target"). On a Seestar those two questions have
 * the *same* answer most of the time — subs are a fixed length, so total
 * exposure is very nearly the sub count times a constant — and a library with
 * one target has no choice at all. When that happens the page used to render the
 * same picture, the same name and a near-identical figure twice, side by side,
 * which reads as a bug or as padding rather than as two accolades.
 *
 * So the deciding is pure and lives here: it returns one card when the two
 * superlatives land on one target (naming both, with both figures — nothing is
 * removed) and two when they genuinely differ. The all-time poster already made
 * the same call for its own copy (`seestack/recap.py` keeps the top target out
 * of the "also shot" line "so the two lines sit together without repeating a
 * name"); this is that rule on the screen the poster is made from.
 */
import type { SummaryTarget } from "./api/client";

export type StandoutKey = "longest" | "most_imaged" | "both";

export interface StandoutSpec {
  /** Which accolade(s) this card carries — also its React key. */
  key: StandoutKey;
  /** The dimmed label above the name. */
  title: string;
  target: SummaryTarget;
  /** The figure(s) under the name. */
  detail: string;
}

function integrationDetail(
  t: SummaryTarget, formatIntegration: (s: number) => string,
): string {
  return `${formatIntegration(t.total_exposure_s)} of integration`;
}

function subsDetail(t: SummaryTarget): string {
  const n = t.n_frames_accepted;
  return `${n.toLocaleString()} sub${n === 1 ? "" : "s"} kept`;
}

/**
 * The standout cards to render, in order — none, one or two.
 *
 * One card whenever both accolades name the same target: it keeps both titles
 * and both figures, so the reader loses no fact and gains the thing the two
 * cards never said — that this target is *both*.
 */
export function libraryStandouts(
  longest: SummaryTarget | null | undefined,
  mostImaged: SummaryTarget | null | undefined,
  formatIntegration: (s: number) => string,
): StandoutSpec[] {
  if (longest && mostImaged && longest.safe === mostImaged.safe) {
    return [{
      key: "both",
      title: "Your biggest project — and most-imaged",
      target: longest,
      detail: `${integrationDetail(longest, formatIntegration)} · ${subsDetail(mostImaged)}`,
    }];
  }
  const out: StandoutSpec[] = [];
  if (longest) {
    out.push({
      key: "longest",
      title: "Your biggest project",
      target: longest,
      detail: integrationDetail(longest, formatIntegration),
    });
  }
  if (mostImaged) {
    out.push({
      key: "most_imaged",
      title: "Most-imaged target",
      target: mostImaged,
      detail: subsDetail(mostImaged),
    });
  }
  return out;
}
