import {
  Badge, Group, NumberInput, Paper, SimpleGrid, Stack, Switch, Text, ThemeIcon, Title,
} from "@mantine/core";
import { IconShieldCheck } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { BADGE_COLOR, BADGE_LABEL } from "./moreSettings";
import {
  HANDS_OFF_PRESETS, handsOffPatch, handsOffPreset, PIPELINE_STEPS, pipelineUnsaved,
  quietWords, stepState, stepStatusText,
  type SettingsForm, type SettingsPatch,
} from "./handsOff";

/**
 * Sections 1–2 of the owner-approved Settings redesign
 * (`docs/design/settings-redesign.md`): the three "how hands-off?" cards, the
 * six steps a new sub goes through as a numbered row, and the two cards that
 * shape a hands-off stack (when to start one; what to do with two targets in
 * one batch).
 *
 * The copy and the arithmetic live in `handsOff.ts`; this file only draws them.
 * Every control writes the page's one shared edit buffer, like every other
 * section, so a picked card is a preview until **Save settings** — and the
 * section says so while it is.
 *
 * `labelFor` is the page's own `lbl()`, so the two stack-trigger boxes keep the
 * hover hint and the `data-setting` stamp the "nothing was removed" guard reads.
 */
export function HandsOffSection({
  form, saved, onPatch, labelFor,
}: {
  form: SettingsForm;
  /** The settings as last saved, to tell a preview from what is in force. */
  saved: SettingsForm;
  onPatch: (patch: SettingsPatch) => void;
  labelFor: (key: string, label: string) => ReactNode;
}) {
  const picked = handsOffPreset(form);
  const savedPreset = handsOffPreset(saved);
  const unsaved = pipelineUnsaved(form, saved);
  const stackOn = Boolean(form.auto_stack);
  const num = (k: string) => (typeof form[k] === "number" ? (form[k] as number) : "");

  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Title order={3}>How hands-off should AstroStack be?</Title>
        <Text size="sm" c="dimmed">
          Pick one — it sets the steps below for you. You can still fine-tune each
          step afterwards.
        </Text>
        <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
          {HANDS_OFF_PRESETS.map((p) => {
            const on = picked === p.id;
            return (
              <Paper
                key={p.id}
                component="button"
                type="button"
                withBorder
                p="md"
                aria-pressed={on}
                onClick={() => onPatch(handsOffPatch(p.id))}
                style={{
                  textAlign: "left",
                  cursor: "pointer",
                  minHeight: 44,
                  borderWidth: 2,
                  borderColor: on ? "var(--mantine-color-orange-6)" : undefined,
                  background: on ? "var(--mantine-color-orange-light)" : undefined,
                }}
              >
                <Stack gap={6} align="flex-start">
                  <Text fw={700}>{p.title}</Text>
                  <Text size="sm" c="dimmed">{p.desc}</Text>
                  <Badge variant={on ? "filled" : "light"} color={on ? "orange" : "gray"} size="sm">
                    {savedPreset === p.id ? "Your saved setup" : p.tag}
                  </Badge>
                </Stack>
              </Paper>
            );
          })}
        </SimpleGrid>
        {picked === null ? (
          <Text size="sm" c="dimmed" data-testid="hands-off-custom">
            Custom — your own mix of the steps below, so none of the three is picked.
          </Text>
        ) : null}
        {unsaved ? (
          <Text size="sm" c="orange" fw={500} data-testid="hands-off-unsaved">
            Not saved yet — press Save settings to use this.
          </Text>
        ) : null}
      </Stack>

      <Stack gap="xs">
        <Group justify="space-between" align="flex-start" gap="xs">
          <Stack gap={4} style={{ flex: "1 1 320px" }}>
            <Title order={3}>When new photos land in your drop folder</Title>
            <Text size="sm" c="dimmed">
              Each step hands its work to the next. Switch off a step and the steps
              that need it wait until you do it yourself — press Scan incoming, or
              upload from the browser.
            </Text>
          </Stack>
          <Group gap={6} wrap="nowrap">
            <ThemeIcon variant="light" color="teal" size="sm" radius="xl">
              <IconShieldCheck size={14} />
            </ThemeIcon>
            <Text size="sm" c="teal" fw={500}>
              Your raw subs are only ever read — never moved or deleted.
            </Text>
          </Group>
        </Group>

        <SimpleGrid cols={{ base: 2, md: 3 }} spacing="sm" component="ol"
          style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {PIPELINE_STEPS.map((s, i) => {
            const state = stepState(form, s.field);
            const live = state === "auto";
            return (
              <Paper
                key={s.field}
                component="li"
                withBorder
                p="sm"
                data-setting={s.field}
                data-step-state={state}
                style={{ opacity: live ? 1 : 0.8 }}
              >
                <Stack gap={6} h="100%">
                  <Group justify="space-between" wrap="nowrap">
                    <Group gap="xs" wrap="nowrap">
                      <ThemeIcon radius="xl" size="md" variant={live ? "filled" : "light"}
                        color={live ? "orange" : "gray"}>
                        <Text size="sm" fw={700}>{i + 1}</Text>
                      </ThemeIcon>
                      {/* The old switch's hover hint rides on the new name. */}
                      <Text fw={700} component="div">{labelFor(s.field, s.title)}</Text>
                    </Group>
                    <Switch
                      aria-label={`${s.title} automatically`}
                      checked={Boolean(form[s.field])}
                      onChange={(e) => onPatch({ [s.field]: e.currentTarget.checked })}
                    />
                  </Group>
                  <Text size="sm" c="dimmed">{s.desc(quietWords(form.watch_quiet_period_s))}</Text>
                  <Text size="xs" fw={500} mt="auto"
                    c={state === "auto" ? "teal" : state === "waiting" ? "orange" : "dimmed"}>
                    {stepStatusText(state)}
                  </Text>
                  <Text size="xs" c="dimmed">Was: {s.was}</Text>
                </Stack>
              </Paper>
            );
          })}
        </SimpleGrid>

        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          <Paper withBorder p="md">
            <Stack gap="xs">
              <Group justify="space-between" align="flex-start" wrap="nowrap" gap="xs">
                <Text fw={600}>Stack once there are enough frames</Text>
                <Badge variant="light" color={BADGE_COLOR.pictures} size="sm" style={{ flexShrink: 0 }}>
                  {BADGE_LABEL.pictures}
                </Badge>
              </Group>
              <Text size="sm" c="dimmed">
                {stackOn
                  ? "So a stack isn't started while you're still shooting, or from a single frame."
                  : "Only used when Stack (step 5) runs automatically."}
              </Text>
              <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="xs">
                <NumberInput label={labelFor("auto_stack_min_frames", "Wait for at least this many placed frames")}
                  value={num("auto_stack_min_frames")} min={1} max={1000}
                  disabled={!stackOn}
                  onChange={(v) => onPatch({ auto_stack_min_frames: Number(v) })} />
                <NumberInput label={labelFor("auto_stack_settle_min", "Wait for the night to settle (minutes)")}
                  value={num("auto_stack_settle_min")} min={0} max={1440}
                  disabled={!stackOn}
                  onChange={(v) => onPatch({ auto_stack_settle_min: Number(v) })} />
              </SimpleGrid>
              <Text size="xs" c="dimmed">
                Was: Hands-off auto-stack: minimum located subs · wait for the night to settle
              </Text>
            </Stack>
          </Paper>
          <Paper withBorder p="md">
            <Stack gap="xs">
              <Group justify="space-between" align="flex-start" wrap="nowrap" gap="xs">
                <Text fw={600}>Two targets in one batch?</Text>
                <Badge variant="light" color={BADGE_COLOR.safe} size="sm" style={{ flexShrink: 0 }}>
                  {BADGE_LABEL.safe}
                </Badge>
              </Group>
              <Switch
                label={labelFor("mixed_pointing_guard",
                  "If a hands-off stack looks like two different patches of sky, skip it and tell you instead of blending them")}
                checked={Boolean(form.mixed_pointing_guard)}
                onChange={(e) => onPatch({ mixed_pointing_guard: e.currentTarget.checked })}
              />
              <Text size="xs" c="dimmed">
                Was: Skip a hands-off stack when the batch looks like two different targets
              </Text>
            </Stack>
          </Paper>
        </SimpleGrid>
      </Stack>
    </Stack>
  );
}
