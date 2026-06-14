import {
  Group, NumberInput, Select, Slider, Stack, Switch, Text, TextInput, Tooltip,
} from "@mantine/core";
import { IconInfoCircle } from "@tabler/icons-react";
import type { StackOptionField } from "../api/client";

/** A label with an optional hover hint (info icon → tooltip). */
export function HintLabel({ label, hint }: { label: string; hint?: string | null }) {
  return (
    <Group gap={4} wrap="nowrap">
      <Text size="sm">{label}</Text>
      {hint ? (
        <Tooltip label={hint} multiline w={260} withArrow position="top-start">
          <IconInfoCircle size={14} color="var(--mantine-color-dimmed)" style={{ flexShrink: 0 }} />
        </Tooltip>
      ) : null}
    </Group>
  );
}

/** Renders one stacking option from the API schema (shared by Stack + Settings).
 * ``preferSlider`` (used by the editor) renders bounded numbers as a slider with
 * a live value readout, matching the History page's stretch/black controls. */
export function StackOptionControl({
  field, value, onChange, disabled, preferSlider,
}: {
  field: StackOptionField;
  value: unknown;
  onChange: (v: unknown) => void;
  disabled?: boolean;
  preferSlider?: boolean;
}) {
  const label = <HintLabel label={field.label} hint={field.help} />;

  if (preferSlider && (field.type === "int" || field.type === "float")
      && field.min != null && field.max != null) {
    const isInt = field.type === "int";
    const fallback = (field.default as number) ?? field.min;
    const num = value === null || value === undefined ? fallback : (value as number);
    return (
      <Stack gap={2}>
        <Group justify="space-between" gap="xs" wrap="nowrap">
          {label}
          <Text size="xs" c="dimmed">{isInt ? Math.round(num) : Number(num).toFixed(2)}</Text>
        </Group>
        <Slider
          min={field.min} max={field.max}
          step={field.step ?? (isInt ? 1 : 0.01)}
          value={Number(num)} disabled={disabled} label={null}
          onChange={(v) => onChange(isInt ? Math.round(v) : v)}
        />
      </Stack>
    );
  }

  switch (field.type) {
    case "bool":
      return (
        <Switch
          label={label} checked={Boolean(value)} disabled={disabled}
          onChange={(e) => onChange(e.currentTarget.checked)}
        />
      );
    case "enum":
      return (
        <Select
          label={label} data={field.options ?? []} value={(value as string) ?? null}
          disabled={disabled} allowDeselect={false} onChange={(v) => onChange(v)}
        />
      );
    case "int":
    case "float":
      return (
        <NumberInput
          label={label}
          value={value === null || value === undefined ? "" : (value as number)}
          min={field.min ?? undefined}
          max={field.max ?? undefined}
          step={field.step ?? (field.type === "int" ? 1 : 0.1)}
          decimalScale={field.type === "int" ? 0 : 2}
          disabled={disabled}
          onChange={(v) => onChange(v === "" ? null : Number(v))}
        />
      );
    default:
      return (
        <TextInput
          label={label} value={(value as string) ?? ""} disabled={disabled}
          onChange={(e) => onChange(e.currentTarget.value)}
        />
      );
  }
}
