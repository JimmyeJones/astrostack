/** "Show and tell" — turn everything the app already knows into a list of
 * captioned slides for the full-screen slideshow.
 *
 * Every existing "enjoy/share" surface is either a *single* artefact (the
 * share JPEG, the wallpaper, the print export) or a *static* composite (the
 * montage poster, the gallery grid you click through). None of them is the
 * hands-off, room-filling thing a proud beginner actually wants when someone
 * says "show me what you've shot". This module is the data half of that: it
 * takes the ranked "My best pictures" wall and the finished Moon/Sun stills —
 * both already served by endpoints the app has — and flattens them into slides
 * that carry their own caption.
 *
 * Kept pure (no React, no DOM) so every caption shape, including the degraded
 * ones an old run produces, is pinned by a unit test.
 */

import type { BestPicture, VideoStill } from "./api/client";
import { formatIntegration, formatStampDate } from "./format";

/** One picture in the show, with everything needed to caption it. */
export interface Slide {
  /** Stable React key / test handle. */
  key: string;
  /** Preview URL to display. */
  src: string;
  /** The big line: what this is ("M31", "Moon"). */
  title: string;
  /** The "what am I looking at?" line, or "" when nothing is known — the
   *  caption then just names the picture rather than padding with filler. */
  fact: string;
  /** The small acquisition line ("2 May 2026 · 3.4 h · 500 frames"), or "". */
  meta: string;
  /** Where to go for more about this picture, when it has a page. Absent for a
   *  Moon/Sun still, which has no target of its own. */
  href?: string;
}

/** The plain-language "what is this?" line for a deep-sky picture: the catalog
 *  blurb when there is one, else a bare type ("A galaxy."), else "". Both
 *  fields are optional — an older backend sends neither. */
export function deepSkyFact(pic: BestPicture): string {
  const blurb = (pic.blurb ?? "").trim();
  if (blurb) return blurb;
  const type = (pic.object_type ?? "").trim();
  if (!type) return "";
  const article = /^[aeiou]/i.test(type) ? "An" : "A";
  return `${article} ${type}.`;
}

/** One-liners for the two things everybody in the room recognises. Kept here
 *  (not in the catalog) because a Moon/Sun still has no catalog entry at all —
 *  it isn't a target, it's a video capture. */
const VIDEO_FACTS: Record<string, string> = {
  lunar:
    "Our own Moon — close enough that a small telescope shows the craters, " +
    "mountains and lava plains on its surface.",
  solar:
    "The Sun — our nearest star. Its darker spots are cooler patches where " +
    "its magnetic field breaks through the surface.",
};

/** The acquisition line for a deep-sky picture: date, integration time and
 *  frame count, dropping any clause the run didn't record. */
export function deepSkyMeta(pic: BestPicture): string {
  const parts: string[] = [];
  const date = formatStampDate(pic.timestamp_utc);
  if (date) parts.push(date);
  if (
    pic.total_exposure_s != null &&
    Number.isFinite(pic.total_exposure_s) &&
    pic.total_exposure_s > 0
  ) {
    parts.push(formatIntegration(pic.total_exposure_s));
  }
  if (Number.isFinite(pic.n_frames_used) && pic.n_frames_used > 0) {
    parts.push(`${pic.n_frames_used} ${pic.n_frames_used === 1 ? "frame" : "frames"}`);
  }
  return parts.join(" · ");
}

/**
 * The show's running order.
 *
 * The deep-sky wall comes first, in the order the portfolio ranker already put
 * it (best first — including any picture the user pinned as a cover, which that
 * ranking floats to the top), then the Moon/Sun stills newest-first. One fixed,
 * explainable order beats a clever interleave nobody can predict, and the show
 * loops anyway. A picture with no preview URL is skipped rather than shown as a
 * broken frame.
 */
export function buildSlides(
  best: BestPicture[] | undefined,
  videos: VideoStill[] | undefined,
): Slide[] {
  const slides: Slide[] = [];
  for (const pic of best ?? []) {
    if (!pic.preview_url) continue;
    slides.push({
      key: `run:${pic.safe}:${pic.run_id}`,
      src: pic.preview_url,
      title: pic.target_name,
      fact: deepSkyFact(pic),
      meta: deepSkyMeta(pic),
      href: `/targets/${pic.safe}/history`,
    });
  }
  for (const v of videos ?? []) {
    if (!v.preview_url) continue;
    const parts: string[] = [];
    const date = formatStampDate(v.created_utc);
    if (date) parts.push(date);
    if (Number.isFinite(v.n_stacked) && v.n_stacked > 0) {
      parts.push(`${v.n_stacked} ${v.n_stacked === 1 ? "frame" : "frames"} stacked`);
    }
    slides.push({
      key: `video:${v.capture_id}`,
      src: v.preview_url,
      title: v.label,
      fact: VIDEO_FACTS[v.kind] ?? "",
      meta: parts.join(" · "),
    });
  }
  return slides;
}

/** How long each picture holds the screen. Long enough to actually look at it
 *  and read the caption out loud, short enough that a small collection doesn't
 *  feel stuck. */
export const SLIDE_MS = 8000;

/** The next index in the loop — or the same index when there is nothing to
 *  advance to, so a one-picture show simply rests. */
export function nextIndex(current: number, count: number, step = 1): number {
  if (count <= 1) return 0;
  return ((current + step) % count + count) % count;
}
