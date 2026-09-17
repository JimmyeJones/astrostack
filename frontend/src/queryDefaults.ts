/** The running app's TanStack Query defaults, in one importable place.
 *
 * These lived inline in `main.tsx`, which a test cannot import (it renders the
 * app on import). So a test that wants to assert something about *caching* had
 * to hand-write its own client, and hand-written clients get the defaults —
 * `staleTime: 0` — which is not what anyone runs. A claim like "clicking Stack
 * from the Target page costs no request" is true of the app and false of the
 * bare default, so the test has to be given the real numbers rather than a
 * plausible copy of them.
 */
import type { DefaultOptions } from "@tanstack/react-query";

/** How long a fetched answer is served without going back to the server.
 *
 * Long enough to cover moving between two screens that ask the same question —
 * the Target page's frames table and the Stack form's pre-flight guards both
 * read one target's complete sub list, which is 531 bytes a row on the wire and
 * 19.1 MB on the owner's deepest target — and short enough that a screen left
 * open is not looking at yesterday.
 */
export const QUERY_STALE_TIME_MS = 10_000;

export const QUERY_DEFAULTS: DefaultOptions = {
  queries: { refetchOnWindowFocus: false, staleTime: QUERY_STALE_TIME_MS },
};
