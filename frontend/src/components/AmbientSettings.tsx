/** Settings card for the optional ambient soundbed: the volume, and a plain
 * explanation of what it is and where it lives.
 *
 * It sits *outside* the server-settings form on purpose — the preference is
 * per-device `localStorage`, not part of `config.json`, so it saves as you move
 * the slider and has nothing to do with the "Save settings" button.
 */
import { Group, Paper, Slider, Stack, Text } from "@mantine/core";
import { IconMusic } from "@tabler/icons-react";
import { useState } from "react";

import { ambientPlayer, ambientSupported } from "../ambient/player";
import { DEFAULT_VOLUME, ambientVolume, setAmbientVolume } from "../ambient/prefs";

export function AmbientSettings() {
  const [volume, setVolume] = useState(() => ambientVolume());
  if (!ambientSupported()) return null;
  const player = ambientPlayer(volume);

  const onChange = (v: number) => {
    const fraction = v / 100;
    setVolume(fraction);
    setAmbientVolume(fraction);
    // Ramps immediately if it's playing, and is remembered for the next start
    // if it isn't — so the slider is never dead.
    player.setVolume(fraction);
  };

  return (
    <Paper withBorder p="lg">
      <Stack>
        <Group gap={6}>
          <IconMusic size={18} />
          <Text fw={600}>Ambient sound (this device)</Text>
        </Group>
        <Text size="sm" c="dimmed">
          A quiet space-ambient soundbed for long sessions watching a stack run
          or browsing the gallery. It is generated in your browser as it plays —
          nothing is downloaded and no two minutes sound the same. Off unless you
          turn it on with the speaker button in the top bar, and remembered for
          this device only (on the lounge PC, off on your phone).
        </Text>
        <div>
          <Text size="sm" fw={500} mb={4}>Volume</Text>
          <Slider
            value={Math.round(volume * 100)}
            onChange={onChange}
            min={0}
            max={100}
            step={5}
            label={(v) => `${v}%`}
            aria-label="Ambient sound volume"
            w={{ base: "100%", xs: 320 }}
            marks={[{ value: Math.round(DEFAULT_VOLUME * 100), label: "default" }]}
          />
        </div>
      </Stack>
    </Paper>
  );
}
