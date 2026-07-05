/** Detect a plate-solve *setup* problem — ASTAP (the plate-solver) or its star
 * database not being available — as distinct from an ordinary per-frame
 * "couldn't solve this one frame".
 *
 * When ASTAP or its star database is missing, *every* frame's solve fails with
 * the same message, so the whole target's frames pile up as "Plate-solve failed"
 * with no hint that the fix is one setup action (install / point at ASTAP,
 * download a star database) rather than dropping frames one at a time — a total
 * blocker at first use with zero guidance today. We read the target's
 * `reject_reason` tally (keys like `solve_failed:<astap message>`) and match the
 * deterministic setup signatures the engine emits (mirroring
 * `_is_fatal_solve_error` and the "astap.exe not found" installer hint in
 * `seestack/solve/astap.py`).
 *
 * Deliberately conservative: only the install/database signatures trigger it. A
 * generic "could not open / error reading" is NOT treated as a setup problem (it
 * can be a single corrupt frame), so this never nags about setup when the real
 * issue is one bad file. Returns `null` when there's no detectable setup
 * problem, so the UI simply shows nothing (today's behaviour). */
export type SolveSetup = { kind: "astap" | "database"; frames: number };

// The plate-solver binary itself wasn't found — the most fundamental problem
// (nothing can be solved). Deterministic short message, so reliably detectable
// in the stored (120-char-truncated) reject reason.
const ASTAP_MISSING = ["astap.exe not found", "astap not found"];
// ASTAP ran but couldn't find a star database to match against. Best-effort:
// this phrase may fall outside the truncated reason window, in which case the
// banner simply doesn't fire (graceful — no regression, no false positive).
const DB_MISSING = ["no star database", "star database not found", "star database"];

export function detectSolveSetupProblem(
  counts: Record<string, number> | undefined | null,
): SolveSetup | null {
  if (!counts) return null;
  let astapFrames = 0;
  let dbFrames = 0;
  for (const [reason, n] of Object.entries(counts)) {
    if (!reason.startsWith("solve_failed")) continue;
    const low = reason.toLowerCase();
    if (ASTAP_MISSING.some((s) => low.includes(s))) astapFrames += n;
    else if (DB_MISSING.some((s) => low.includes(s))) dbFrames += n;
  }
  // ASTAP-missing is the more fundamental problem (the solver never even ran, so
  // a "no database" message can't also be present); report it first.
  if (astapFrames > 0) return { kind: "astap", frames: astapFrames };
  if (dbFrames > 0) return { kind: "database", frames: dbFrames };
  return null;
}
