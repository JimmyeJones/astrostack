import { Box, Text } from "@mantine/core";
import type { FieldFill } from "../api/client";

/** The drawing "here's how it fills your field" needs, in arcminutes.
 *
 *  Everything is laid out in real arcminutes and centred on the origin, then
 *  handed to the SVG as a `viewBox` — so the frame and the object are to scale
 *  with each other by construction, and an object *bigger* than the frame simply
 *  makes the viewport bigger instead of being clipped at the frame's edge (the
 *  overflow is the single most useful thing the picture has to say). */
export interface FieldFillGeometry {
  // Rendered size in CSS pixels.
  width: number;
  height: number;
  viewBox: string;
  // The frame rectangle, in the same arcminute space as the viewBox.
  frame: { x: number; y: number; w: number; h: number };
  // The object's ellipse, centred on the origin.
  object: { rx: number; ry: number };
}

/** Lay out the to-scale diagram for a `field_fill` payload.
 *
 *  `width` is the rendered width in pixels; the height follows from the content's
 *  own aspect ratio, so the frame is never squashed. `margin` is breathing room
 *  around whichever of the two is larger, as a fraction of that extent.
 *
 *  Pure and unit-testable: no DOM, no Mantine, no rounding surprises. */
export function fieldFillGeometry(
  fill: FieldFill, { width = 168, margin = 0.06 }: { width?: number; margin?: number } = {},
): FieldFillGeometry | null {
  const fw = fill.field_long_arcmin;
  const fh = fill.field_short_arcmin;
  if (!(fw > 0) || !(fh > 0)) return null;
  const major = Math.max(0, fill.frac_long) * fw;
  const minor = Math.max(0, fill.frac_short) * fh;
  if (!Number.isFinite(major) || !Number.isFinite(minor)) return null;

  // The viewport has to hold whichever is bigger on each axis — the frame, or an
  // object that overflows it.
  const contentW = Math.max(fw, major);
  const contentH = Math.max(fh, minor);
  const padX = contentW * margin;
  const padY = contentH * margin;
  const boxW = contentW + 2 * padX;
  const boxH = contentH + 2 * padY;
  return {
    width,
    height: Math.round((width * boxH) / boxW),
    viewBox: `${-boxW / 2} ${-boxH / 2} ${boxW} ${boxH}`,
    frame: { x: -fw / 2, y: -fh / 2, w: fw, h: fh },
    object: { rx: major / 2, ry: minor / 2 },
  };
}

/**
 * "Here's how it fills your field" — a small to-scale picture of the object
 * inside one Seestar frame, drawn *before* you shoot.
 *
 * The app has always answered "will it fit?" in words, which is enough to know
 * whether to shoot a mosaic but not what the shot will look like: "fits
 * comfortably in a single Seestar frame" covers a nebula that fills two thirds of
 * the frame and a planetary that is a dot in the middle of it. This shows which.
 *
 * Every number comes off the backend's `field_fill`, which is built from the same
 * catalogue size, the same minor-axis convention and the same *derived* field as
 * the framing sentence beside it — so the picture and the sentence cannot
 * disagree. Renders nothing when the payload is absent (an object with no vetted
 * size, or an older backend), exactly like the sentence.
 */
export function FieldFillDiagram({ fill, name }: { fill: FieldFill; name: string }) {
  const g = fieldFillGeometry(fill);
  if (!g) return null;
  const overflows = fill.frac_long >= 1 || fill.frac_short >= 1;
  return (
    <Box mt={4}>
      <svg width={g.width} height={g.height} viewBox={g.viewBox}
        role="img" aria-label={`${name} against one Seestar frame. ${fill.text}`}
        style={{ display: "block", overflow: "visible" }}>
        {/* One frame of sky. Dashed so it reads as "the edge of what you get"
            rather than as a border around the drawing. The stroke is
            non-scaling, so its width and dashes are CSS pixels — constants, not
            fractions of the field, or the same border would come out thinner on
            a narrower telescope's frame than on a wider one. */}
        <rect x={g.frame.x} y={g.frame.y} width={g.frame.w} height={g.frame.h}
          fill="none" stroke="var(--mantine-color-dimmed)" strokeWidth={1.2}
          strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
        {/* The object, to scale and centred — where it would sit if you pointed
            straight at it. */}
        <ellipse cx={0} cy={0} rx={g.object.rx} ry={g.object.ry}
          fill="var(--mantine-color-indigo-5)" fillOpacity={overflows ? 0.22 : 0.3}
          stroke="var(--mantine-color-indigo-5)" strokeWidth={1.4}
          vectorEffect="non-scaling-stroke" />
      </svg>
      <Text size="xs" c="dimmed" mt={2}>{fill.text}</Text>
    </Box>
  );
}
