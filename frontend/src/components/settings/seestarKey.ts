/**
 * The Seestar key box's words, free of React so each one is tested as a value
 * (⭐ Seestar-page upgrade, slice 1).
 *
 * The API only ever says whether a key is installed — the key itself is never
 * sent back — so everything the box can say is derived from that one answer.
 */
import type { SeestarKeyStatus } from "../../api/client";

/** One plain sentence on what the key does for the owner right now. */
export function seestarKeyLine(status: SeestarKeyStatus | undefined): string {
  if (!status) return "Checking for a Seestar key…";
  if (status.installed) {
    return "Your Seestar key is installed. AstroStack keeps it private: it is never "
      + "shown again, sent anywhere or included in a settings backup.";
  }
  if (status.problem) return status.problem;
  return "No key yet, so AstroStack can only listen to what the telescope announces "
    + "on its own. Newer Seestar firmware answers questions and commands only from "
    + "an app that has its key file.";
}

/** The server's refusal without the `400: ` prefix `req` puts on every error. */
export function seestarKeyError(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err);
  return raw.replace(/^\d{3}:\s*/, "");
}
