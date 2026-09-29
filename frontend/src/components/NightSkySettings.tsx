/** Settings card for the night-sky starfield: the per-device switch, and a plain
 * explanation of what it does and where the preference lives.
 *
 * It sits *outside* the server-settings form on purpose, exactly like
 * `AmbientSettings` beside it — the preference is per-device `localStorage`, not
 * part of `config.json`, so it saves the moment you flip it and has nothing to do
 * with the "Save settings" button.
 */
import { Group, Paper, Stack, Switch, Text } from "@mantine/core";
import { IconStars } from "@tabler/icons-react";
import { useState } from "react";

import { isStarfieldEnabled, setStarfieldEnabled } from "../nightsky/prefs";

export function NightSkySettings() {
  const [on, setOn] = useState(() => isStarfieldEnabled());

  const toggle = (next: boolean) => {
    setOn(next);
    // Writes the preference and tells the mounted sky, so the stars stop (or
    // start) behind this card as you flip it.
    setStarfieldEnabled(next);
  };

  return (
    <Paper withBorder p="lg">
      <Stack>
        <Group gap={6}>
          <IconStars size={18} />
          <Text fw={600}>Drifting stars (this device)</Text>
        </Group>
        <Text size="sm" c="dimmed">
          A few faint layers of stars sliding very slowly behind the pages, at
          three different speeds so the sky has some depth to it. Turning it off
          leaves the dark night-sky colours and simply stops the stars. Either
          way they never appear behind a picture you are judging — the editor and
          the comparison view keep a plain neutral surround, which is what lets
          you trust the colours you see there.
        </Text>
        <Switch
          checked={on}
          onChange={(e) => toggle(e.currentTarget.checked)}
          label="Show drifting stars behind the pages"
          description="Remembered for this device only. Stars also hold still if your system asks for reduced motion, and pause whenever this tab is in the background."
        />
      </Stack>
    </Paper>
  );
}
