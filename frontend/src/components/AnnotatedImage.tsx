import { useEffect, useRef, useState } from "react";
import type { FieldObject, ScaleBar, SkyDirections } from "../api/client";

/**
 * "What's in this picture?" — overlay named catalog objects on a finished stack.
 *
 * The object pixel coordinates (`x_px`/`y_px`) live on the stack's own FITS grid
 * (`imgWidth` × `imgHeight`). The preview `<img>` is shown with `object-fit:
 * contain` inside a box of a possibly different aspect ratio, so it is letterboxed.
 * :func:`objectMarkerLayout` reproduces that exact contain-fit transform, so a
 * label lands on the object regardless of the box size — and re-runs on resize.
 */

export interface Marker {
  object: FieldObject;
  /** CSS pixels from the box's top-left, at the object's centre. */
  left: number;
  top: number;
  /** True when the centre lands within the rendered (letterbox-trimmed) image. */
  visible: boolean;
  /**
   * Normalised distance from the picture's centre — 0 at the centre, ~1.41 at a
   * corner. Exactly the quantity `describeFieldObjects` sorts its read-out on,
   * so "how notable is this object?" is answered the same way in the list under
   * the picture and in the labels drawn on it. Used by
   * :func:`deconflictMarkers` to decide who keeps a label when a field is too
   * crowded to give one to everybody.
   */
  r: number;
}

/**
 * Where each object's label lands inside a `boxW` × `boxH` box that shows an
 * `imgWidth` × `imgHeight` image with `object-fit: contain`. Pure so the geometry
 * is unit-testable without a DOM. Returns an empty list when any dimension is
 * non-positive (nothing can be placed yet).
 */
export function objectMarkerLayout(
  objects: FieldObject[],
  imgWidth: number,
  imgHeight: number,
  boxW: number,
  boxH: number,
): Marker[] {
  if (imgWidth <= 0 || imgHeight <= 0 || boxW <= 0 || boxH <= 0) return [];
  // contain-fit: the image scales uniformly to fit inside the box, centred.
  const scale = Math.min(boxW / imgWidth, boxH / imgHeight);
  const renderW = imgWidth * scale;
  const renderH = imgHeight * scale;
  const offsetX = (boxW - renderW) / 2;
  const offsetY = (boxH - renderH) / 2;
  return objects.map((o) => {
    const left = offsetX + o.x_px * scale;
    const top = offsetY + o.y_px * scale;
    const visible =
      left >= offsetX && left <= offsetX + renderW &&
      top >= offsetY && top <= offsetY + renderH;
    const nx = (o.x_px - imgWidth / 2) / (imgWidth / 2);
    const ny = (o.y_px - imgHeight / 2) / (imgHeight / 2);
    return { object: o, left, top, visible, r: Math.hypot(nx, ny) };
  });
}

/* ---- keeping a crowded field readable ---------------------------------- */

/** Radius of the marker dot, and the gap between it and its label chip. */
const DOT_R = 4;
const CHIP_GAP = 2;
/** Chip metrics, matching the rendered chip's font-size/padding closely enough
 *  to test overlap. Deliberately a *pure estimate* rather than a DOM measurement:
 *  the layout has to be decidable before anything is rendered, and being a pixel
 *  or two generous only makes the spacing safer. */
const CHIP_H = 15;
const CHIP_CHAR_PX = 6.2;
const CHIP_PAD_PX = 10;
/** Breathing room required between two chips before they count as "apart". */
const CHIP_MARGIN = 2;
/** How many rings out from the dot a chip may be pushed before its label is
 *  given up. Three is enough to place a genuinely crowded pile without a chip
 *  ending up so far from its dot that it reads as pointing at something else. */
const CHIP_RINGS = 3;
/** One label per this much box area, so the same field labels sensibly on a
 *  180 px History card, a 260 px Target card and a full-screen lightbox. */
const AREA_PER_LABEL = 22_000;
const MIN_LABELS = 3;
const MAX_LABELS = 12;

