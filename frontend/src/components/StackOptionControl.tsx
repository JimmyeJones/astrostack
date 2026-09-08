import {
  Group, NumberInput, Select, Slider, Stack, Switch, Text, TextInput, Tooltip,
  UnstyledButton,
} from "@mantine/core";
import { IconInfoCircle } from "@tabler/icons-react";
import { useState } from "react";
import type { StackOptionField } from "../api/client";

/**
 * A label with its plain-language explanation behind a small info icon.
 *
 * This is the app's *only* explanation surface for a descriptor-driven option,
 * and it is shared by the Stack form, Settings, the editor's op parameter panel
 * and the editor's print-size control — so whatever it does, it does everywhere
 * an engine parameter is offered.
 *
 * **The icon is a real button, and that is the point.** A phone has no hover, so
 * an explanation that only ever appears on `mouseenter` is, on the device this
 * app is mostly read on, not written at all. Worse, `HintLabel` is passed as the
 * `label` of a `Switch`/`Select`/`NumberInput`, which Mantine renders *inside a
 * `<label>`* — so the one thing a touch user could try, tapping the icon, used
 * to activate the control instead: tapping "what does this do?" on a checkbox
 * flipped the setting. The click handler now `preventDefault()`s exactly that.
 *
 * Nothing changes for a mouse: hovering still opens the same tooltip with the
 * same words, and the button carries no padding, so no row gets taller (the
 * standing "the pages are extremely busy" priority). Keyboard users gain it too
 * — the icon is focusable now, and focus opens the hint.
 */
export function HintLabel({ label, hint }: { label: string; hint?: string | null }) {
  // Two reasons a hint can be showing, kept apart so a pointer leaving doesn't
  // dismiss one the user deliberately tapped open. Blur closes both: on touch,
  // tapping anything else takes focus away, which is how a tapped hint is
  // dismissed without a second, precise tap on a 14 px target.
  const [tapped, setTapped] = useState(false);
  const [pointed, setPointed] = useState(false);
  return (
    <Group gap={4} wrap="nowrap">
      <Text size="sm">{label}</Text>
      {hint ? (
        <Tooltip label={hint} multiline w={260} withArrow position="top-start"
          opened={tapped || pointed}>
          <UnstyledButton
            // A <span>, not a <button>, and that is load-bearing: Mantine
            // renders this inside the control's own <label>, and a <button>
            // there is a *labelable* element — so the field's label would name
            // two controls at once, and "find the ASTAP path field" would become
            // ambiguous for a screen reader exactly as it does for a test query.
            // A span carries the role explicitly instead.
            component="span" role="button" tabIndex={0}
            // Deliberately generic rather than "What does <label> do?": the
            // label text is how the control itself is found, so repeating it
            // here would collide the same way. A reader hears the field's own
            // label immediately before this, in the same <label>.
            aria-label="What does this do?"
            onClick={(e) => {
              // Without this the surrounding <label> forwards the tap to the
              // control it labels — reading the hint would change the setting.
              e.preventDefault();
              setTapped((open) => !open);
            }}
            onKeyDown={(e) => {
              if (e.key !== "Enter" && e.key !== " ") return;
              e.preventDefault();   // Space would scroll the panel
              setTapped((open) => !open);
            }}
            onMouseEnter={() => setPointed(true)}
            onMouseLeave={() => setPointed(false)}
            onFocus={() => setPointed(true)}
            onBlur={() => { setPointed(false); setTapped(false); }}
            style={{ display: "inline-flex", lineHeight: 0, flexShrink: 0,
              cursor: "pointer" }}
          >
            <IconInfoCircle size={14} color="var(--mantine-color-dimmed)" />
          </UnstyledButton>
        </Tooltip>
      ) : null}
    </Group>
  );
}

/** How a `unit: "percent"` field is shown versus how it is stored.
 *
 * The engine's `lucky_fraction` is a fraction in (0, 1] and stays one — but a
 * beginner reading "Lucky 50%" on their own picture should be able to type
 * **50**, not 0.5, and the descriptor-driven form sends whatever the input holds
 * straight through. So the conversion lives here, at the boundary, for any field
 * that asks for it: nothing about the stored value, the engine field or its
 * bounds changes.
 *
 * Both directions round away binary-fraction noise (0.35 × 100 is
 * 35.000000000000004), so the round-trip a saved recipe depends on — stored 0.35
 * → shown 35 → stored 0.35 — is exact rather than nearly exact.
 */
export function percentFromFraction(fraction: number): number {
  return Math.round(fraction * 10000) / 100;
}

export function fractionFromPercent(percent: number): number {
  return Math.round(percent * 100) / 10000;
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
  // A percent field is shown in percent *everywhere* — value, bounds and step —
  // so the slider, the readout and the typed number all speak one unit. `show`
  // and `store` are the identity for every other field, so nothing else moves.
  const pct = field.unit === "percent";
  const show = (n: number) => (pct ? percentFromFraction(n) : n);
  const store = (n: number) => (pct ? fractionFromPercent(n) : n);

  if (preferSlider && (field.type === "int" || field.type === "float")
      && field.min != null && field.max != null) {
    const isInt = field.type === "int";
    const step = show(field.step ?? (isInt ? 1 : 0.01));
    const fallback = (field.default as number) ?? field.min;
    const num = show(value === null || value === undefined
      ? fallback : (value as number));
    return (
      <Stack gap={2}>
        <Group justify="space-between" gap="xs" wrap="nowrap" align="center">
          {label}
          {/* Editable readout: drag the slider for a coarse value, or type an exact
           * one here. Both share the field's value/min/max/step and clamp on blur. */}
          <NumberInput
            size="xs" hideControls w={pct ? 80 : 72} aria-label={`${field.label} value`}
            value={Number(num)} min={show(field.min)} max={show(field.max)} step={step}
            decimalScale={isInt || pct ? 0 : 2} suffix={pct ? " %" : undefined}
            clampBehavior="blur" disabled={disabled}
            styles={{ input: { textAlign: "right" } }}
            onChange={(v) => {
              if (v === "" || v === null) return;
              const n = Number(v);
              if (!Number.isFinite(n)) return;
              onChange(isInt ? Math.round(n) : store(n));
            }}
          />
        </Group>
        <Slider
          min={show(field.min)} max={show(field.max)} step={step}
          value={Number(num)} disabled={disabled} label={null}
          onChange={(v) => onChange(isInt ? Math.round(v) : store(v))}
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
    case "enum": {
      const data = (field.options ?? []).map((o) => ({
        value: o, label: field.option_labels?.[o] ?? o,
      }));
      return (
        <Select
          label={label} data={data} value={(value as string) ?? null}
          disabled={disabled} allowDeselect={false} onChange={(v) => onChange(v)}
        />
      );
    }
    case "int":
    case "float":
      return (
        <NumberInput
          label={label}
          value={value === null || value === undefined
            ? "" : show(value as number)}
          min={field.min == null ? undefined : show(field.min)}
          max={field.max == null ? undefined : show(field.max)}
          step={show(field.step ?? (field.type === "int" ? 1 : 0.1))}
          decimalScale={field.type === "int" || pct ? 0 : 2}
          suffix={pct ? " %" : undefined}
          disabled={disabled}
          onChange={(v) => onChange(v === "" ? null : store(Number(v)))}
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
