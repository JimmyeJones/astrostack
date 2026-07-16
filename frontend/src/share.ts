// Share a finished picture through the operating system's native share sheet
// (the Web Share API). Purely local: the browser/OS hands the image file to
// whatever app the user picks (Instagram, Messages, WhatsApp, …) — AstroStack
// makes no outbound network call of its own and needs no server-side hosting.
//
// Everything here is progressive enhancement. On a browser without file-level
// Web Share support (most desktop Chrome/Firefox today) the feature-detect
// returns false and the caller simply doesn't render a Share control, so the
// existing download menu keeps working unchanged.

/** Outcome of a share attempt, so the caller can decide whether to notify. */
export type ShareOutcome =
  | "shared" // the OS share sheet completed
  | "cancelled" // the user dismissed the share sheet (not an error)
  | "unsupported" // this browser can't share files (shouldn't reach here if gated)
  | "error"; // the picture couldn't be fetched or the share threw

/**
 * True when this browser can share image *files* through the OS share sheet.
 * We probe with an empty JPEG `File` because `navigator.canShare({ files })`
 * is the only reliable signal that file sharing (not just link/text sharing)
 * is available — several browsers expose `navigator.share` for text but reject
 * files. Any absence or throw → false (never render the control).
 */
export function canSharePictureFiles(): boolean {
  if (typeof navigator === "undefined") return false;
  if (typeof navigator.share !== "function") return false;
  if (typeof navigator.canShare !== "function") return false;
  try {
    const probe = new File([new Uint8Array()], "probe.jpg", { type: "image/jpeg" });
    return navigator.canShare({ files: [probe] });
  } catch {
    return false;
  }
}

/** True for the "user cancelled the share sheet" case, which is not an error. */
function isAbort(e: unknown): boolean {
  return !!e && typeof e === "object" && (e as { name?: string }).name === "AbortError";
}

/**
 * Fetch the picture at `url`, wrap it in a `File`, and hand it to the OS share
 * sheet with an optional caption. Never throws — always resolves to a
 * {@link ShareOutcome} so the caller can distinguish a genuine failure (worth a
 * message) from a user cancel (silent).
 */
export async function sharePicture(opts: {
  url: string;
  filename: string;
  title?: string;
  text?: string;
}): Promise<ShareOutcome> {
  if (typeof navigator === "undefined" || typeof navigator.share !== "function") {
    return "unsupported";
  }

  let file: File;
  try {
    const resp = await fetch(opts.url);
    if (!resp.ok) return "error";
    const blob = await resp.blob();
    file = new File([blob], opts.filename, { type: blob.type || "image/jpeg" });
  } catch {
    return "error";
  }

  const data: ShareData = { files: [file] };
  if (opts.title) data.title = opts.title;
  if (opts.text) data.text = opts.text;

  // If the concrete file can't be shared (e.g. too large for this OS), bail
  // cleanly rather than throwing a raw platform error at the user.
  if (typeof navigator.canShare === "function" && !navigator.canShare(data)) {
    return "unsupported";
  }

  try {
    await navigator.share(data);
    return "shared";
  } catch (e) {
    return isAbort(e) ? "cancelled" : "error";
  }
}

/** Lower-case, filesystem-safe slug for a share filename (no path separators). */
function slugify(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Build a friendly caption + filename for a shared picture from the target
 * name and (optionally) the capture/stack date, so the post arrives labelled.
 * A blank name falls back to a sensible generic so we never share `.jpg`.
 */
export function sharePictureText(
  name: string | null | undefined,
  dateLabel?: string | null,
): { title: string; text: string; filename: string } {
  const clean = (name ?? "").trim() || "My astrophoto";
  const date = (dateLabel ?? "").trim();
  const title = date ? `${clean} · ${date}` : clean;
  const text = date ? `${clean} — captured ${date}` : clean;
  const filename = `${slugify(clean) || "astrophoto"}.jpg`;
  return { title, text, filename };
}
