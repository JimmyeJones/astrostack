import type { SystemInfo } from "../../api/client";

// Watched-folder readiness, classified from `GET /api/system`. The incoming
// folder is where the user drops frames ("Scan incoming" reads it) and the
// library root is where targets and stack outputs are written — if either is
// missing or read-only (an unmounted/typo'd/read-only NAS dataset), the app
// silently finds nothing to scan or can't write its result, with no cue as to
// why. The backend creates both at boot, so a healthy install is always ready
// and shows nothing; this only fires on a *definite* runtime problem, mirroring
// the `astapReadiness` first-run cue. Incoming is checked first (you can't even
// scan without it), then library.
export type FolderReadiness =
  | { ready: true }
  | { ready: false; kind: "incoming" | "library"; problem: "missing" | "unwritable" };

export function folderReadiness(folders: SystemInfo["folders"] | undefined): FolderReadiness {
  // Not loaded yet, or an old backend without the field → don't nag.
  if (!folders) return { ready: true };
  for (const kind of ["incoming", "library"] as const) {
    const f = folders[kind];
    if (!f) continue;
    // Only a *definite* false counts, so a partial/older payload never shows a
    // spurious warning.
    if (f.exists === false) return { ready: false, kind, problem: "missing" };
    if (f.writable === false) return { ready: false, kind, problem: "unwritable" };
  }
  return { ready: true };
}

// A stable string identifying the *specific* current folder problem (or null
// when ready), so a dismissal keys to it — dismissing "incoming missing"
// shouldn't suppress a later "library unwritable" or a problem that returns.
export function folderReadinessSignature(r: FolderReadiness): string | null {
  return r.ready ? null : `${r.kind}:${r.problem}`;
}
