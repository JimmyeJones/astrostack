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