/** A marker whose label chip has been given a place that nothing else wants. */
export interface PlacedMarker extends Marker {
  /** CSS px offset of the chip's centre from the dot. Never moves the dot. */
  labelDx: number;
  labelDy: number;
}

interface Rect { x0: number; y0: number; x1: number; y1: number }

function chipWidth(label: string): number {
  return label.length * CHIP_CHAR_PX + CHIP_PAD_PX;
}

function chipRect(m: Marker, dx: number, dy: number, w: number): Rect {
  const cx = m.left + dx;
  const cy = m.top + dy;
  return { x0: cx - w / 2, y0: cy - CHIP_H / 2, x1: cx + w / 2, y1: cy + CHIP_H / 2 };
}

function overlaps(a: Rect, b: Rect): boolean {
  return a.x0 < b.x1 + CHIP_MARGIN && b.x0 < a.x1 + CHIP_MARGIN
    && a.y0 < b.y1 + CHIP_MARGIN && b.y0 < a.y1 + CHIP_MARGIN;
}

/** How many labels a box this size can carry before it stops being readable. */
export function labelBudget(boxW: number, boxH: number): number {
  if (boxW <= 0 || boxH <= 0) return 0;
  const n = Math.floor((boxW * boxH) / AREA_PER_LABEL);
  return Math.max(MIN_LABELS, Math.min(MAX_LABELS, n));
}

/**
 * Give each object's label a spot of its own, and drop the ones a crowded field
 * has no room for.
 *
 * Drawing every label dead-centre on its object — which is what this used to do
 * — turns a rich field into an unreadable pile exactly where the labels are most
 * interesting: point a 3° frame at the Sword of Orion or the Virgo cluster and
 * several chips land within a few pixels of each other on a 260 px card.
 *
 * Three rules:
 *   * **The dot never moves.** Only its chip is nudged, or the label stops
 *     pointing at its object. Positions are tried below/above first (chips are
 *     wide, so stacking them vertically collides least), then left/right, each
 *     time preferring the direction with more room inside the box.
 *   * **Nearest the centre wins.** Ordering is `Marker.r` — the same "how
 *     notable is this?" proxy the text read-out under the picture already sorts
 *     on — so when there isn't room for everybody, the objects a beginner is
 *     actually looking at keep their names.
 *   * **Nothing is lost, it moves.** A dropped label's object is still named in
 *     that read-out, which both consumers render.
 *
 * Pure and box-size-driven, so it is unit-testable and behaves consistently
 * from a small card to a lightbox.
 */
export function deconflictMarkers(
  markers: Marker[], boxW: number, boxH: number,
): PlacedMarker[] {
  if (boxW <= 0 || boxH <= 0) return [];
  const budget = labelBudget(boxW, boxH);
  const ordered = markers.filter((m) => m.visible).slice()
    .sort((a, b) => a.r - b.r);

  const taken: Rect[] = [];
  const placed: PlacedMarker[] = [];
  for (const m of ordered) {
    if (placed.length >= budget) break;
    const w = chipWidth(objectLabel(m.object));
    const vOff = DOT_R + CHIP_GAP + CHIP_H / 2;
    const hOff = DOT_R + CHIP_GAP + w / 2;
    // Prefer the side of the dot with more room left in the box, and try
    // straight below/above before sideways — chips are wide, so stacking them
    // vertically collides least. Each direction is then tried further out, so a
    // notable object in a genuine pile still finds somewhere rather than losing
    // its name to a less interesting neighbour that happened to be luckier.
    const vs = m.top < boxH / 2 ? [1, -1] : [-1, 1];
    const hs = m.left < boxW / 2 ? [1, -1] : [-1, 1];
    const dirs: [number, number][] = [
      [0, vs[0]], [0, vs[1]], [hs[0], 0], [hs[1], 0],
      [hs[0], vs[0]], [hs[1], vs[0]], [hs[0], vs[1]], [hs[1], vs[1]],
    ];
    const candidates: [number, number][] = [];
    for (let step = 0; step < CHIP_RINGS; step++) {
      for (const [hx, vy] of dirs) {
        candidates.push([
          hx === 0 ? 0 : hx * (hOff + (step * (w + CHIP_MARGIN)) / 2),
          vy === 0 ? 0 : vy * (vOff + step * (CHIP_H + CHIP_MARGIN)),
        ]);
      }
    }
    for (const [dx, dy] of candidates) {
      const rect = chipRect(m, dx, dy, w);
      if (rect.x0 < 0 || rect.y0 < 0 || rect.x1 > boxW || rect.y1 > boxH) continue;
      if (taken.some((t) => overlaps(t, rect))) continue;
      taken.push(rect);
      placed.push({ ...m, labelDx: dx, labelDy: dy });
      break;
    }
    // No candidate fits: this object's label is one the read-out carries instead.
  }
  return placed;
}

