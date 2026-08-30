import { useState } from "react";
import { Loader, Menu } from "@mantine/core";
import { notifications } from "@mantine/notifications";

/**
 * A `Menu.Item` that downloads a file the server has to **build** first.
 *
 * A plain `<a download>` is free to offer — no request to decide whether the
 * item belongs there, no state — which is why the lazily-built artifacts (the
 * zoom clip, and anything like it) are offered that way. The cost is the first
 * tap: the server spends a second or three rendering before a byte comes back,
 * and a browser shows a download only once it *starts*. So the first tap looks
 * like nothing happened, which is exactly the kind of nothing that gets clicked
 * three times.
 *
 * This keeps the plain link's zero-cost offer and adds the missing feedback: it
 * fetches the file itself, holds the menu open with a spinner and a "building
 * it now" line while the request is in flight, then hands the finished blob to
 * the browser as a download. Every later tap is a file read on the server, so
 * the wait is a first-use-only thing the user sees explained rather than
 * guessed at.
 *
 * Progressive enhancement: a browser with no `fetch`/`createObjectURL` path
 * renders exactly today's plain `<a download>` link and behaves exactly as it
 * did — this can only add feedback, never take the download away.
 */
/**
 * The filename the server named the file, or `fallback` when it didn't say.
 *
 * A plain `<a download>` lets the server's `Content-Disposition` name the file;
 * fetching the blob ourselves takes that away, and guessing is not safe here —
 * the zoom clip is a WEBP *or* an APNG depending on what Pillow can encode, so
 * a hardcoded extension would mislabel half the downloads. Pure/testable.
 */
export function filenameFromDisposition(
  header: string | null, fallback: string,
): string {
  if (!header) return fallback;
  // RFC 5987 `filename*=UTF-8''name` wins over the plain `filename="name"`.
  const ext = /filename\*=\s*UTF-8''([^;]+)/i.exec(header);
  if (ext) {
    try {
      const name = decodeURIComponent(ext[1].trim());
      if (name) return name;
    } catch {
      // A malformed encoding is not worth failing a download over.
    }
  }
  const plain = /filename=\s*"?([^";]+)"?/i.exec(header);
  const name = plain?.[1]?.trim();
  return name || fallback;
}

export function DownloadMenuItem({
  url,
  filename,
  icon,
  label,
  hint,
  busyHint = "Building it now — this takes a few seconds the first time.",
  errorMessage = "Couldn't build that file — please try again.",
  hintStyle,
}: {
  /** The file to download. */
  url: string;
  /** Filename to fall back on when the server doesn't name the file itself. */
  filename: string;
  /** Leading icon, shown when idle (a spinner replaces it while building). */
  icon: React.ReactNode;
  label: string;
  /** Second line under the label, in the menu's usual hint style. */
  hint?: string;
  /** Replaces `hint` while the file is being built. */
  busyHint?: string;
  errorMessage?: string;
  /** The page's `MENU_HINT` style, so the hint line matches its neighbours. */
  hintStyle?: React.CSSProperties;
}) {
  // Feature-detect once at mount (stable per browser).
  const [canFetchBlob] = useState(
    () => typeof fetch === "function"
      && typeof URL !== "undefined"
      && typeof URL.createObjectURL === "function",
  );
  const [busy, setBusy] = useState(false);

  const body = (
    <>
      {label}
      {(busy ? busyHint : hint) && (
        <span style={hintStyle}>{busy ? busyHint : hint}</span>
      )}
    </>
  );

  if (!canFetchBlob) {
    return (
      <Menu.Item leftSection={icon} component="a" href={url} download>
        {body}
      </Menu.Item>
    );
  }

  const download = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const name = filenameFromDisposition(
        res.headers.get("content-disposition"), filename);
      const blobUrl = URL.createObjectURL(await res.blob());
      try {
        const a = document.createElement("a");
        a.href = blobUrl;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
      } finally {
        // Give the browser a tick to pick the blob up before dropping it.
        setTimeout(() => URL.revokeObjectURL(blobUrl), 10_000);
      }
    } catch {
      notifications.show({ message: errorMessage, color: "red" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Menu.Item
      // Keep the menu open while we build, or the spinner unmounts with it and
      // the user is back to staring at nothing.
      closeMenuOnClick={false}
      leftSection={busy ? <Loader size={14} /> : icon}
      onClick={download}
      aria-busy={busy || undefined}
    >
      {body}
    </Menu.Item>
  );
}
