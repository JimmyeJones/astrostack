/** The wording for the optional **read-only token**, in one place.
 *
 * The token is the app's only second credential, and the whole reason it exists
 * is that someone has to be able to trust its limits: the owner hands it to a
 * monitoring script or an assistant, and has to know what that thing can and
 * cannot then do. So the sentence that says so is written once here rather than
 * inline next to the button — the `fullres.ts` / `removed.ts` pattern, so a
 * second surface can never come to describe one credential two ways.
 *
 * The allowlist named below is the backend's `_READONLY_GET_PATHS`
 * (`webapp/main.py`), and `readonlyAllowedReads` is pinned against it by
 * `tests/test_readonly_paths_mirror.py` — a wrong list here would be worse than
 * no list, because it is a promise about a secret.
 */

/** What the token can read, in the order a person would ask about them. */
export const readonlyAllowedReads = [
  "health",
  "logs",
  "jobs",
  "stats",
  "the target list",
] as const;

/** What the token is for, and — the half that matters — what it can't do. */
export function readonlyTokenBlurb(): string {
  return (
    `For something that should only ever look: a monitoring script, or an ` +
    `assistant checking on your install. It can read ${readonlyAllowedReads
      .slice(0, -1)
      .join(", ")} and ${readonlyAllowedReads[readonlyAllowedReads.length - 1]} ` +
    `— and nothing else. It ` +
    `cannot stack, edit a picture, change a setting, upload, or delete ` +
    `anything, even with your password's own username.`
  );
}

/** A ready-to-paste check that the token works, using the caller's own address
 * so it is correct for this install rather than for localhost. `origin` is
 * whatever `window.location.origin` gives; the token is left as a placeholder
 * because it is only ever shown once and pasting it into a shell history is not
 * something to encourage. */
export function readonlyCurlExample(username: string, origin: string): string {
  const base = origin.replace(/\/+$/, "");
  return `curl -u ${username}:YOUR_TOKEN ${base}/api/logs`;
}
