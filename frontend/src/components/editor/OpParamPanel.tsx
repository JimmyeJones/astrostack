import { Accordion, Stack, Text } from "@mantine/core";
import type { EditOp, StackOptionField } from "../../api/client";
import { HintLabel, StackOptionControl } from "../StackOptionControl";
import { CurvesWidget } from "./CurvesWidget";

/** Renders the parameter form for one operation instance, reusing the shared
 * StackOptionControl for scalar params and a CurvesWidget for curve params. */
export function OpParamPanel({ spec, params, onChange }: {
  spec: EditOp;
  params: Record<string, unknown>;
  onChange: (params: Record<string, unknown>) => void;
}) {
  const set = (key: string, v: unknown) => onChange({ ...params, [key]: v });
  const simple = spec.params.filter((p) => p.group !== "advanced");
  const advanced = spec.params.filter((p) => p.group === "advanced");

  const field = (p: StackOptionField) => {
    if (p.type === "curve") {
      return (
        <div key={p.key}>
          <HintLabel label={p.label} hint={p.help} />
          <CurvesWidget
            points={(params[p.key] as [number, number][]) ?? [[0, 0], [1, 1]]}
            onChange={(pts) => set(p.key, pts)}
          />
        </div>
      );
    }
    const disabled = p.depends_on ? !params[p.depends_on] : false;
    return (
      <StackOptionControl
        key={p.key} field={p} value={params[p.key]} disabled={disabled}
        onChange={(v) => set(p.key, v)}
      />
    );
  };

  if (!spec.params.length) {
    return <Text size="sm" c="dimmed">This operation has no parameters.</Text>;
  }

  return (
    <Stack gap="sm">
      {simple.map(field)}
      {advanced.length ? (
        <Accordion variant="separated">
          <Accordion.Item value="adv">
            <Accordion.Control>Advanced</Accordion.Control>
            <Accordion.Panel><Stack gap="sm">{advanced.map(field)}</Stack></Accordion.Panel>
          </Accordion.Item>
        </Accordion>
      ) : null}
    </Stack>
  );
}
