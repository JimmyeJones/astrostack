/**
 * "I've seen this one" — remembering that a self-hiding note was dismissed.
 *
 * Every dismissable note in this app stores a *signature* of the problem it is
 * about rather than a bare boolean, so dismissing one never suppresses a
 * genuinely different (or returning) one: the note reappears whenever the live
 * signature differs from the dismissed one, and self-clears once the problem is
 * fixed (no problem → no signature).
 *
 * The two accessors live here rather than being re-typed per note because a
 * `localStorage` read that isn't guarded is a page that breaks in private mode
 * or with storage disabled — a rule worth writing once. Both fail soft: a broken
 * store costs the user a note that won't stay dismissed, never a broken screen.
 */

export function loadDismissedSig(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function saveDismissedSig(key: string, sig: string): void {
  try {
    localStorage.setItem(key, sig);
  } catch {
    /* storage unavailable — the note just won't stay dismissed across reloads */
  }
}
