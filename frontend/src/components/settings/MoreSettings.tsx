import {
  Alert, Badge, Button, Group, NumberInput, Paper, SimpleGrid, Slider, Stack,
  Switch, TagsInput, Text, TextInput, Title,
} from "@mantine/core";
import { IconAlertTriangle, IconSearch } from "@tabler/icons-react";
import { useState, type ReactNode } from "react";
import type { FolderConflict } from "../../settingsFolders";
import {
  BADGE_COLOR, BADGE_LABEL, filterMoreGroups, MORE_SETTINGS_GROUPS,
  moreSettingChanged, moreSettingDefaultLabel, moreSettingResetPatch, moreSettingWarning,
  type MoreCtx, type MoreSetting, type SettingsForm, type SettingsPatch,
} from "./moreSettings";

/**
 * "More settings" — slice 1 of the owner-approved Settings redesign
 * (`docs/design/settings-redesign.md`).
 *
 * The copy, the groupings and the warnings live in `moreSettings.ts`; this file
 * only draws them. The one thing worth knowing here is what the section *is*:
 * not an "expert" drawer to be scared of, but the plain-words home for the
 * settings the owner said looked scary — each one saying what it does, warning
 * the moment it leaves its default, and offering the way back.
 *
 * It is **additive**. Every control here still lives on the section it always
 * did (both read and write the one shared edit buffer the page keeps, so they
 * can never disagree), which is how "nothing is removed" is kept while the
 * later slices rebuild the rest of the page. That is also why each card prints
 * `Was: …`: the old label is how somebody who knows this app finds the card,
 * and the search box matches it too.
 */
export function MoreSettingsSection({
  form, onPatch, ctx, conflict, resolvedIncoming, resolvedLibrary, saveRow,
}: {
  form: SettingsForm;
  /** Merge a partial patch into the page's shared edit buffer. */
  onPatch: (patch: SettingsPatch) => void;
  ctx: MoreCtx;
  /** The live folder-layout refusal, so this card shows it as the old one does. */
  conflict: FolderConflict | null;
  resolvedIncoming?: string;
  resolvedLibrary?: string;
  saveRow: ReactNode;
}) {
  const [query, setQuery] = useState("");
  const groups = filterMoreGroups(MORE_SETTINGS_GROUPS, query);

  return (
    <Paper withBorder p="lg">
      <Stack>
        <Title order={3}>More settings</Title>
        <Text size="sm" c="dimmed">
          Everything else, in plain words. You can change any of these — each one
          says what it does, warns you the moment your choice has a side effect,
          and offers a one-click way back to how it shipped.
        </Text>

        <TextInput
          label="Find a setting"
          description="Matches the old names too, so “CIDR” or “quiet period” still finds it."
          placeholder="e.g. memory, folders, quiet period"
          leftSection={<IconSearch size={16} />}
          value={query}
          onChange={(e) => setQuery(e.currentTarget.value)}
        />

        <Group gap="md" wrap="wrap">
          {(["safe", "pictures", "side-effects"] as const).map((b) => (
            <Badge key={b} variant="light" color={BADGE_COLOR[b]} size="sm">
              {BADGE_LABEL[b]}
            </Badge>
          ))}
        </Group>

        {groups.length === 0 ? (
          <Text size="sm" c="dimmed">
            Nothing here matches “{query}”. It may be one of the settings on the
            other tabs above — they all stay where they were.
          </Text>
        ) : groups.map((g) => (
          <Stack key={g.title} gap="xs">
            <Text fw={600}>{g.title}</Text>
            <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm">
              {g.items.map((d) => (
                <MoreCard
                  key={d.id} d={d} form={form} ctx={ctx} onPatch={onPatch}
                  conflict={conflict} resolvedIncoming={resolvedIncoming}
                  resolvedLibrary={resolvedLibrary}
                />
              ))}
            </SimpleGrid>
          </Stack>
        ))}

        {saveRow}
      </Stack>
    </Paper>
  );
}

