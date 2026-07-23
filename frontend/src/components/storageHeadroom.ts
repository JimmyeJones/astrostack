// "How much longer can I keep imaging?" — turns the disk's free space and the
// library's recent growth rate into a plain-language headroom line for the
// Storage page. A number in gigabytes means nothing to a beginner; "room for
// about 18 more nights" does — and when space runs short it points at the safe
// thing to clear (the regenerable caches) before ingest silently starts losing
// a night's frames on a full disk.
//
// Pure and framework-free so it can be unit-tested in isolation.

export type HeadroomLevel = "healthy" | "short" | "unknown";

export interface Headroom {
  level: HeadroomLevel;
  /** Whole nights of imaging the free space should last, or null if unknown. */
  nightsLeft: number | null;
  /** One plain-language sentence for the Storage page. */
  sentence: string;
  /** When short: how much clearing regenerable caches would reclaim (else null). */
  reclaimHint: string | null;
}

function formatGB(bytes: number): string {
  const gb = bytes / 1024 ** 3;
  if (gb >= 10) return `${gb.toFixed(0)} GB`;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  const mb = bytes / 1024 ** 2;
  return `${mb.toFixed(0)} MB`;
}

// A short "per night" figure — GB when that reads naturally, else MB.
function formatRate(bytesPerNight: number): string {
  const gb = bytesPerNight / 1024 ** 3;
  if (gb >= 1) return `${gb.toFixed(1)} GB/night`;
  const mb = bytesPerNight / 1024 ** 2;
  return `${mb.toFixed(0)} MB/night`;
}

function nights(n: number): string {
  return n === 1 ? "1 more night" : `${n} more nights`;
}

/**
 * Compute the storage-headroom summary.
 *
 * - `freeBytes` — bytes free on the disk (null when the app couldn't read it).
 * - `nightlyBytes` — the estimated recent growth rate in bytes/night (null when
 *   there isn't enough capture history to estimate — see
 *   `estimate_nightly_bytes` on the server).
 * - `reclaimableCacheBytes` — total regenerable cache bytes across the library,
 *   used to suggest the safe thing to clear when space is short.
 *
 * Degrades gracefully to `level: "unknown"` whenever a projection can't be made
 * (no free reading, no rate, or a non-positive rate), showing just the free
 * figure rather than an invented estimate.
 */
export function storageHeadroom(args: {
  freeBytes: number | null | undefined;
  nightlyBytes: number | null | undefined;
  reclaimableCacheBytes: number;
}): Headroom {
  const { freeBytes, nightlyBytes, reclaimableCacheBytes } = args;

  if (freeBytes == null) {
    return {
      level: "unknown",
      nightsLeft: null,
      sentence: "Couldn't read how much disk space is free.",
      reclaimHint: null,
    };
  }

  const freeStr = formatGB(freeBytes);

  if (nightlyBytes == null || nightlyBytes <= 0) {
    return {
      level: "unknown",
      nightsLeft: null,
      sentence: `${freeStr} free — not enough imaging history yet to estimate how many nights that lasts.`,
      reclaimHint: null,
    };
  }

  const nightsLeft = Math.max(0, Math.floor(freeBytes / nightlyBytes));
  const rate = formatRate(nightlyBytes);
  const short = nightsLeft < 5;

  const reclaimHint =
    short && reclaimableCacheBytes > 0
      ? `Clearing regenerable caches would free about ${formatGB(reclaimableCacheBytes)} — the safe thing to clear first.`
      : null;

  if (short) {
    return {
      level: "short",
      nightsLeft,
      sentence:
        nightsLeft === 0
          ? `Almost out of space — ${freeStr} free, about ${rate} lately. Free up space before your next session.`
          : `Only room for about ${nights(nightsLeft)} of imaging before the disk fills (${freeStr} free, about ${rate} lately).`,
      reclaimHint,
    };
  }

  return {
    level: "healthy",
    nightsLeft,
    sentence: `Room for about ${nights(nightsLeft)} of imaging before the disk fills (${freeStr} free, about ${rate} lately).`,
    reclaimHint: null,
  };
}
