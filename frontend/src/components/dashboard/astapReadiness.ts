import type { SystemInfo } from "../../api/client";

// Plate-solving readiness, classified from `GET /api/system`. ASTAP (and a star
// database to match against) is required before *any* frame can be stacked, so a
// first-timer who lands on the Dashboard with no targets yet should be told
// upfront that it isn't set up — today that's surfaced only *reactively*, on the
// Settings page (badges) and on a Target page once a solve has already failed
// (`solveSetup.ts`). This mirrors the `astap.found` / `star_db_found` signals the
// Settings page already reads, so the Dashboard cue stays consistent with them.
export type AstapReadiness =
  | { ready: true }
  | { ready: false; kind: "astap" | "database" };

export function astapReadiness(astap: SystemInfo["astap"] | undefined): AstapReadiness {
  // System info not loaded yet (or an old backend without the field) → don't nag.
  if (!astap) return { ready: true };
  if (!astap.found) return { ready: false, kind: "astap" };
  // `star_db_found` is optional on older backends; only flag a *definite* false so
  // a backend that doesn't report it never shows a spurious "database missing".
  if (astap.star_db_found === false) return { ready: false, kind: "database" };
  return { ready: true };
}

// A stable string identifying the *specific* current problem (or null when
// ready), so a dismissal can be keyed to it: dismissing "ASTAP missing" then
// shouldn't suppress a later *different* problem ("database missing", or a
// problem that returns after ASTAP had been working and broke again).
export function astapReadinessSignature(r: AstapReadiness): string | null {
  return r.ready ? null : r.kind;
}