/** Fractional bounds of the stack canvas a stored preview shows (`run.preview_crop`). */
export interface PreviewCropBounds { x0: number; y0: number; x1: number; y1: number }

/**
 * Re-express the annotations payload on a *cropped* picture's own grid.
 *
 * Object pixels and the scale bar come off the run's un-cropped FITS grid, but
 * the one-click "Process target" auto-edit rewrites the stored preview through a
 * recipe that ends with a border trim — so drawn on those bytes as-is, every pin
 * lands off by the trim's offset and the bar claims a length it doesn't have.
 * Shifting the pixels into the crop and re-basing the bar's `fraction` on the
 * narrower picture fixes both, exactly.
 *
 * Pure, and a no-op (same values, same references) when there is no crop — which
 * is every ordinary run, and every moment the *live* Adjust render is on screen
 * instead of the stored bytes. Objects whose centre falls outside the trim are
 * dropped (they're no longer in the picture), and a bar that would no longer fit
 * is dropped rather than drawn overflowing.
 */
export function croppedAnnotationView(
  crop: PreviewCropBounds | null | undefined,
  objects: FieldObject[],
  scaleBar: ScaleBar | null,
  width: number,
  height: number,
): { objects: FieldObject[]; scaleBar: ScaleBar | null; width: number; height: number } {
  const same = { objects, scaleBar, width, height };
  if (!crop || width <= 0 || height <= 0) return same;
  const x0 = Math.min(Math.max(Math.round(crop.x0 * width), 0), width - 1);
  const y0 = Math.min(Math.max(Math.round(crop.y0 * height), 0), height - 1);
  const x1 = Math.max(Math.min(Math.round(crop.x1 * width), width), x0 + 1);
  const y1 = Math.max(Math.min(Math.round(crop.y1 * height), height), y0 + 1);
  const w = x1 - x0;
  const h = y1 - y0;
  if (w === width && h === height) return same;
  const shifted = objects
    .map((o) => ({ ...o, x_px: o.x_px - x0, y_px: o.y_px - y0 }))
    .filter((o) => o.x_px >= 0 && o.x_px < w && o.y_px >= 0 && o.y_px < h);
  let bar: ScaleBar | null = null;
  if (scaleBar) {
    // The bar's on-sky length is unchanged, so it covers a *larger* share of the
    // narrower picture. Past ~90 % it would run off the edge — drop it instead.
    const fraction = (scaleBar.fraction * width) / w;
    bar = fraction > 0.9 ? null : { ...scaleBar, fraction };
  }
  return { objects: shifted, scaleBar: bar, width: w, height: h };
}

/** A friendly one-word label for an object: its name if it has one, else its id. */
export function objectLabel(o: FieldObject): string {
  return o.name && o.name.trim() ? o.name : o.catalog_id;
}

/**
 * On-screen geometry for the scale bar over a contain-fit image. The bar's
 * `fraction` is a share of the *image* width, so its on-screen length is
 * `fraction · renderW` (the letterbox-trimmed rendered width). Returns `null`
 * when nothing can be placed yet (no bar, or a zero-size box). Pure so it's
 * unit-testable without a DOM.
 */
