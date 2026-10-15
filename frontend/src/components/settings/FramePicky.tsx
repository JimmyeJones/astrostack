import {
  Badge, Box, Button, Group, Paper, SimpleGrid, Stack, Switch, Text, Title,
} from "@mantine/core";
import type { ReactNode } from "react";
import { BADGE_COLOR, BADGE_LABEL } from "./moreSettings";
import {
  FRAME_TILES, PICKY_LEVELS, PICKY_WAS, pickyLevel, pickyPatch, pickyWaitingNote,
  tileLeftOut, trailNote, type FrameTile, type SettingsForm, type SettingsPatch,
} from "./framePicky";

/**
 * Section 3 of the owner-approved Settings redesign
 * (`docs/design/settings-redesign.md`): "Leaving out bad frames" — the
 * "How picky?" control, an illustration of which frames each choice keeps, and
 * the trails switch. It replaces the bare auto-grade switch, Sensitivity
 * select and trails switch that used to sit at the foot of Automation — same
 * three fields, same edit buffer, each still stamped `data-setting` for the
 * "nothing was removed" guard.
 *
 * The copy and the arithmetic live in `framePicky.ts`; this file only draws.
 */
export function FramePickySection({
  form, onPatch, labelFor,
}: {
  form: SettingsForm;
  onPatch: (patch: SettingsPatch) => void;
  labelFor: (key: string, label: string) => ReactNode;
}) {
  const level = pickyLevel(form);
  const keepTrails = Boolean(form.keep_streaked_frames);
  const note = PICKY_LEVELS.find((l) => l.id === level)?.note;
  const waiting = pickyWaitingNote(form);

  return (
    <Stack gap="sm" data-testid="frame-picky">
      <Group justify="space-between" align="flex-start" gap="xs">
        <Stack gap={4} style={{ flex: "1 1 320px" }}>
          <Title order={3}>Leaving out bad frames</Title>
          <Text size="sm" c="dimmed">
            Clouds, wind shake and soft focus make a stack worse. AstroStack can
            leave those frames out for you, each judged against the rest of the
            same target's frames. Left-out frames are never deleted — you can bring
            any of them back on the target's Frames tab, and a frame you kept or
            left out yourself is never changed.
          </Text>
        </Stack>
        <Badge variant="light" color={BADGE_COLOR.pictures} size="sm" style={{ flexShrink: 0 }}>
          {BADGE_LABEL.pictures}
        </Badge>
      </Group>

      <Group gap="sm" align="center">
        <Text fw={700} component="div">
          {/* Both fields the four buttons write ride on the one label, so the
              old names' hover hints and the guard's stamps both survive. */}
          {labelFor("auto_grade_frames", "How picky?")}
        </Text>
        <Box data-setting="auto_grade_sensitivity" role="group" aria-label="How picky?"
          style={{ display: "inline-flex", flexWrap: "wrap", gap: 4 }}>
          {PICKY_LEVELS.map((l) => {
            const on = level === l.id;
            return (
              <Button key={l.id} type="button" size="sm" mih={44}
                variant={on ? "filled" : "default"} color={on ? "orange" : undefined}
                aria-pressed={on}
                onClick={() => onPatch(pickyPatch(l.id))}>
                {l.label}
              </Button>
            );
          })}
        </Box>
      </Group>
      {note ? <Text size="sm" data-testid="picky-note">{note}</Text> : null}
      {level !== "off" ? (
        <Text size="xs" c="dimmed">
          It never leaves out more than a quarter of a target's frames, and a
          target needs at least 10 frames before any are judged.
        </Text>
      ) : null}
      {waiting ? (
        <Text size="sm" c="orange" fw={500} role="note" data-testid="picky-waiting">{waiting}</Text>
      ) : null}

      <SimpleGrid cols={{ base: 4, xs: 6 }} spacing="xs" component="ul"
        aria-label="Illustration of which frames are kept"
        style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {FRAME_TILES.map((t, i) => (
          <FrameTileView key={i} tile={t} leftOut={tileLeftOut(t, level, keepTrails)} />
        ))}
      </SimpleGrid>
      <Text size="xs" c="dimmed">
        Illustration. Your own frames, and why any were left out, are on each
        target's Frames tab.
      </Text>

      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
        <Paper withBorder p="md">
          <Stack gap="xs">
            <Switch
              label={labelFor("keep_streaked_frames", "Keep frames with a satellite or plane trail")}
              checked={keepTrails}
              onChange={(e) => onPatch({ keep_streaked_frames: e.currentTarget.checked })}
            />
            <Text size="sm" c="dimmed" data-testid="trail-note">{trailNote(keepTrails)}</Text>
          </Stack>
        </Paper>
        <Paper withBorder p="md">
          <Stack gap={4}>
            <Text size="sm" fw={600}>Was: {PICKY_WAS}</Text>
            <Text size="xs" c="dimmed">
              The same three settings as before, in plain words.
            </Text>
          </Stack>
        </Paper>
      </SimpleGrid>
    </Stack>
  );
}

/** Where the tile's four stars sit, as % of the tile. */
const STARS: [number, number, number][] = [[22, 30, 5], [62, 22, 4], [48, 62, 6], [78, 70, 3]];

function FrameTileView({ tile, leftOut }: { tile: FrameTile; leftOut: boolean }) {
  const blur = tile.kind === "soft" ? 1.8 : tile.kind === "bitsoft" ? 0.6
    : tile.kind === "borderline" ? 1.1 : 0;
  const stretch = tile.kind === "shaken" ? "scaleX(2.6)" : undefined;
  const dim = tile.kind === "haze" ? 0.45 : tile.kind === "borderline" ? 0.8 : 1;
  return (
    <Box component="li" data-frame-kind={tile.kind} data-left-out={leftOut}
      style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <Box aria-hidden style={{
        position: "relative", aspectRatio: "1", borderRadius: 8, overflow: "hidden",
        background: "#050812",
        border: `2px solid ${leftOut ? "var(--mantine-color-red-8)" : "var(--mantine-color-teal-7)"}`,
        opacity: leftOut ? 0.45 : 1,
      }}>
        <Box style={{ position: "absolute", inset: 0, filter: blur ? `blur(${blur}px)` : undefined, opacity: dim }}>
          {STARS.map(([x, y, s], i) => (
            <span key={i} style={{
              position: "absolute", left: `${x}%`, top: `${y}%`, width: s, height: s,
              borderRadius: "50%", background: "#fff", transform: stretch,
            }} />
          ))}
        </Box>
        {tile.kind === "cloud" ? (
          <span style={{ position: "absolute", inset: 0, background:
            "radial-gradient(circle at 40% 45%, rgba(190,200,220,0.8), rgba(150,160,185,0.4) 60%, rgba(0,0,0,0) 85%)" }} />
        ) : null}
        {tile.kind === "haze" ? (
          <span style={{ position: "absolute", inset: 0, background: "rgba(150,160,185,0.25)" }} />
        ) : null}
        {tile.kind === "trail" ? (
          <span style={{ position: "absolute", left: "-10%", top: "50%", width: "120%", height: 2,
            background: "#fff", transform: "rotate(-24deg)" }} />
        ) : null}
      </Box>
      <Text size="xs" fw={700} ta="center" c={leftOut ? "red.6" : "teal.6"}>
        {leftOut ? "Left out" : "Kept"}
      </Text>
      <Text size="xs" c="dimmed" ta="center" lh={1.2}>{tile.what}</Text>
    </Box>
  );
}
