// The one folder layout the app must never be pointed at, checked while you type.
//
// The server already refuses it (`nested_incoming_conflict` in `webapp/config.py`)
// and stays the authority — this is the same question asked early, so the answer
// arrives beside the field that caused it rather than as a red toast after Save.
//
// **Advisory only, on purpose.** A browser cannot resolve a symlink, a bind mount
// or a case-insensitive filesystem, so anything this cannot judge confidently must
// fall through to the save and let the server decide. It may therefore say nothing
// when there *is* a conflict; it must never claim one that isn't there.

export type FolderConflictField = "library_root" | "data_root";

export interface FolderConflict {
  /** Which form field to mark — the one the user can move. */
  field: FolderConflictField;
  /** Plain-language reason, in the same voice as the server's own message. */
  message: string;
}

/** Split an absolute POSIX path into its segments, or `null` if it isn't one we
 * can reason about (relative, empty, or containing `.`/`..`, which we cannot
 * resolve here without knowing the filesystem). */
function segments(path: string): string[] | null {
  const p = path.trim();
  if (!p.startsWith("/")) return null;
  const parts = p.split("/").filter(Boolean);
  if (parts.some((s) => s === "." || s === "..")) return null;
  return parts;
}

/** True when `child` is `parent` itself or sits beneath it. Segment-wise, so
 * `/data/incoming-old` is *not* inside `/data/incoming` (a plain string
 * `startsWith` would say it is, and would block a perfectly good layout). */
function isWithin(child: string[], parent: string[]): boolean {
  if (parent.length > child.length) return false;
  return parent.every((seg, i) => child[i] === seg);
}

/** Join a data root with one of the app's default sub-folder names, the same way
 * a blank field resolves on the server. */
function resolved(explicit: string, dataRoot: string, fallbackName: string): string {
  const v = explicit.trim();
  if (v) return v;
  const root = dataRoot.trim().replace(/\/+$/, "");
  return root ? `${root}/${fallbackName}` : "";
}

/**
 * The conflict to show, or `null` when the layout is safe *or* undecidable here.
 *
 * `incoming/` holds the owner's only copy of every raw sub and is strictly
 * read-only. The library tree and the state folder are the opposite — the app
 * prunes caches, thumbnails and stack outputs inside the library and rewrites
 * `config.json` in the state folder. Each of those deletes is correctly scoped to
 * its own tree, which is exactly why nesting one inside the other is the risk: a
 * perfectly correctly-scoped clean-up would resolve inside the raw folder.
 *
 * One-directional, like the server's: `incoming/` living inside the library root
 * is the app's own default shape one level up (both are children of the data
 * root), so it is not flagged.
 *
 * Arguments are the *form's* values, not the saved ones — a blank field resolves
 * against the data root being typed, so the check follows the edit rather than
 * the last save.
 */
export function folderConflict(
  incomingDir: string, libraryRoot: string, dataRoot: string,
): FolderConflict | null {
  const incoming = segments(resolved(incomingDir, dataRoot, "incoming"));
  if (!incoming || incoming.length === 0) return null;   // "/" is everyone's parent
  const candidates: [FolderConflictField, string, string][] = [
    ["library_root", "library folder", resolved(libraryRoot, dataRoot, "library")],
    ["data_root", "data folder", dataRoot],
  ];
  for (const [field, label, path] of candidates) {
    const segs = segments(path);
    if (!segs) continue;
    if (isWithin(segs, incoming)) {
      return {
        field,
        message:
          `Your ${label} would sit inside the incoming folder (${"/" + incoming.join("/")}). `
          + `Those two have to stay separate: the app tidies up old files inside the `
          + `${label}, and your incoming folder holds the only copy of your raw frames — `
          + `it must never be written to or cleaned up. Pick a folder outside it.`,
      };
    }
  }
  return null;
}

/**
 * A settings error as a sentence, without the HTTP status the API client prefixes.
 *
 * `api()` throws `` `${res.status}: ${detail}` ``, which is useful when the detail
 * is a bare stack trace and pure noise when — as with every guard on this page —
 * the server already wrote a plain-language reason. So the number is dropped only
 * when what follows actually reads as a sentence; anything else keeps the code,
 * because a beginner reporting "422" is more use than a beginner reporting nothing.
 */
export function settingsErrorMessage(raw: string): string {
  const m = /^\d{3}:\s+(.*)$/s.exec(raw.trim());
  if (!m) return raw;
  const detail = m[1].trim();
  // A sentence: starts with a capital, has more than a couple of words, and isn't
  // an exception's `SomeError: ...` shape.
  if (!/^[A-Z]/.test(detail)) return raw;
  if (/^[A-Za-z]*(Error|Exception):/.test(detail)) return raw;
  if (detail.split(/\s+/).length < 4) return raw;
  return detail;
}