function MoreCard({
  d, form, ctx, onPatch, conflict, resolvedIncoming, resolvedLibrary,
}: {
  d: MoreSetting;
  form: SettingsForm;
  ctx: MoreCtx;
  onPatch: (patch: SettingsPatch) => void;
  conflict: FolderConflict | null;
  resolvedIncoming?: string;
  resolvedLibrary?: string;
}) {
  const changed = moreSettingChanged(d, form, ctx);
  const warning = moreSettingWarning(d, form, ctx);

  return (
    <Paper
      withBorder p="md"
      bg={changed ? "var(--mantine-color-yellow-light)" : undefined}
      // Which `Settings` fields this card can write. The page-wide "every
      // setting is still on the page" guard reads it, so a control that moves
      // here from its old section is still accounted for.
      data-settings={d.keys.join(" ")}
    >
      <Stack gap="xs" h="100%">
        <Group justify="space-between" align="flex-start" wrap="nowrap" gap="xs">
          <Text fw={600}>{d.title}</Text>
          <Badge variant="light" color={BADGE_COLOR[d.badge]} size="sm" style={{ flexShrink: 0 }}>
            {BADGE_LABEL[d.badge]}
          </Badge>
        </Group>
        <Text size="sm" c="dimmed">{d.desc}</Text>

        <MoreControl d={d} form={form} ctx={ctx} onPatch={onPatch} />
        <MoreExtras
          d={d} form={form} ctx={ctx} onPatch={onPatch} conflict={conflict}
          resolvedIncoming={resolvedIncoming} resolvedLibrary={resolvedLibrary}
        />

        {warning ? (
          <Alert
            role="note" color="yellow" variant="light" p="sm"
            icon={<IconAlertTriangle size={18} />}
            title="Heads up"
          >
            <Stack gap="xs" align="flex-start">
              <Text size="sm">{warning}</Text>
              <Button
                size="compact-sm" variant="default"
                onClick={() => onPatch(moreSettingResetPatch(d, ctx))}
              >
                Back to default ({moreSettingDefaultLabel(d, ctx)})
              </Button>
            </Stack>
          </Alert>
        ) : null}

        <Text size="xs" c="dimmed" mt="auto">Was: {d.was}</Text>
      </Stack>
    </Paper>
  );
}

function MoreControl({
  d, form, ctx, onPatch,
}: {
  d: MoreSetting;
  form: SettingsForm;
  ctx: MoreCtx;
  onPatch: (patch: SettingsPatch) => void;
}) {
  if (d.kind === "switch") {
    return (
      <Switchy
        label={d.title} checked={Boolean(form[d.field])}
        onChange={(on) => onPatch({ [d.field]: on })}
      />
    );
  }
  if (d.kind === "choice") {
    const selected = d.selected(form, ctx);
    return (
      <Group role="group" aria-label={d.title} gap="xs" wrap="wrap">
        {d.choices(form, ctx).map((c) => (
          <Button
            key={c.id}
            size="compact-md"
            variant={c.id === selected ? "filled" : "default"}
            aria-pressed={c.id === selected}
            // The synthetic "whatever is stored" chip is shown, never offered:
            // a value this card has no button for stays exactly as it is.
            disabled={c.readOnly}
            onClick={() => onPatch(c.patch)}
          >
            {c.label}
          </Button>
        ))}
      </Group>
    );
  }
  const v = d.value(form);
  return (
    <Stack gap={2}>
      <Text size="sm" fw={500}>{d.format(v)}</Text>
      <Slider
        min={d.min} max={d.max} step={d.step} value={v} label={null}
        thumbLabel={d.title}
        onChange={(next) => onPatch(d.patch(next))}
      />
      <Group justify="space-between">
        <Text size="xs" c="dimmed">{d.minLabel}</Text>
        <Text size="xs" c="dimmed">{d.maxLabel}</Text>
      </Group>
    </Stack>
  );
}

