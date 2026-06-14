import { Accordion, ActionIcon, Button, Group, Stack, Text, Tooltip } from "@mantine/core";
import { IconRestore } from "@tabler/icons-react";
import type { EditOp, Histogram, StackOptionField } from "../../api/client";
import { HintLabel, StackOptionControl } from "../StackOptionControl";
import { CurvesWidget } from "./CurvesWidget";

/** Renders the parameter form for one operation instance. Scalars use the shared
 * StackOptionControl (as sliders here), curves use the CurvesWidget (with the
 * histogram behind it), and every param can be reset to its schema default. */
export function OpParamPanel({ spec, params, onChange, histogram }: {
  spec: EditOp;
  params: Record<string, unknown>;
  onChange: (params: Record<string, unknown>) => void;
  histogram?: Histogram;
}) {
  const set = (key: string, v: unknown) => onChange({ ...params, [key]: v });
  const simple = spec.params.filter((p) => p.group !== "advanced");
  const advanced = spec.params.filter((p) => p.group === "advanced");

  const isDefault = (p: StackOptionField) =>
    JSON.stringify(params[p.key] ?? p.default) === JSON.stringify(p.default);
  const resetAll = () =>
    onChange(Object.fromEntries(spec.params.map((p) => [p.key, p.default])));

  const control = (p: StackOptionField) => {
    if (p.type === "curve") {
      return (
        <div>
          <HintLabel label={p.label} hint={p.help} />
          <CurvesWidget
            points={(params[p.key] as [number, number][]) ?? [[0, 0], [1, 1]]}
            histogram={histogram}
            onChange={(pts) => set(p.key, pts)}
          />
        </div>
      );
    }
    const disabled = p.depends_on ? !params[p.depends_on] : false;
    return (
      <StackOptionControl
        field={p} value={params[p.key]} disabled={disabled} preferSlider
        onChange={(v) => set(p.key, v)}
      />
    );
  };

  const row = (p: StackOptionField) => (
    <Group key={p.key} align="flex-end" wrap="nowrap" gap={6}>
      <div style={{ flex: 1, minWidth: 0 }}>{control(p)}</div>
      <Tooltip label="Reset to default" withArrow>
        <ActionIcon variant="subtle" size="sm" color="gray" disabled={isDefault(p)}
          onClick={() => set(p.key, p.default)} aria-label={`Reset ${p.label}`}>
          <IconRestore size={14} />
        </ActionIcon>
      </Tooltip>
    </Group>
  );

  if (!spec.params.length) {
    return <Text size="sm" c="dimmed">This operation has no parameters.</Text>;
  }

  return (
    <Stack gap="sm">
      <Group justify="flex-end" gap={4}>
        <Button size="compact-xs" variant="subtle" color="gray"
          leftSection={<IconRestore size={12} />} onClick={resetAll}>
          Reset op
        </Button>
      </Group>
      {simple.map(row)}
      {advanced.length ? (
        <Accordion variant="separated">
          <Accordion.Item value="adv">
            <Accordion.Control>Advanced</Accordion.Control>
            <Accordion.Panel><Stack gap="sm">{advanced.map(row)}</Stack></Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      ) : null}
    </Stack>
  );
}
