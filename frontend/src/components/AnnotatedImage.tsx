import { useEffect, useRef, useState } from "react";
import type { FieldObject } from "../api/client";

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
    return { object: o, left, top, visible };
  });
}

/** A friendly one-word label for an object: its name if it has one, else its id. */
export function objectLabel(o: FieldObject): string {
  return o.name && o.name.trim() ? o.name : o.catalog_id;
}

export function AnnotatedImage({
  src, alt, imgWidth, imgHeight, objects, show, height, onClick,
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

  const markers = show ? objectMarkerLayout(objects, imgWidth, imgHeight, box.w, box.h) : [];

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
      {markers.filter((m) => m.visible).map((m) => (
        <div
          key={m.object.catalog_id}
          data-testid="object-marker"
          style={{
            position: "absolute", left: m.left, top: m.top,
            transform: "translate(-50%, -50%)", pointerEvents: "none",
            display: "flex", flexDirection: "column", alignItems: "center", gap: 2,
          }}
        >
          <div style={{
            width: 8, height: 8, borderRadius: "50%",
            border: "1.5px solid rgba(120,200,255,0.95)",
            boxShadow: "0 0 3px rgba(0,0,0,0.9)",
          }} />
          <span style={{
            fontSize: 11, lineHeight: 1.1, color: "#dff1ff", whiteSpace: "nowrap",
            padding: "1px 4px", borderRadius: 4, background: "rgba(8,12,22,0.72)",
            textShadow: "0 1px 2px rgba(0,0,0,0.9)",
          }}>
            {objectLabel(m.object)}
          </span>
        </div>
      ))}
    </div>
  );
}
