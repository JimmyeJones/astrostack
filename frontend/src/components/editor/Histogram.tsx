import { Box } from "@mantine/core";
import type { Histogram as Hist } from "../../api/client";

const W = 256;
const H = 70;

/** A vertical guide line drawn over the histogram at a display value in [0, 1]
 * (e.g. the Levels op's black/white points, or their data-driven suggestion). */
export type HistGuide = {
  /** Display value in [0, 1]; clamped to the axis. */
  value: number;
  color: string;
  /** Dashed + fainter for an advisory (suggested) marker vs a solid current one. */
  dashed?: boolean;
  /** Optional short label drawn at the top of the line (e.g. "B", "W"). */
  label?: string;
};

/** Overlaid R/G/B histogram as filled SVG areas, with a sqrt scale so faint
 * detail in the shadows is visible (typical for astro histograms). Optional
 * `guides` overlay vertical lines (the Levels black/white points and their
 * suggestion) so a beginner can see where those points land on the tonal range. */
export function Histogram({ data, guides }: { data: Hist | undefined; guides?: HistGuide[] }) {
  if (!data) return <Box h={H} bg="dark.8" style={{ borderRadius: 6 }} />;
  const n = data.bins || 1;
  const channels: [string, number[]][] = [
    ["#fa5252", data.r], ["#40c057", data.g], ["#4dabf7", data.b],
  ];
  const peak = Math.max(1, ...channels.flatMap(([, c]) => c));
  const area = (counts: number[]) => {
    const pts = counts.map((v, i) => {
      const x = (i / (n - 1)) * W;
      const y = H - Math.sqrt(v / peak) * H;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    return `0,${H} ${pts.join(" ")} ${W},${H}`;
  };
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none"
      style={{ width: "100%", height: H, background: "#0c0c0c", borderRadius: 6 }}>
      {channels.map(([color, counts]) => (
        <polygon key={color} points={area(counts)} fill={color} fillOpacity={0.4}
          stroke={color} strokeWidth={0.75} strokeOpacity={0.9} />
      ))}
      {(guides ?? []).map((g, i) => {
        const x = Math.min(Math.max(g.value, 0), 1) * W;
        return (
          <g key={i}>
            <line x1={x} y1={0} x2={x} y2={H} stroke={g.color}
              strokeWidth={g.dashed ? 0.75 : 1} strokeOpacity={g.dashed ? 0.5 : 0.95}
              strokeDasharray={g.dashed ? "2 2" : undefined} />
            {g.label ? (
              <text x={Math.min(x + 1.5, W - 1)} y={7} fill={g.color}
                fillOpacity={g.dashed ? 0.6 : 0.95} fontSize={7}
                textAnchor={x > W - 12 ? "end" : "start"}>{g.label}</text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}