export function scaleBarLayout(
  bar: ScaleBar | null | undefined,
  imgWidth: number,
  imgHeight: number,
  boxW: number,
  boxH: number,
): { widthPx: number } | null {
  if (!bar || imgWidth <= 0 || imgHeight <= 0 || boxW <= 0 || boxH <= 0) return null;
  const scale = Math.min(boxW / imgWidth, boxH / imgHeight);
  const renderW = imgWidth * scale;
  const widthPx = bar.fraction * renderW;
  if (!(widthPx > 0)) return null;
  return { widthPx };
}

/**
 * On-screen geometry for the North/East rose over a contain-fit image.
 *
 * `directions` are angles measured **counter-clockwise from screen-right, with
 * screen-up positive** — the engine's convention (`seestack.skymarks`), the same
 * one the baked share JPEG draws in, so the rose on screen and the rose in the
 * downloaded file can't disagree. CSS y grows *downward*, so each arm's screen
 * vector negates the y component. Arms are sized from the box's short side, so a
 * wide mosaic and a square crop get proportionally the same rose — the same rule
 * the baked version uses.
 *
 * Returns `null` when there is nothing to place (no directions, or a box not yet
 * measured). Pure, so the geometry is unit-testable without a DOM.
 */
export function compassLayout(
  directions: SkyDirections | null | undefined,
  boxW: number,
  boxH: number,
): { armPx: number; north: { dx: number; dy: number }; east: { dx: number; dy: number } } | null {
  if (!directions || boxW <= 0 || boxH <= 0) return null;
  const { north_deg, east_deg } = directions;
  if (!Number.isFinite(north_deg) || !Number.isFinite(east_deg)) return null;
  const armPx = Math.max(10, Math.round(Math.min(boxW, boxH) * 0.11));
  const arm = (deg: number) => {
    const rad = (deg * Math.PI) / 180;
    return { dx: Math.cos(rad) * armPx, dy: -Math.sin(rad) * armPx };
  };
  return { armPx, north: arm(north_deg), east: arm(east_deg) };
}

/** One arm of the rose, drawn from the hub out to its tip with a letter on the end. */
function CompassArm({ letter, dx, dy }: { letter: string; dx: number; dy: number }) {
  const len = Math.hypot(dx, dy);
  // Rotate a horizontal bar into place rather than computing a path: the hub is
  // the transform origin, so the bar always starts at the centre.
  const angle = (Math.atan2(dy, dx) * 180) / Math.PI;
  return (
    <>
      <div style={{
        position: "absolute", left: 0, top: 0, width: len, height: 2,
        background: "rgba(223,241,255,0.95)", borderRadius: 1,
        boxShadow: "0 0 3px rgba(8,12,22,0.9)",
        transformOrigin: "0 50%", transform: `translateY(-50%) rotate(${angle}deg)`,
      }} />
      <span style={{
        position: "absolute", left: dx, top: dy,
        transform: "translate(-50%, -50%)",
        fontSize: 11, lineHeight: 1, color: "#dff1ff",
        padding: "1px 3px", borderRadius: 3, background: "rgba(8,12,22,0.72)",
        textShadow: "0 1px 2px rgba(0,0,0,0.9)",
      }}>
        {letter}
      </span>
    </>
  );
}

