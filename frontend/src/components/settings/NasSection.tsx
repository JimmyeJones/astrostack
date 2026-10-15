import {
  Alert, Badge, Box, Group, NumberInput, SimpleGrid, Stack, Text, Title,
} from "@mantine/core";
import { IconInfoCircle } from "@tabler/icons-react";
import type { ReactNode } from "react";
import type { SystemInfo } from "../../api/client";
import { stackBudgetNote } from "../../stackBudgetNote";
import { MoreCard } from "./MoreSettings";
import {
  BADGE_COLOR, BADGE_LABEL, moreSettingById, type MoreCtx, type SettingsForm,
  type SettingsPatch,
} from "./moreSettings";
import { memoryBar, memoryHeadline } from "./observingSite";

const OTHER = "var(--mantine-color-indigo-7)";
const ROOM = "var(--mantine-color-orange-4)";

/**
 * Section 6 of the owner-approved Settings redesign
 * (`docs/design/settings-redesign.md`): "How hard your NAS works" — the
 * machine's memory drawn as a bar (other apps / room one stack may use / kept
 * free), the memory limit and processor-cores cards (the same cards "More
 * settings" shows, warnings and Back to default included), and an exact-figure
 * box for a memory limit the slider can't land on.
 *
 * It replaces the "Memory" card at the foot of the Stacking tab and takes the
 * cores box off Plate solving, where a beginner would never look for it (the
 * cores card's own `data-settings` stamp is what the "nothing was removed"
 * guard finds now). The
 * two advisories that card carried — which control is really setting the
 * budget, and a budget above the RAM that is free — are kept word for word.
 */
export function NasSection({
  form, onPatch, labelFor, memory, ctx,
}: {
  form: SettingsForm;
  onPatch: (patch: SettingsPatch) => void;
  labelFor: (key: string, label: string) => ReactNode;
  memory: SystemInfo["memory"] | undefined;
  ctx: MoreCtx;
}) {
  const bar = memoryBar(memory);
  const note = stackBudgetNote(memory);
  const budget = form.max_stack_memory_gb;
  const avail = memory?.available_gb;
  // Advisory only: a budget higher than the box's available RAM re-opens the
  // OOM door the guard exists to close. Silent where the env override is in
  // force: the field it is warning about is not the number any stack will be
  // priced against, and the note above has already said so.
  const overRam = memory?.stack_budget_source !== "env"
    && typeof budget === "number" && typeof avail === "number" && budget > avail;

  return (
    <Stack gap="sm" data-testid="nas-section">
      <Group justify="space-between" align="flex-start" gap="xs">
        <Stack gap={4} style={{ flex: "1 1 320px" }}>
          <Title order={3}>How hard your NAS works</Title>
          <Text size="sm" c="dimmed">
            Stacking is heavy. These keep it from crowding out everything else
            your NAS does.
          </Text>
        </Stack>
        <Badge variant="light" color={BADGE_COLOR.safe} size="sm" style={{ flexShrink: 0 }}>
          {BADGE_LABEL.safe}
        </Badge>
      </Group>

      <Stack gap={6}>
        <Text size="sm">
          <b>Memory for stacking:</b>{" "}
          <span data-testid="memory-headline">{memoryHeadline(form)}</span>
        </Text>
        {bar ? (
          <>
            <Box aria-hidden data-testid="memory-bar" style={{
              height: 18, borderRadius: 9, overflow: "hidden", display: "flex",
              border: "1px solid var(--mantine-color-default-border)",
              background: "var(--mantine-color-default)",
            }}>
              <span data-part="other" style={{ width: `${bar.otherPct}%`, background: OTHER }} />
              <span data-part="room" style={{ width: `${bar.roomPct}%`, background: ROOM }} />
            </Box>
            {/* The legend carries the numbers, so the bar is never the only
                place a figure lives (it is hidden from screen readers). */}
            <Group gap="md" wrap="wrap">
              <LegendItem swatch={OTHER} text={`Other apps on your NAS: ${bar.otherGb} GB`} />
              <LegendItem swatch={ROOM} text={`Room one stack may use: ${bar.roomGb} GB`} />
              <LegendItem swatch={null} text={`Kept free: ${bar.freeGb} GB`} />
            </Group>
            <Text size="xs" c="dimmed">
              Out of {bar.totalGb} GB, as it stands right now — other apps' share
              goes up and down through the day.
            </Text>
          </>
        ) : null}
        {note ? (
          note.tone === "warning" ? (
            <Alert color="orange" icon={<IconInfoCircle size={16} />}
              title="This field is being overridden">
              {note.text}
            </Alert>
          ) : (
            <Text size="sm" c="dimmed">{note.text}</Text>
          )
        ) : null}
      </Stack>

      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
        <MoreCard d={moreSettingById("max_stack_memory_gb")} form={form} ctx={ctx} onPatch={onPatch} />
        <MoreCard d={moreSettingById("cpu_workers")} form={form} ctx={ctx} onPatch={onPatch} />
      </SimpleGrid>

      <NumberInput label={labelFor("max_stack_memory_gb", "Exact memory limit (GB)")}
        description="For a figure the slider can't land on. Leave it blank for Automatic."
        value={typeof budget === "number" ? budget : ""} min={0.5} max={1024} step={0.5}
        decimalScale={1} placeholder="Automatic" w={{ base: "100%", xs: 300 }}
        onChange={(v) => onPatch({ max_stack_memory_gb: v === "" ? null : Number(v) })} />
      {overRam ? (
        <Alert color="orange" icon={<IconInfoCircle size={16} />}
          title="Budget is higher than this machine's available RAM">
          You set {budget} GB, but only about {avail} GB is currently
          available on this box. A stack that actually uses this much could
          still run out of memory. Consider lowering it, or leave it blank
          for the automatic ~70%-of-RAM cap.
        </Alert>
      ) : null}
    </Stack>
  );
}

function LegendItem({ swatch, text }: { swatch: string | null; text: string }) {
  return (
    <Group gap={6} wrap="nowrap">
      <span aria-hidden style={{
        width: 12, height: 12, borderRadius: 3, display: "inline-block",
        background: swatch ?? "transparent",
        border: swatch ? undefined : "1px solid var(--mantine-color-dimmed)",
      }} />
      <Text size="xs" c="dimmed">{text}</Text>
    </Group>
  );
}
