// The one place that says "your new frames haven't been imported yet, and this
// is what's holding them up".
//
// AstroStack runs one job at a time on purpose (a serial worker — two stacks at
// once on a RAM-capped NAS is an OOM kill), so a job that runs for days holds
// the queue for days. That is visible and fine for a job someone started. The
// import job is the one nobody starts by hand: the watcher enqueues it, and
// while it waits the app looks perfectly healthy — every target still shows the
// frame count it had before, and a frame that was never imported has no QC row
// and no reject reason, so there is nowhere in the record it can be *seen* to be
// missing. On the owner's own box that came to 2,259 subs across two nights
// sitting on disk for eleven days with nothing anywhere saying so.
//
// Two surfaces need the same sentence — the Jobs page, where the queue is, and
// the Dashboard's notice board, which is the screen the owner actually opens —
// so the wording lives here rather than in either of them (the `fullres.ts`
// arrangement, so two screens cannot make two claims about one queue).

import type { ImportWaiting } from "./api/client";

/** A wait, in the largest unit that still reads naturally. Hours below a day
 * (the Jobs page's own scale), days beyond that — "70.4 h" is a number a reader
 * has to divide, and the whole point of the sentence is that it lands. */
export function waitedFor(hours: number | null | undefined): string {
  if (hours == null || !Number.isFinite(hours) || hours <= 0) return "";
  if (hours < 1) return "under an hour";
  if (hours < 24) {
    const h = hours < 10 ? Number(hours.toFixed(1)) : Math.round(hours);
    return `${h} ${h === 1 ? "hour" : "hours"}`;
  }
  const d = Math.round(hours / 24);
  return `${d} ${d === 1 ? "day" : "days"}`;
}

export interface ImportWaitingNote {
  title: string;
  /** Why it is waiting, in one sentence — names the holder when there is one. */
  body: string;
  /** What is true about the frames themselves. Always said: the first thing a
   * beginner reading "your frames aren't imported" needs to know is that they
   * are not lost. */
  reassurance: string;
}

/** The note for a stuck import, or `null` when nothing is stuck — which is the
 * ordinary answer, and renders nothing rather than an "all fine" banner.
 *
 * `kindLabel` translates the holder's engine job kind ("reprocess_all") into the
 * plain name the Jobs page already shows; pass `jobKindLabel`. */
export function importWaitingNote(
  waiting: ImportWaiting | null | undefined,
  kindLabel: (kind: string) => string,
): ImportWaitingNote | null {
  if (!waiting) return null;
  const waited = waitedFor(waiting.waiting_hours);
  if (!waited) return null;

  const title = waiting.n_waiting > 1
    ? `${waiting.n_waiting} imports are waiting to run`
    : "New frames are waiting to be imported";

  // Three cases, and the third is the worst one: nothing is running at all, so
  // the queue is not busy — it is stalled, and "wait for it to finish" would be
  // advice about a job that does not exist.
  let body: string;
  if (!waiting.holder_kind) {
    body = `AstroStack runs one job at a time, and importing your new frames has been `
      + `waiting ${waited} for its turn — but nothing is running. Restarting AstroStack `
      + `should let it start.`;
  } else {
    const holder = waiting.holder_target
      ? `“${kindLabel(waiting.holder_kind)}” on ${waiting.holder_target}`
      : `“${kindLabel(waiting.holder_kind)}”`;
    const forHow = waitedFor(waiting.holder_hours);
    body = `AstroStack runs one job at a time, and importing your new frames has been `
      + `waiting ${waited} behind ${holder}`
      + (forHow ? `, which has been running for ${forHow}` : "")
      + `. Let it finish, or cancel it on the Jobs page to let the import through.`;
  }

  return {
    title,
    body,
    reassurance: "Nothing is lost — your subs are safe in your incoming folder — but "
      + "anything shot since then isn't in your library yet, so its targets will look "
      + "shallower than they are.",
  };
}

/** Whether a stuck-import note is speaking right now.
 *
 * Deliberately the *same* predicate `importWaitingNote` returns non-null on,
 * rather than a second reading of the same field: the only honest way for one
 * note to defer to another is to ask the identical question. A backend with no
 * such endpoint (or a failed read) answers `false`, which is the state every
 * caller already renders for.
 */
export function importIsWaiting(waiting: ImportWaiting | null | undefined): boolean {
  return !!waiting && !!waitedFor(waiting.waiting_hours);
}

export interface IncomingLagCause {
  /** Why those files are still on disk, in one sentence. */
  sentence: string;
  /** Whether starting a scan is what actually picks them up. `false` while an
   *  import is already queued: the worker is serial, so a second scan only
   *  joins the back of the queue the first one is already at the front of. */
  scanHelps: boolean;
  /** Said only when there is no queued import to point at — the reassurance
   *  `StuckImportNote` would otherwise be saying an inch higher up the same
   *  notice board. */
  reassurance: string;
}

