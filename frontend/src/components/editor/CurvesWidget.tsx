import { Anchor, Box, Group, Text } from "@mantine/core";
import { useRef } from "react";
import type { Histogram } from "../../api/client";
import {
  addCurvePointInLargestGap, moveCurvePoint, nudgeCurvePoint, removeCurvePoint, type Pt,
} from "./curveDrag";

// Keyboard nudge step for a focused curve point (Shift = coarse). Small enough
// for fine tone tweaks, large enough that a few presses are visible.
const KEY_STEP = 0.02;
const KEY_STEP_COARSE = 0.1;

const SIZE = 220;
const PAD = 10;

/** Faint combined-channel histogram polygon to sit behind the curve, mapped into
 * the curve's [PAD, SIZE-PAD] box with a sqrt scale (astro shadows are crowded). */
function histPath(h: Histogram): string {
  const n = h.bins || 1;
  const combined = h.r.map((_, i) => (h.r[i] ?? 0) + (h.g[i] ?? 0) + (h.b[i] ?? 0));
  const peak = Math.max(1, ...combined);
  const span = SIZE - 2 * PAD;
  const pts = combined.map((v, i) => {
    const x = PAD + (i / (n - 1)) * span;
    const y = SIZE - PAD - Math.sqrt(v / peak) * span;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return `${PAD},${SIZE - PAD} ${pts.join(" ")} ${SIZE - PAD},${SIZE - PAD}`;
}

function toSvg(x: number, y: number): [number, number] {
  return [PAD + x * (SIZE - 2 * PAD), PAD + (1 - y) * (SIZE - 2 * PAD)];
}
function fromSvg(px: number, py: number): Pt {
  const x = (px - PAD) / (SIZE - 2 * PAD);
  const y = 1 - (py - PAD) / (SIZE - 2 * PAD);
  return [Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))];
}

/** A small draggable tone-curve editor. Endpoints keep their x (0 and 1); inner
 * points move freely; double-click empty space to add a point, double-click a
 * point to remove it.
 *
 * `ghost` draws a read-only dashed curve behind the editable one — used to show
 * the shape the Auto-contrast (`auto`) mode is applying at render time while the
 * stored points are still a flat identity, so the widget no longer contradicts
 * the preview. It's advisory: the user can't drag it (they Bake it to edit). */
