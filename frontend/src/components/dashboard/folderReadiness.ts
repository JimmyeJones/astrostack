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
//
// Ahead of both: the unsafe nested layout (`incoming/` inside the library's own
// trees, or the other way round), which the server reports as a sentence. It
// outranks a missing folder because while it is set the server refuses every
// delete and scan to keep the raws safe, so it must be fixed first.
export type FolderReadiness =
  | { ready: true }
  | { ready: false; kind: "incoming" | "library"; problem: "missing" | "unwritable" }
  | { ready: false; kind: "layout"; problem: "nested"; message: string };

export function folderReadiness(folders: SystemInfo["folders"] | undefined): FolderReadiness {
  // Not loaded yet, or an old backend without the field → don't nag.
  if (!folders) return { ready: true };
  if (folders.layout_conflict) {
    return { ready: false, kind: "layout", problem: "nested", message: folders.layout_conflict };
  }
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

// The Dashboard notice's words for a folder problem. Moved here from the
// component so the nested-layout case (the server's own sentence, plus what the
// app is now refusing to do) is testable beside the other four.
export function folderNoticeText(
  r: Exclude<FolderReadiness, { ready: true }>,
): { title: string; body: string } {
  if (r.kind === "layout") {
    return {
      title: "Your folders are set up in a way that could delete your raw frames",
      body: r.message + " Until this is fixed, the app won't delete, merge, clear or scan "
        + "anything, to keep your raw frames safe.",
    };
  }
  if (r.kind === "incoming") {
    return r.problem === "missing"
      ? {
        title: "Your incoming folder doesn't exist yet",
        body: "The folder you drop frames into can't be found — \"Scan incoming\" will "
          + "find nothing until it exists. Check the folder is mounted and the path "
          + "is right.",
      }
      : {
        title: "Your incoming folder isn't writable",
        body: "The folder you drop frames into is read-only, so scanning it may fail. "
          + "Check the folder's permissions or the path.",
      };
  }
  return r.problem === "missing"
    ? {
      title: "Your library folder doesn't exist yet",
      body: "The folder your stacks and library are written to can't be found — "
        + "processing will fail until it exists. Check the folder is mounted and "
        + "the path is right.",
    }
    : {
      title: "Your library folder isn't writable",
      body: "The folder your stacks and library are written to is read-only, so "
        + "processing can't save its results. Check the folder's permissions or "
        + "the path.",
    };
}
