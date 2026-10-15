import {
  Badge, Box, Button, Group, NumberInput, SimpleGrid, Slider, Stack, Text, Title,
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api } from "../../api/client";
import { BADGE_COLOR, BADGE_LABEL, type SettingsForm, type SettingsPatch } from "./moreSettings";
import {
  HORIZON, READ_FROM_PHOTOS_PATCH, altitudeBandPath, altitudeHint, altitudeLine,
  currentLocationLine, showTypedBoxes, siteMode,
} from "./observingSite";

/** The query key `GET /api/plan/site` lives under; the page's Save refreshes it. */
export const PLAN_SITE_QUERY_KEY = ["plan-site"] as const;

/**
 * Section 4 of the owner-approved Settings redesign
 * (`docs/design/settings-redesign.md`): "Where you observe from" — read it
 * from my photos or type it in, a privacy line, and the lowest altitude the
 * planner suggests as a slider over a small horizon drawing whose lit band
 * redraws as it moves.
 *
 * It replaces the bare latitude / longitude / elevation / minimum-altitude
 * boxes that opened the Observing site tab — same four fields, same edit
 * buffer, each still stamped `data-setting` (and the two location fields also
 * `data-settings` on the section, because the "Read it from my photos" button
 * writes them while their boxes are hidden). The copy and the geometry live in
 * `observingSite.ts`; this file only draws.
 */
export function ObservingSiteSection({
  form, onPatch, labelFor,
}: {
  form: SettingsForm;
  onPatch: (patch: SettingsPatch) => void;
  labelFor: (key: string, label: string) => ReactNode;
}) {
  const site = useQuery({ queryKey: PLAN_SITE_QUERY_KEY, queryFn: api.getSite, retry: false });
  const [typedChosen, setTypedChosen] = useState(false);
  const mode = siteMode(form, typedChosen);
  const siteData = site.isError ? undefined : site.data;
  const current = currentLocationLine(form, mode, siteData);
  const showBoxes = showTypedBoxes(mode, siteData);
  const alt = typeof form.min_target_altitude_deg === "number" ? form.min_target_altitude_deg : 30;

  const numOrEmpty = (k: string) =>
    (typeof form[k] === "number" ? (form[k] as number) : "");

  return (
    <Stack gap="sm" data-testid="observing-site" data-settings="site_lat site_lon">
      <Group justify="space-between" align="flex-start" gap="xs">
        <Stack gap={4} style={{ flex: "1 1 320px" }}>
          <Title order={3}>Where you observe from</Title>
          <Text size="sm" c="dimmed">
            Used only to plan your nights — what's up, and when. It stays on your
            NAS; AstroStack never sends it anywhere.
          </Text>
        </Stack>
        <Badge variant="light" color={BADGE_COLOR.safe} size="sm" style={{ flexShrink: 0 }}>
          {BADGE_LABEL.safe}
        </Badge>
      </Group>

      <Group gap="xs" role="group" aria-label="Where you observe from">
        <Button type="button" mih={44} aria-pressed={mode === "photos"}
          variant={mode === "photos" ? "filled" : "default"}
          color={mode === "photos" ? "orange" : undefined}
          onClick={() => { setTypedChosen(false); onPatch(READ_FROM_PHOTOS_PATCH); }}>
          Read it from my photos
        </Button>
        <Button type="button" mih={44} aria-pressed={mode === "typed"}
          variant={mode === "typed" ? "filled" : "default"}
          color={mode === "typed" ? "orange" : undefined}
          onClick={() => setTypedChosen(true)}>
          Type it in
        </Button>
      </Group>
      <Text size="sm" data-testid="site-current" c={current.known ? undefined : "orange"}
        fw={current.known ? undefined : 500}>
        Currently: <b>{current.text}</b>
      </Text>

      <SimpleGrid cols={{ base: 1, xs: 3 }}>
        {showBoxes ? (
          <>
            <NumberInput label={labelFor("site_lat", "Latitude (° north)")}
              value={numOrEmpty("site_lat")}
              min={-90} max={90} step={0.1} decimalScale={4} placeholder="e.g. 51.5"
              description="South is negative"
              onChange={(v) => onPatch({ site_lat: v === "" ? null : Number(v) })} />
            <NumberInput label={labelFor("site_lon", "Longitude (° east)")}
              value={numOrEmpty("site_lon")}
              min={-180} max={180} step={0.1} decimalScale={4} placeholder="e.g. -0.1"
              description="West is negative"
              onChange={(v) => onPatch({ site_lon: v === "" ? null : Number(v) })} />
          </>
        ) : null}
        {/* Used whichever way the location is found — the photos give only
            latitude and longitude — so it is never hidden. */}
        <NumberInput label={labelFor("site_elevation_m", "Height above sea level (m)")}
          value={numOrEmpty("site_elevation_m")}
          min={-500} max={9000} step={10}
          onChange={(v) => onPatch({ site_elevation_m: v === "" ? 0 : Number(v) })} />
      </SimpleGrid>
      <Text size="xs" c="dimmed">
        Was: Latitude (°N), Longitude (°E), Elevation (m)
      </Text>

      <Group align="center" gap="lg" wrap="wrap">
        <Stack gap={6} style={{ flex: "1 1 260px", minWidth: 0 }}>
          <Text fw={600} component="div">
            {labelFor("min_target_altitude_deg", altitudeLine(alt))}
          </Text>
          <Slider min={0} max={80} step={5} value={alt} label={null}
            thumbLabel="Lowest altitude to suggest"
            onChange={(v) => onPatch({ min_target_altitude_deg: v })} />
          <Group justify="space-between">
            <Text size="xs" c="dimmed">Horizon</Text>
            <Text size="xs" c="dimmed">Nearly overhead</Text>
          </Group>
          <Text size="sm" c="dimmed" data-testid="altitude-hint">{altitudeHint(alt)}</Text>
          <Text size="xs" c="dimmed">Was: Minimum target altitude (°)</Text>
        </Stack>
        <HorizonDrawing alt={alt} />
      </Group>
    </Stack>
  );
}

function HorizonDrawing({ alt }: { alt: number }) {
  const { cx, cy, r } = HORIZON;
  return (
    <Box component="svg" viewBox="0 0 320 180" w={320} maw="100%" h="auto"
      role="img" aria-label={`Sky above the horizon; targets are suggested only above ${alt}°`}
      style={{ flex: "0 1 320px" }}>
      <rect x="0" y="0" width="320" height="180" rx="12" fill="#0b1020" />
      <path d={`M${cx - r} ${cy} A${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke="#2a3553" strokeWidth="2" />
      <path data-testid="altitude-band" d={altitudeBandPath(alt)}
        fill="rgba(242,168,79,0.16)" stroke="#f2a84f" strokeWidth="2" />
      <path d="M0 160 L40 148 L52 132 L64 150 L110 154 L128 138 L140 156 L200 152 L224 134 L240 154 L320 150 L320 180 L0 180 Z"
        fill="#1b2440" />
      <circle cx="232" cy="74" r="4" fill="#fff3d9" />
      <circle cx="118" cy="58" r="3" fill="#dfe8ff" />
      <circle cx="182" cy="40" r="3" fill="#ffffff" />
      <text x="160" y="24" fill="#aab3c8" fontSize="12" textAnchor="middle">
        Suggested targets come from the lit band
      </text>
    </Box>
  );
}