export function CurvesWidget({ points, onChange, histogram, ghost }: {
  points: Pt[];
  onChange: (pts: Pt[]) => void;
  histogram?: Histogram;
  ghost?: Pt[];
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const drag = useRef<number | null>(null);
  const pointRefs = useRef<(SVGCircleElement | null)[]>([]);
  const pts = points.length ? points : [[0, 0], [1, 1]] as Pt[];

  const evtPt = (e: React.PointerEvent | React.MouseEvent): Pt => {
    const rect = svgRef.current!.getBoundingClientRect();
    return fromSvg(
      ((e.clientX - rect.left) / rect.width) * SIZE,
      ((e.clientY - rect.top) / rect.height) * SIZE,
    );
  };

  const update = (i: number, p: Pt) => {
    // moveCurvePoint clamps interior points between their neighbours so the drag
    // can't cross another point and swap which handle is being moved.
    onChange(moveCurvePoint(pts, i, p));
  };

  const onMove = (e: React.PointerEvent) => {
    if (drag.current == null) return;
    update(drag.current, evtPt(e));
  };

  const addPoint = (e: React.MouseEvent) => {
    if (drag.current != null) return;
    const p = evtPt(e);
    onChange([...pts, p].sort((a, b) => a[0] - b[0]) as Pt[]);
  };

  const removePoint = (i: number) => {
    if (i === 0 || i === pts.length - 1) return;
    onChange(pts.filter((_, j) => j !== i));
  };

  const addPointKeyboard = () => {
    // Keyboard users can't double-click empty space to add a point; add one in
    // the widest gap (on the current curve) and focus it so it can be nudged.
    const { points, index } = addCurvePointInLargestGap(pts);
    onChange(points);
    // Focus the new handle once React has re-rendered it.
    requestAnimationFrame(() => pointRefs.current[index]?.focus());
  };

  const onPointKeyDown = (i: number) => (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? KEY_STEP_COARSE : KEY_STEP;
    let handled = true;
    if (e.key === "ArrowLeft") onChange(nudgeCurvePoint(pts, i, -step, 0));
    else if (e.key === "ArrowRight") onChange(nudgeCurvePoint(pts, i, step, 0));
    else if (e.key === "ArrowUp") onChange(nudgeCurvePoint(pts, i, 0, step));
    else if (e.key === "ArrowDown") onChange(nudgeCurvePoint(pts, i, 0, -step));
    else if (e.key === "Delete" || e.key === "Backspace") onChange(removeCurvePoint(pts, i));
    else handled = false;
    if (handled) { e.preventDefault(); e.stopPropagation(); }
  };

  const path = pts.map((p) => toSvg(p[0], p[1]).join(",")).join(" ");
  const ghostPath = ghost && ghost.length >= 2
    ? ghost.map((p) => toSvg(p[0], p[1]).join(",")).join(" ")
    : null;

  return (
    <Box>
      <svg
        ref={svgRef} viewBox={`0 0 ${SIZE} ${SIZE}`}
        style={{ width: "100%", maxWidth: SIZE, background: "#111", borderRadius: 6,
                 touchAction: "none", cursor: "crosshair" }}
        onPointerMove={onMove}
        onPointerUp={() => (drag.current = null)}
        onPointerLeave={() => (drag.current = null)}
        onDoubleClick={addPoint}
      >
        {histogram ? (
          <polygon points={histPath(histogram)} fill="#5c5f66" fillOpacity={0.35} stroke="none" />
        ) : null}
        {[0.25, 0.5, 0.75].map((g) => (
          <g key={g} stroke="#333" strokeWidth={0.5}>
            <line x1={toSvg(g, 0)[0]} y1={PAD} x2={toSvg(g, 0)[0]} y2={SIZE - PAD} />
            <line x1={PAD} y1={toSvg(0, g)[1]} x2={SIZE - PAD} y2={toSvg(0, g)[1]} />
          </g>
        ))}
        {ghostPath ? (
          <polyline points={ghostPath} fill="none" aria-label="auto contrast preview curve"
            stroke="var(--mantine-color-violet-4)" strokeOpacity={0.55}
            strokeWidth={2} strokeDasharray="5 4" />
        ) : null}
        <polyline points={path} fill="none" stroke="var(--mantine-color-violet-4)" strokeWidth={2} />
        {pts.map((p, i) => {
          const [cx, cy] = toSvg(p[0], p[1]);
          const isEndpoint = i === 0 || i === pts.length - 1;
          return (
            <circle
              key={i} cx={cx} cy={cy} r={6}
              ref={(el) => { pointRefs.current[i] = el; }}
              fill="var(--mantine-color-violet-3)" stroke="#fff" strokeWidth={1}
              style={{ cursor: "grab" }}
              // Focusable so a keyboard user can move/remove points (arrow keys
              // nudge, Delete removes an interior point) — the drag handles are
              // otherwise mouse-only.
              tabIndex={0}
              role="slider"
              aria-label={`Curve point ${i + 1} of ${pts.length}${isEndpoint ? " (endpoint)" : ""}`}
              aria-valuetext={`input ${Math.round(p[0] * 100)}%, output ${Math.round(p[1] * 100)}%`}
              onPointerDown={(e) => { e.stopPropagation(); (e.target as Element).setPointerCapture?.(e.pointerId); drag.current = i; }}
              onDoubleClick={(e) => { e.stopPropagation(); removePoint(i); }}
              onKeyDown={onPointKeyDown(i)}
            />
          );
        })}
      </svg>
      <Group justify="space-between">
        <Text size="xs" c="dimmed">
          drag or focus a point &amp; use arrow keys · double-click (or Delete) to remove · double-click empty space to add
        </Text>
        <Group gap="sm">
          <Anchor component="button" type="button" size="xs" c="violet"
            onClick={addPointKeyboard}>add point</Anchor>
          <Anchor component="button" type="button" size="xs" c="violet"
            onClick={() => onChange([[0, 0], [1, 1]])}>reset</Anchor>
        </Group>
      </Group>
    </Box>
  );
}
