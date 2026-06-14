import { Box } from "@mantine/core";
import type { Histogram as Hist } from "../../api/client";

const W = 256;
const H = 70;

/** Overlaid R/G/B histogram as filled SVG areas, with a sqrt scale so faint
 * detail in the shadows is visible (typical for astro histograms). */
export function Histogram({ data }: { data: Hist | undefined }) {
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
    </svg>
  );
}
