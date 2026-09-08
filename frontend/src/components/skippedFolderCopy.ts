/**
 * One place that owns how a **skipped folder** is described, because two
 * surfaces describe the same finding — the Jobs page's per-scan alert and the
 * Library's standing `SkippedFoldersCard` — and there are now two reasons a
 * folder can be skipped. Written apart from both (the `fullres.ts` /
 * `removed.ts` pattern) so they cannot drift into two accounts of one folder.
 *
 * The two reasons need different sentences, and one sentence cannot serve both:
 *
 * - `device_output` — a bare `<T>/` sitting beside a `<T>_sub/`. On a Seestar
 *   that folder is the finished picture the scope made for itself, so skipping
 *   it is right; it is only worth mentioning when the files inside are *not*
 *   named like the device's output, i.e. when the scan may have walked past raw
 *   subs (the owner's `NGC 6888` of 4,815 files beside an `NGC 6888_SUB` of
 *   3,110 different ones).
 * - `temp_folder` — the folder's name is another stacking program's working
 *   directory. Skipped at scan time since v0.393.0, owner-decided 2026-09-08.
 *   Calling that "your Seestar's own finished picture" would simply be untrue.
 *
 * A `temp_folder` is mentioned however its files are named: the device-output
 * rule can be certain it is right, a name-pattern guess about someone else's
 * folder cannot — and being mentioned is what makes it recoverable, since the
 * "bring it in" button lives in this report.
 */

export type SkipReason = "device_output" | "temp_folder";

/** Read a reason off the wire, defaulting to the only case an older backend
 *  could produce (it sends no `reason` at all). */
export function skipReasonOf(raw: unknown): SkipReason {
  return raw === "temp_folder" ? "temp_folder" : "device_output";
}

export interface SkippedFolderCopyInput {
  name: string;
  nFiles: number;
  nUnrecognised: number;
  reason: SkipReason;
}

/** The Jobs page alert's title, named for what was actually skipped. The
 *  device-output wording is unchanged; only a scan that hit the new rule reads
 *  differently. */
export function skippedFoldersTitle(reasons: SkipReason[]): string {
  const hasDevice = reasons.some((r) => r === "device_output");
  const hasTemp = reasons.some((r) => r === "temp_folder");
  if (hasDevice && hasTemp) return "Some folders in your incoming folder were skipped";
  if (hasTemp) return "Another program's working folder was skipped";
  return "Some folders were skipped as your Seestar's own pictures";
}

/** The Library card's title. Deliberately *not* the same sentence as the Jobs
 *  alert's: the card exists to answer "are some of my subs missing from my
 *  pictures?", which is the right question for a folder that may hold the
 *  owner's own raw subs — and the wrong one for another program's scratch
 *  directory, where nothing of theirs is missing at all. */
export function skippedFoldersCardTitle(reasons: SkipReason[]): string {
  if (reasons.some((r) => r === "device_output")) {
    return "Some of your subs may not be reaching a picture";
  }
  return reasons.length === 1
    ? "A folder in your incoming folder was skipped"
    : "Some folders in your incoming folder were skipped";
}

/** The paragraph above the list: only the sentences that apply, in a fixed
 *  order so a scan that hits both reasons reads as one explanation. */
export function skippedFoldersExplainer(reasons: SkipReason[]): string {
  const parts: string[] = [];
  if (reasons.some((r) => r === "device_output")) {
    parts.push(
      "A folder named the same as one of your \"_sub\" folders is normally the "
      + "finished picture your Seestar made on the scope, so it isn't stacked "
      + "with your raw subs — but these hold files that don't look like your "
      + "Seestar's own pictures, so they may be subs that aren't reaching your "
      + "stack.",
    );
  }
  if (reasons.some((r) => r === "temp_folder")) {
    parts.push(
      "A working folder another stacking program leaves behind isn't one of "
      + "your capture folders, so it isn't brought in as a target.",
    );
  }
  parts.push("Nothing on disk was changed — nothing was deleted, moved or renamed.");
  return parts.join(" ");
}

/** The one line for a single skipped folder. */
export function skippedFolderLine(f: SkippedFolderCopyInput): string {
  const files = `${f.nFiles.toLocaleString()} file${f.nFiles === 1 ? "" : "s"}`;
  if (f.reason === "temp_folder") {
    return `${f.name}: ${files} skipped — another stacking program's working folder.`;
  }
  return `${f.name}: ${files} skipped, ${f.nUnrecognised.toLocaleString()} of them `
    + "not recognised as your Seestar's own picture.";
}
