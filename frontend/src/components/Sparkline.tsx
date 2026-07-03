import { Box } from "@mantine/core";

// Map a numeric series to SVG polyline points inside a `width`×`height` box.
// x is spread evenly across the width; y is inverted (SVG y grows downward) and
// scaled to the series' own min..max with a small vertical margin so the extreme
// points aren't clipped at the edge. A flat series (min==max) draws a centred
// horizontal line. Pure/non-mutating so it's easy to test.
export function sparklinePoints(
  values: number[], width: number, height: number, pad = 2,
): { x: number; y: number }[] {
  if (values.length === 0) return [];
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo;
  const innerH = height - 2 * pad;
  const stepX = values.length > 1 ? width / (values.length - 1) : 0;
  return values.map((v, i) => {
    const frac = span > 0 ? (v - lo) / span : 0.5;
    return { x: values.length > 1 ? i * stepX : width / 2, y: pad + (1 - frac) * innerH };
  });
}

/** A tiny inline SVG line chart. `values` are plotted left→right in order; the
 * last point is marked with a dot. Colour-neutral (inherits `color`). */
export function Sparkline({
  values, width = 120, height = 28, color = "var(--mantine-color-teal-5)",
  "aria-label": ariaLabel,
}: {
  values: number[]; width?: number; height?: number; color?: string;
  "aria-label"?: string;
}) {
  const pts = sparklinePoints(values, width, height);
  if (pts.length === 0) return null;
  const path = pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  return (
    <Box component="span" style={{ display: "inline-flex", lineHeight: 0 }}>
      <svg width={width} height={height} role="img" aria-label={ariaLabel}
        style={{ overflow: "visible" }}>
        {pts.length > 1 ? (
          <polyline points={path} fill="none" stroke={color} strokeWidth={1.5}
            strokeLinejoin="round" strokeLinecap="round" />
        ) : null}
        <circle cx={last.x} cy={last.y} r={2.2} fill={color} />
      </svg>
    </Box>
  );
}