export function AnnotatedImage({
  src, alt, imgWidth, imgHeight, objects, show, height, onClick,
  scaleBar, showScale, directions, showCompass,
}: {
  src: string;
  alt: string;
  imgWidth: number;
  imgHeight: number;
  objects: FieldObject[];
  /** Draw the object markers. When false the image renders bare. */
  show: boolean;
  /** Box height in px (the image is contain-fit into full width × this height). */
  height: number;
  onClick?: () => void;
  /** The run's angular scale bar (null when it has no usable WCS). */
  scaleBar?: ScaleBar | null;
  /** Draw the scale bar in the corner. When false it isn't shown. */
  showScale?: boolean;
  /** Where North and East point on the run's grid (null when unorientable). */
  directions?: SkyDirections | null;
  /** Draw the North/East rose. When false it isn't shown. */
  showCompass?: boolean;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [box, setBox] = useState<{ w: number; h: number }>({ w: 0, h: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setBox({ w: el.clientWidth, h: el.clientHeight });
    measure();
    // Track width changes (responsive card). ResizeObserver is widely supported;
    // guard for very old/jsdom environments that lack it.
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Lay the labels out so they don't pile up on each other in a crowded field —
  // and so a small card draws only as many as it can carry (the rest stay named
  // in the read-out both consumers render under the picture).
  const markers = show
    ? deconflictMarkers(
      objectMarkerLayout(objects, imgWidth, imgHeight, box.w, box.h), box.w, box.h)
    : [];
  const bar = showScale
    ? scaleBarLayout(scaleBar, imgWidth, imgHeight, box.w, box.h)
    : null;
  const rose = showCompass ? compassLayout(directions, box.w, box.h) : null;

  return (
    <div
      ref={ref}
      style={{
        position: "relative", width: "100%", height, background: "#000",
        cursor: onClick ? "zoom-in" : undefined, overflow: "hidden",
      }}
      onClick={onClick}
    >
      <img
        src={src}
        alt={alt}
        draggable={false}
        style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
      />
      {markers.map((m) => (
        <div
          key={m.object.catalog_id}
          data-testid="object-marker"
          style={{
            position: "absolute", left: m.left, top: m.top,
            width: 0, height: 0, pointerEvents: "none",
          }}
        >
          {/* The dot stays exactly on the object; only the chip is placed. */}
          <div style={{
            position: "absolute", left: -DOT_R, top: -DOT_R,
            width: 8, height: 8, borderRadius: "50%",
            border: "1.5px solid rgba(120,200,255,0.95)",
            boxShadow: "0 0 3px rgba(0,0,0,0.9)",
          }} />
          <span style={{
            position: "absolute", left: m.labelDx, top: m.labelDy,
            transform: "translate(-50%, -50%)",
            fontSize: 11, lineHeight: 1.1, color: "#dff1ff", whiteSpace: "nowrap",
            padding: "1px 4px", borderRadius: 4, background: "rgba(8,12,22,0.72)",
            textShadow: "0 1px 2px rgba(0,0,0,0.9)",
          }}>
            {objectLabel(m.object)}
          </span>
        </div>
      ))}
      {bar && scaleBar ? (
        <div
          data-testid="scale-bar"
          style={{
            position: "absolute", left: 10, bottom: 8, pointerEvents: "none",
            display: "flex", flexDirection: "column", alignItems: "center", gap: 3,
          }}
        >
          <span style={{
            fontSize: 11, lineHeight: 1.1, color: "#dff1ff", whiteSpace: "nowrap",
            padding: "1px 4px", borderRadius: 4, background: "rgba(8,12,22,0.72)",
            textShadow: "0 1px 2px rgba(0,0,0,0.9)",
          }}>
            {scaleBar.label}
          </span>
          <div style={{
            width: bar.widthPx, height: 3, background: "rgba(223,241,255,0.95)",
            borderRadius: 2, boxShadow: "0 0 3px rgba(0,0,0,0.9)",
            borderLeft: "2px solid rgba(223,241,255,0.95)",
            borderRight: "2px solid rgba(223,241,255,0.95)",
          }} />
        </div>
      ) : null}
      {/* The rose sits top-right and the bar bottom-left, so they can never
          overlap however small the box gets. (The baked share picture puts both
          along the *top* because its bottom edge is the caption zone; on screen
          there is no caption, and bottom-left is where the bar has always been.)
          Inset by the arm length plus a margin so no arm can run off an edge. */}
      {rose ? (
        <div
          data-testid="sky-compass"
          style={{
            position: "absolute", right: rose.armPx + 10, top: rose.armPx + 10,
            width: 0, height: 0, pointerEvents: "none",
          }}
        >
          <CompassArm letter="N" dx={rose.north.dx} dy={rose.north.dy} />
          <CompassArm letter="E" dx={rose.east.dx} dy={rose.east.dy} />
        </div>
      ) : null}
    </div>
  );
}