/** What the incoming-lag note should say about *why* files are still waiting.
 *
 * The note used to guess — *"this usually means an import is still waiting its
 * turn behind another job"* — while its sibling directly above it on the same
 * notice board said exactly that as a **measured fact with a duration**, and
 * then offered the opposite action ("Scan incoming now" against "cancel it on
 * the Jobs page to let the import through"). Both notes fire on the same event
 * (they were built from one observer report), both are `warning`, and the board
 * keeps two notes inline — so the owner's own case is precisely the one where a
 * beginner reads a guess, a fact and two contradictory instructions at once.
 *
 * So the cause is *read* rather than guessed, from the queue health the sibling
 * has already fetched under the same query key. Neither branch invents
 * anything: with an import queued the wait is quoted from the queue; with
 * nothing queued the old sentence was simply wrong about the cause, and a scan
 * is genuinely the right retry.
 */
export function incomingLagCause(
  waiting: ImportWaiting | null | undefined,
): IncomingLagCause {
  if (!importIsWaiting(waiting)) {
    return {
      sentence: "AstroStack normally imports new files by itself within a few minutes, "
        + "and nothing is queued waiting to run — so a scan is what picks these up. "
        + "Starting one is safe to do at any time; it only ever adds what is missing.",
      scanHelps: true,
      reassurance: "Nothing is lost — your subs are safe exactly where they are, and "
        + "AstroStack never writes to that folder.",
    };
  }
  const waited = waitedFor(waiting!.waiting_hours);
  return {
    sentence: `An import is already queued and has been waiting ${waited} for `
      + "AstroStack's one job slot, so these are on their way in rather than "
      + "overlooked. Starting another scan would only add a second job behind it.",
    scanHelps: false,
    // Withheld on purpose: the note above is already saying "nothing is lost",
    // and two notes are all the board keeps inline — so repeating it here would
    // spend half of what the owner reads on one sentence said twice.
    reassurance: "",
  };
}

export interface IncomingLagUnreadable {
  /** True when *every* waiting file is one the app cannot read — i.e. nothing is
   *  actually on its way in, and the note must not offer a scan. */
  all: boolean;
  /** The note's title, replacing the "haven't been imported yet" one. Null when
   *  only some of the waiting files are damaged: the rest genuinely are waiting,
   *  so that title is still the true headline. */
  title: string | null;
  /** The sentence that says what these files are and what to do about them. */
  sentence: string;
}

/** The damaged-file half of the incoming-lag note.
 *
 * The lag note compares files on disk with frame rows, which is exactly the
 * right question and cannot see *why* a row is missing. It was written for the
 * cause that fixes itself — a stalled or queued import — and says so: *"haven't
 * been imported yet"*, with a **Scan incoming now** button. A file the app has
 * opened and cannot read is missing its row **permanently**, so on that file the
 * note is promising a fix that no scan can deliver, and goes on promising it for
 * as long as the file sits there. On the owner's own library that is six files
 * across five folders, since May.
 *
 * Since v0.452.0 the Jobs page says plainly that those files could not be read,
 * which turns a wrong sentence into a contradiction: two of the app's own
 * screens, about the same six files, disagreeing about whether anything is
 * waiting. This is the half that makes them agree.
 *
 * Returns null when nothing is damaged — every healthy install, and every
 * install that has not scanned since the count existed — so the note is byte-for
 * byte what it was.
 */
export function incomingLagUnreadable(
  nWaiting: number, nUnreadable: number | null | undefined,
): IncomingLagUnreadable | null {
  const bad = Math.max(0, Math.min(Number(nUnreadable ?? 0) || 0, nWaiting));
  if (bad <= 0) return null;
  const all = bad >= nWaiting;
  // Said in both branches, because it is the actionable half and a beginner
  // reading "can't be read" needs to know it is a copy problem and not a
  // verdict on their night.
  const advice = "The usual cause is a copy that didn't finish. Copying "
    + (bad === 1 ? "it" : "them") + " over again from your Seestar normally fixes "
    + (bad === 1 ? "it" : "them") + "; if not, "
    + (bad === 1 ? "the file is" : "the files are")
    + " damaged and safe to delete. Nothing else is affected, and AstroStack "
    + "never changes anything in that folder.";
  if (all) {
    return {
      all: true,
      title: nWaiting === 1
        ? "A sub in your incoming folder can't be read"
        : `${nWaiting.toLocaleString()} subs in your incoming folder can't be read`,
      sentence: (bad === 1 ? "AstroStack has opened it and " : "AstroStack has opened them and ")
        + "found no picture data inside, so "
        + (bad === 1 ? "it can't" : "they can't")
        + " be imported — a scan won't help, and every scan has already tried. "
        + advice + " The last scan's result on the Jobs page names the files.",
    };
  }
  return {
    all: false,
    // The headline stays as it was: most of these files really are waiting.
    title: null,
    sentence: `${bad.toLocaleString()} of these can't be read at all — AstroStack `
      + "has opened " + (bad === 1 ? "it" : "them")
      + " and found no picture data inside, so no scan will ever import "
      + (bad === 1 ? "it" : "them") + ". " + advice
      + " The last scan's result on the Jobs page names the files.",
  };
}
