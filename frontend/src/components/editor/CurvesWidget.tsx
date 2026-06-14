import { Box, Group, Text } from "@mantine/core";
import { useRef } from "react";
import type { Histogram } from "../../api/client";

type Pt = [number, number];

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
 * points move freely; click empty space to add a point, double-click to remove. */
export function CurvesWidget({ points, onChange, histogram }: {
  points: Pt[];
  onChange: (pts: Pt[]) => void;
  histogram?: Histogram;
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const drag = useRef<number | null>(null);
  const pts = points.length ? points : [[0, 0], [1, 1]] as Pt[];

  const evtPt = (e: React.PointerEvent | React.MouseEvent): Pt => {
    const rect = svgRef.current!.getBoundingClientRect();
    return fromSvg(
      ((e.clientX - rect.left) / rect.width) * SIZE,
      ((e.clientY - rect.top) / rect.height) * SIZE,
    );
  };

  const update = (i: number, p: Pt) => {
    const next = pts.map((q, j) => (j === i ? p : q)) as Pt[];
    if (i === 0) next[0] = [0, p[1]];
    if (i === pts.length - 1) next[pts.length - 1] = [1, p[1]];
    next.sort((a, b) => a[0] - b[0]);
    onChange(next);
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

  const path = pts.map((p) => toSvg(p[0], p[1]).join(",")).join(" ");

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
        <polyline points={path} fill="none" stroke="var(--mantine-color-violet-4)" strokeWidth={2} />
        {pts.map((p, i) => {
          const [cx, cy] = toSvg(p[0], p[1]);
          return (
            <circle
              key={i} cx={cx} cy={cy} r={6}
              fill="var(--mantine-color-violet-3)" stroke="#fff" strokeWidth={1}
              style={{ cursor: "grab" }}
              onPointerDown={(e) => { e.stopPropagation(); (e.target as Element).setPointerCapture?.(e.pointerId); drag.current = i; }}
              onDoubleClick={(e) => { e.stopPropagation(); removePoint(i); }}
            />
          );
        })}
      </svg>
      <Group justify="space-between">
        <Text size="xs" c="dimmed">double-click to add · double-click a point to remove</Text>
        <Text size="xs" c="violet" style={{ cursor: "pointer" }}
          onClick={() => onChange([[0, 0], [1, 1]])}>reset</Text>
      </Group>
    </Box>
  );
}
