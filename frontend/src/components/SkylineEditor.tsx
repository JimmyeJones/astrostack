/**
 * "Draw your skyline" — the visual way to tell the Tonight planner what your
 * trees and buildings block.
 *
 * The planner has always been able to skip a target while it sits behind an
 * obstruction (`HorizonProfile` in the engine, `horizon_profile` in settings),
 * but the only way to set it was to type `(azimuth°, altitude°)` pairs — which
 * assumes you know that the tree at the end of the garden is at "az 95°". A
 * backyard Seestar owner knows where their tree is by looking at it, so here
 * they drag the skyline up instead, and the same array gets saved.
 *
 * Nothing is removed: the numeric list is still here, one disclosure down, for
 * anyone who does want to type exact bearings. An untouched install keeps an
 * empty profile, which is a flat open horizon — byte-for-byte today's planner.
 */
import { useRef, useState } from "react";
import { Button, Group, Stack, Text } from "@mantine/core";
import {
  SKYLINE_MAX_ALT, SKYLINE_PRESETS, STRIP, altAtY, azAtX, bucketAzimuths,
  compassLabel, describeSkyline, emptyHeights, groundPolygonPoints,
  heightsToProfile, paintSpan, profileToHeights, xAtAz, yAtAlt,
  type HorizonPoint,
} from "../skyline";

const COMPASS_TICKS = [0, 45, 90, 135, 180, 225, 270, 315];
const ALT_TICKS = [15, 30, 45, 60];

export function SkylineEditor(
  { value, onChange }: { value: HorizonPoint[]; onChange: (v: HorizonPoint[]) => void },
) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  // The drawn heights are derived from the saved profile until a gesture starts,
  // so a profile typed into the numeric list below shows up here immediately.
  const [drag, setDrag] = useState<{ heights: number[]; az: number; alt: number } | null>(null);
  const heights = drag ? drag.heights : profileToHeights(value);

  // Map a pointer event into the fixed viewBox the strip is drawn in, so the
  // arithmetic doesn't care what width the card ended up.
  const toStrip = (e: { clientX: number; clientY: number }) => {
    const box = svgRef.current?.getBoundingClientRect();
    if (!box || !box.width || !box.height) return null;
    return {
      az: azAtX(((e.clientX - box.left) / box.width) * STRIP.w),
      alt: altAtY(((e.clientY - box.top) / box.height) * STRIP.h),
    };
  };

  const start = (e: React.PointerEvent<SVGSVGElement>) => {
    const at = toStrip(e);
    if (!at) return;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    const next = paintSpan(heights, at.az, at.alt, at.az, at.alt);
    setDrag({ heights: next, az: at.az, alt: at.alt });
  };

  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!drag) return;
    const at = toStrip(e);
    if (!at) return;
    setDrag({
      heights: paintSpan(drag.heights, drag.az, drag.alt, at.az, at.alt),
      az: at.az, alt: at.alt,
    });
  };

  const finish = () => {
    if (!drag) return;
    onChange(heightsToProfile(drag.heights));
    setDrag(null);
  };

  const apply = (next: number[]) => {
    setDrag(null);
    onChange(heightsToProfile(next));
  };

  const drawn = heights.some((h) => h > 0);

  return (
    <Stack gap="xs" data-testid="skyline-editor">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${STRIP.w} ${STRIP.h}`}
        role="img"
        aria-label="Your skyline: drag upwards where trees or buildings block the sky"
        data-testid="skyline-strip"
        style={{ width: "100%", height: "auto", touchAction: "none", cursor: "crosshair" }}
        onPointerDown={start}
        onPointerMove={move}
        onPointerUp={finish}
        onPointerCancel={finish}
        onPointerLeave={finish}
      >
        <rect x={STRIP.x0} y={STRIP.yTop} width={STRIP.x1 - STRIP.x0}
          height={STRIP.yBase - STRIP.yTop} fill="var(--mantine-color-dark-8)"
          stroke="var(--mantine-color-dark-4)" />
        {ALT_TICKS.map((alt) => (
          <g key={alt}>
            <line x1={STRIP.x0} x2={STRIP.x1} y1={yAtAlt(alt)} y2={yAtAlt(alt)}
              stroke="var(--mantine-color-dark-5)" strokeDasharray="3 5" />
            <text x={STRIP.x0 - 6} y={yAtAlt(alt) + 4} textAnchor="end" fontSize={11}
              fill="var(--mantine-color-dimmed)">{alt}°</text>
          </g>
        ))}
        {COMPASS_TICKS.map((az) => (
          <g key={az}>
            <line x1={xAtAz(az)} x2={xAtAz(az)} y1={STRIP.yTop} y2={STRIP.yBase}
              stroke="var(--mantine-color-dark-5)" />
            <text x={xAtAz(az)} y={STRIP.yBase + 20} textAnchor="middle" fontSize={13}
              fill="var(--mantine-color-dimmed)">{compassLabel(az)}</text>
          </g>
        ))}
        <polygon data-testid="skyline-ground" points={groundPolygonPoints(heights)}
          fill="var(--mantine-color-dark-3)" stroke="var(--mantine-color-gray-5)"
          strokeWidth={1.5} />
        {/* One grab handle per bucket, so it reads as draggable rather than as a chart. */}
        {bucketAzimuths().map((az, i) => (
          heights[i] > 0 ? (
            <circle key={az} cx={xAtAz(az)} cy={yAtAlt(heights[i])} r={2.5}
              fill="var(--mantine-color-gray-4)" />
          ) : null
        ))}
        <text x={STRIP.x0} y={STRIP.yTop - 2} fontSize={11}
          fill="var(--mantine-color-dimmed)">
          drag upwards where the sky is blocked
        </text>
      </svg>

      <Text size="xs" c="dimmed" data-testid="skyline-summary">
        {describeSkyline(heights)}
      </Text>

      <Group gap="xs" wrap="wrap">
        {SKYLINE_PRESETS.map((p) => (
          <Button key={p.id} variant="light" size="compact-sm" title={p.hint}
            onClick={() => apply(p.heights())}>
            {p.label}
          </Button>
        ))}
        {drawn && (
          <Button variant="subtle" color="gray" size="compact-sm"
            onClick={() => apply(emptyHeights())}>
            Flatten it
          </Button>
        )}
      </Group>
      <Text size="xs" c="dimmed">
        Each step is {360 / bucketAzimuths().length}° of compass and at most{" "}
        {SKYLINE_MAX_ALT}° high. Drawing here replaces the exact points below — use
        those if you'd rather type bearings.
      </Text>
    </Stack>
  );
}
