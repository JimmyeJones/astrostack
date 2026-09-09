/** What the upload form should say about the destination folder you typed.
 *
 *  The "Target folder" box on the upload card is a plain text field, and two
 *  beginner mistakes live in it — neither of them guessable from the field:
 *
 *  1. **A near-miss makes a second target.** Typing `M31` when the library
 *     already holds *M 31* splits one object's subs across two thinner stacks,
 *     and nothing says so until the Library shows two rows.
 *  2. **The obvious name is the one the app skips.** A Seestar's raw subs live
 *     in `M 31_sub/`; the bare `M 31/` beside it is the device's *own* finished
 *     picture, which the scanner deliberately passes over
 *     (`seestack.io.scanner._apply_seestar_convention`). So typing the target's
 *     own name lands the files and never ingests them.
 *
 *  Both are answerable from `GET /api/upload-destinations` — the folders under
 *  `incoming/` that already hold subs, and the target each one became — so the
 *  wording lives here, once, next to the rules it is describing.
 */

/** One folder under `incoming/` that already holds a target's subs.
 *  Mirrors `webapp.routers.upload.UploadDestination`. */
export interface UploadDestination {
  target: string;
  folder: string;
  n_frames: number;
}

export interface DestinationAdvice {
  /** `warn` when following through would lose or split the upload. */
  tone: "info" | "warn";
  message: string;
  /** The folder to use instead — present only when there is one right answer,
   *  so the sentence can carry the button that sets it (the app's usual idiom:
   *  copy that names a value some reachable control would accept gets that
   *  control). */
  fixFolder?: string;
}

/** The suffix a Seestar's raw-subs folder carries, and the one the scanner's
 *  "this bare folder is the device's own output" sibling test appends. Kept as a
 *  constant because both rules below are exactly about this string. */
const SUB_SUFFIX = "_sub";
const MOSAIC_SUB_SUFFIX = "_mosaic_sub";
/** Capture-mode folders the scanner never ingests at all. */
const CAPTURE_SUFFIXES = ["_video", "_photo"];
/** Another program's scratch directory, skipped by exact name (v0.393.0). */
const TEMP_FOLDER_NAMES = ["batch_stack_tmp"];

/** The target name a folder becomes under the scanner's Seestar convention.
 *
 *  Mirror of `seestack.io.scanner.target_name_for_folder`; a drift test pins the
 *  two against each other, because a stale copy here would quietly tell someone
 *  their upload joins a target it does not join. */
export function targetNameForFolder(folder: string): string {
  const low = folder.toLowerCase();
  if (low.endsWith(MOSAIC_SUB_SUFFIX)) {
    const base = folder.slice(0, -MOSAIC_SUB_SUFFIX.length).replace(/\s+$/, "");
    return base ? `${base} (mosaic)` : folder;
  }
  if (low.endsWith(SUB_SUFFIX)) {
    const base = folder.slice(0, -SUB_SUFFIX.length).replace(/\s+$/, "");
    return base ? base : folder;
  }
  return folder;
}

/** Fold away the differences a person does not mean — case, spaces, underscores
 *  and hyphens — so `M31`, `m 31` and `M-31` all read as one name. Used **only**
 *  for the "did you mean" nudge; every rule that describes what the scanner will
 *  actually do compares exactly (case-insensitively), because the scanner does. */
export function normalizeTargetName(name: string): string {
  return name.toLowerCase().replace(/[\s_-]+/g, "");
}

function plural(n: number, one: string, many: string): string {
  return `${n.toLocaleString()} ${n === 1 ? one : many}`;
}

/** What to say under the destination box for what has been typed into it.
 *
 *  `null` when there is nothing worth saying — a blank box already has the
 *  form's own "will go to Unsorted" line, and repeating it would be one more
 *  always-on sentence on a card that is trying to stay small. */
export function destinationAdvice(
  typed: string,
  destinations: UploadDestination[],
): DestinationAdvice | null {
  const folder = typed.trim();
  if (!folder) return null;
  const low = folder.toLowerCase();

  if (CAPTURE_SUFFIXES.some((s) => low.endsWith(s))) {
    return {
      tone: "warn",
      message:
        `AstroStack skips folders ending in “${low.endsWith("_video") ? "_video" : "_photo"}” — ` +
        "they hold videos and single stills, not stackable subs. " +
        "Pick a different folder name for these.",
    };
  }
  if (TEMP_FOLDER_NAMES.includes(low)) {
    return {
      tone: "warn",
      message:
        `“${folder}” is another program’s working folder, so AstroStack walks past it. ` +
        "Pick a different folder name for these.",
    };
  }

  const exact = destinations.find((d) => d.folder.toLowerCase() === low);
  if (exact) {
    return {
      tone: "info",
      message:
        `Adds to ${exact.target} — ${plural(exact.n_frames, "sub", "subs")} of it ` +
        `already live in “${exact.folder}”.`,
    };
  }

  // The trap: a bare `<T>/` next to a real `<T>_sub/` is the Seestar's own
  // finished picture, and the scanner skips it. Compared exactly (lower-cased)
  // because that is the comparison the scanner itself makes — a near-miss like
  // `M31` would *not* be skipped, it would make a second target, which is the
  // different (and differently-worded) case below.
  const sibling = destinations.find((d) => d.folder.toLowerCase() === low + SUB_SUFFIX);
  if (sibling) {
    return {
      tone: "warn",
      message:
        `“${folder}” beside “${sibling.folder}” is where a Seestar puts its own ` +
        `finished picture, so AstroStack would skip these. ${sibling.target}’s subs ` +
        `live in “${sibling.folder}”.`,
      fixFolder: sibling.folder,
    };
  }

  // A near-miss on a target you already have: same object, different spelling,
  // which would quietly become a second target with half the subs.
  const norm = normalizeTargetName(folder);
  const asTarget = normalizeTargetName(targetNameForFolder(folder));
  const near = destinations.find(
    (d) =>
      normalizeTargetName(d.folder) === norm ||
      normalizeTargetName(d.target) === norm ||
      normalizeTargetName(d.target) === asTarget,
  );
  if (near) {
    return {
      tone: "warn",
      message:
        `You already have ${near.target} — ${plural(near.n_frames, "sub", "subs")} in ` +
        `“${near.folder}”. “${folder}” would start a second target and split them.`,
      fixFolder: near.folder,
    };
  }

  const name = targetNameForFolder(folder);
  return {
    tone: "info",
    message:
      name === folder
        ? `Starts a new target called ${name}.`
        // `M 31_sub` becomes the target *M 31* — worth saying, because the box
        // asks for a folder and the Library will show the other name.
        : `Starts a new target called ${name} (a “${folder}” folder becomes that).`,
  };
}
