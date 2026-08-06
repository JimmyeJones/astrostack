/**
 * Cache-busting `src` for a saved Moon/Sun still.
 *
 * The still lives at a fixed URL (`/api/videos/<id>/preview.png`) and is
 * rewritten in place when it is cropped or restored — so the picture can change
 * while neither its address nor its "made at" timestamp does. Without a buster
 * the browser happily keeps showing the version it already has, and the user
 * clicks "Crop it", sees the toast, and looks at the uncropped picture.
 *
 * Keying on the *size* as well as the timestamp is enough: cropping is the only
 * thing that rewrites a still, and it always changes the size (a crop that
 * trimmed nothing is refused).
 */
export function videoPreviewSrc(
  still: { preview_url: string; created_utc: string; width?: number; height?: number },
): string {
  const size = still.width && still.height ? `${still.width}x${still.height}` : "";
  const key = size ? `${still.created_utc}-${size}` : still.created_utc;
  return `${still.preview_url}?t=${encodeURIComponent(key)}`;
}