/**
 * The boxes a card needs beyond its own control — the folder paths, the
 * telescope's address, the intervals. They appear under the choice that calls
 * for them; every one of them also still has its own field on the tab it has
 * always lived on, so nothing here is the only way to reach a setting.
 */
function MoreExtras({
  d, form, ctx, onPatch, conflict, resolvedIncoming, resolvedLibrary,
}: {
  d: MoreSetting;
  form: SettingsForm;
  ctx: MoreCtx;
  onPatch: (patch: SettingsPatch) => void;
  conflict: FolderConflict | null;
  resolvedIncoming?: string;
  resolvedLibrary?: string;
}) {
  if (d.kind === "choice" && d.id === "folders" && d.selected(form, ctx) === "custom") {
    return (
      <Stack gap="xs">
        <TextInput
          label="Main folder" value={(form.data_root as string) ?? ""}
          description="Everything else sits under this unless you say otherwise."
          error={conflict?.field === "data_root" ? conflict.message : undefined}
          onChange={(e) => onPatch({ data_root: e.currentTarget.value })}
        />
        <TextInput
          label="Drop folder (where your new subs arrive)"
          value={(form.incoming_dir as string) ?? ""}
          placeholder={resolvedIncoming}
          onChange={(e) => onPatch({ incoming_dir: e.currentTarget.value })}
        />
        <TextInput
          label="Library folder (stacks and pictures)"
          value={(form.library_root as string) ?? ""}
          placeholder={resolvedLibrary}
          error={conflict?.field === "library_root" ? conflict.message : undefined}
          onChange={(e) => onPatch({ library_root: e.currentTarget.value })}
        />
      </Stack>
    );
  }
  if (d.kind === "switch" && d.id === "seestar_enabled" && Boolean(form.seestar_enabled)) {
    return (
      <NumberInput
        label="Check on it every" suffix=" seconds" min={1} max={3600} w={200}
        value={typeof form.seestar_poll_interval_s === "number" ? form.seestar_poll_interval_s : 5}
        onChange={(v) => onPatch({ seestar_poll_interval_s: v === "" ? 5 : Number(v) })}
      />
    );
  }
  if (d.kind === "choice" && d.id === "seestar_find") {
    return d.selected(form, ctx) === "typed" ? (
      <TagsInput
        label="The telescope's address" placeholder="e.g. 192.168.1.50"
        value={(form.seestar_known_ips as string[]) ?? []}
        onChange={(v) => onPatch({ seestar_known_ips: v })}
      />
    ) : (
      <Stack gap="xs">
        <TextInput
          label="Part of the network to search"
          placeholder="work it out for me"
          description="Leave blank unless your network is unusual."
          value={(form.seestar_scan_subnet as string) ?? ""}
          onChange={(e) => onPatch({ seestar_scan_subnet: e.currentTarget.value })}
        />
        <NumberInput
          label="Look again every" suffix=" seconds" min={30} max={86400} w={200}
          value={typeof form.seestar_scan_interval_s === "number" ? form.seestar_scan_interval_s : 300}
          onChange={(v) => onPatch({ seestar_scan_interval_s: v === "" ? 300 : Number(v) })}
        />
      </Stack>
    );
  }
  return null;
}

/**
 * A switch whose accessible name is the card's title.
 *
 * The card already shows that title as its heading, so repeating it beside the
 * switch would say everything twice; `aria-label` keeps it reachable by name
 * for a screen reader and for a test, and the visible label says which way it
 * is set.
 */
function Switchy({ label, checked, onChange }: {
  label: string; checked: boolean; onChange: (on: boolean) => void;
}) {
  return (
    <Switch
      aria-label={label}
      checked={checked}
      label={checked ? "On" : "Off"}
      onChange={(e) => onChange(e.currentTarget.checked)}
    />
  );
}
