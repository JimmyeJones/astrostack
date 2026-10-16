import {
  Badge, Button, Group, Paper, SimpleGrid, Stack, Switch, Text, Title,
} from "@mantine/core";
import type { ReactNode } from "react";
import { BADGE_COLOR, BADGE_LABEL } from "./moreSettings";
import { pictureCards, type SettingsForm, type SettingsPatch } from "./picturesMade";

/**
 * Section 5 of the owner-approved Settings redesign
 * (`docs/design/settings-redesign.md`): "How pictures are made" — the four
 * hands-off picture choices as cards, each with its current value in plain
 * words, over the full stacking-defaults list. It replaces the four bare
 * switches that sat at the foot of Automation (outlier removal, drizzle, the
 * border trim, calibration) — same fields, same edit buffer, each still
 * stamped `data-setting` for the "nothing was removed" guard.
 *
 * The copy and the arithmetic live in `picturesMade.ts`; this file only draws.
 */
export function PicturesSection({
  form, onPatch, labelFor,
}: {
  form: SettingsForm;
  onPatch: (patch: SettingsPatch) => void;
  labelFor: (key: string, label: string) => ReactNode;
}) {
  return (
    <Stack gap="sm" data-testid="pictures-made">
      <Stack gap={4}>
        <Title order={3}>How pictures are made</Title>
        <Text size="sm" c="dimmed">
          The four choices that matter most when AstroStack stacks a target for
          you. Each card says what the next hands-off stack will do. A stack you
          set up yourself on a target's Stack page always uses exactly what you
          pick there, and a target's own “Save as defaults” beats these.
        </Text>
      </Stack>
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
        {pictureCards(form).map((c) => (
          <Paper key={c.id} withBorder p="md" data-testid={`picture-card-${c.id}`}>
            <Stack gap={6}>
              <Group justify="space-between" align="flex-start" gap="xs">
                <Text fw={700}>{c.title}</Text>
                <Badge variant="light" color={BADGE_COLOR.pictures} size="sm" style={{ flexShrink: 0 }}>
                  {BADGE_LABEL.pictures}
                </Badge>
              </Group>
              <Text size="sm" c="dimmed">{c.desc}</Text>
              <Badge variant="outline" color="gray" size="lg" tt="none" radius="sm"
                style={{ alignSelf: "flex-start" }} data-testid={`picture-value-${c.id}`}>
                {c.value}
              </Badge>
              <Text size="sm">{c.note}</Text>
              <Switch mt={4}
                label={labelFor(c.field, c.switchLabel)}
                checked={c.checked}
                onChange={(e) => onPatch({ [c.field]: e.currentTarget.checked })} />
              {c.overruled ? (
                <Stack gap={4} role="note">
                  <Text size="sm" c="orange" fw={500}>{c.overruled.text}</Text>
                  <Button size="compact-sm" variant="light" color="orange" mih={32}
                    style={{ alignSelf: "flex-start" }}
                    onClick={() => onPatch(c.overruled!.patch)}>
                    {c.overruled.button}
                  </Button>
                </Stack>
              ) : null}
              <Text size="xs" c="dimmed">Was: {c.was}</Text>
            </Stack>
          </Paper>
        ))}
      </SimpleGrid>
    </Stack>
  );
}
