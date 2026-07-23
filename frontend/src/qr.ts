import qrcode from "qrcode-generator";

/**
 * Helpers for the "Scan to get it on your phone" QR feature.
 *
 * AstroStack runs headless on a NAS/Docker box and the beginner views results
 * on a laptop on the LAN — but the picture they want to post lives on their
 * *phone*. A QR their camera reads in one second closes that loop with no
 * typing and no account: it just encodes the absolute LAN URL of the picture's
 * download endpoint, which the phone (on the same Wi-Fi) opens and saves.
 *
 * Everything here is pure and client-side — the QR is built in the browser from
 * `window.location`, so nothing leaves the LAN and there is no server dependency.
 */

/**
 * Resolve a possibly-relative download path to an absolute URL the phone can
 * reach on the LAN.
 *
 * Uses the origin the user already typed (`window.location.origin` by default),
 * **not** a server-guessed hostname, so it works behind Docker/reverse-proxy
 * without the server knowing its own external name. An already-absolute
 * `http(s)://…` path is returned unchanged; a leading/trailing slash mismatch
 * between origin and path is normalised so we never emit a `//` join.
 */
export function absoluteLanUrl(
  path: string,
  origin: string = typeof window !== "undefined" ? window.location.origin : "",
): string {
  if (/^https?:\/\//i.test(path)) return path; // already absolute — leave it
  if (!origin) return path; // no origin to anchor to (SSR/tests) — best effort
  return origin.replace(/\/+$/, "") + "/" + path.replace(/^\/+/, "");
}

/** A rendered QR code as a square grid of dark/light modules (no quiet zone). */
export interface QrMatrix {
  /** Module count per side. */
  size: number;
  /** True when the module at (row, col) is dark (foreground). */
  isDark: (row: number, col: number) => boolean;
}

/**
 * Build a byte-mode QR matrix for `text` at error-correction level M and the
 * smallest version that fits (`typeNumber = 0` auto-selects). URLs are ASCII,
 * so byte encoding is unambiguous. Throws only if the text is too long for the
 * largest QR version — callers guard with a self-hide, so a picture URL (well
 * under 100 chars) always encodes.
 */
export function qrMatrix(text: string): QrMatrix {
  const qr = qrcode(0, "M");
  qr.addData(text);
  qr.make();
  const size = qr.getModuleCount();
  return { size, isDark: (r, c) => qr.isDark(r, c) };
}
