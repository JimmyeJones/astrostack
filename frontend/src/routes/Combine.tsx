import {
  Alert, Button, Group, Loader, NumberInput, Paper, Select, Stack, Text,
  TextInput, Title,
} from "@mantine/core";
import { IconInfoCircle, IconPalette } from "@tabler/icons-react";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";

const CHANNELS = ["L", "R", "G", "B"] as const;
type Channel = (typeof CHANNELS)[number];

interface Slot {
  safe: string | null;
  runId: string | null;
  weight: number;
}

const CHANNEL_LABEL: Record<Channel, string> = {
  L: "Luminance (L)", R: "Red (R)", G: "Green (G)", B: "Blue (B)",
};

function ChannelRow({
  channel, slot, targets, onChange,
}: {
  channel: Channel;
  slot: Slot;
  targets: { value: string; label: string }[];
  onChange: (s: Slot) => void;
}) {
  // Runs for the chosen target populate the run picker.
  const runs = useQuery({
    queryKey: ["runs", slot.safe],
    queryFn: () => api.listStackRuns(slot.safe as string),
    enabled: Boolean(slot.safe),
  });
  const runOpts = (runs.data ?? [])
    .filter((r) => r.has_fits)
    .map((r) => ({
      value: String(r.id),
      label: `${r.output_basename} (${r.canvas_w}×${r.canvas_h})`,
    }));

  return (
    <Group align="flex-end" gap="sm" wrap="wrap">
      <Text fw={600} w={120}>{CHANNEL_LABEL[channel]}</Text>
      <Select
        label="Target" placeholder="—" clearable searchable w={180}
        data={targets} value={slot.safe}
        onChange={(v) => onChange({ ...slot, safe: v, runId: null })}
      />
      <Select
        label="Stack" placeholder={slot.safe ? "Pick a stack" : "Pick a target first"}
        clearable w={220} data={runOpts} value={slot.runId}
        disabled={!slot.safe || runs.isLoading}
        onChange={(v) => onChange({ ...slot, runId: v })}
      />
      <NumberInput
        label="Weight" w={90} min={0} max={5} step={0.1} decimalScale={2}
        value={slot.weight} onChange={(v) => onChange({ ...slot, weight: Number(v) || 1 })}
      />
    </Group>
  );
}

export function CombineView() {
  const qc = useQueryClient();
  const targetsQ = useQuery({ queryKey: ["targets"], queryFn: api.listTargets });
  const [slots, setSlots] = useState<Record<Channel, Slot>>({
    L: { safe: null, runId: null, weight: 1 },
    R: { safe: null, runId: null, weight: 1 },
    G: { safe: null, runId: null, weight: 1 },
    B: { safe: null, runId: null, weight: 1 },
  });
  const [outputTarget, setOutputTarget] = useState<string | null>(null);
  const [outputName, setOutputName] = useState("lrgb");

  const targetOpts = (targetsQ.data ?? []).map((t) => ({ value: t.safe_name, label: t.name }));

  const assigned = CHANNELS.filter((c) => slots[c].safe && slots[c].runId);
  const hasColor = assigned.some((c) => c === "R" || c === "G" || c === "B");
  const canSubmit = Boolean(outputTarget) && (hasColor || assigned.includes("L"));

  const combine = useMutation({
    mutationFn: () => {
      const items = assigned.map((c) => ({
        safe: slots[c].safe as string,
        run_id: Number(slots[c].runId),
        channel: c,
      }));
      const weights: Record<string, number> = {};
      assigned.forEach((c) => { weights[c] = slots[c].weight; });
      return api.channelCombine(outputTarget as string, {
        items, output_name: outputName.trim() || "lrgb", weights,
      });
    },
    onSuccess: () => {
      notifications.show({ message: "Combining channels — watch the Jobs page", color: "violet" });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  if (targetsQ.isLoading) return <Loader />;

  return (
    <Stack maw={760}>
      <Title order={2}>Channel combine</Title>
      <Alert icon={<IconInfoCircle size={16} />} color="violet" variant="light">
        Combine separate mono stacks into one colour image. Assign a stack to each of
        R/G/B for an <b>RGB</b> composite; add a <b>Luminance</b> stack for <b>LRGB</b>
        (colour from RGB, detail from L). All stacks must share the same canvas — stack
        each filter against a common reference. Stack mono subs with the “Mono / filtered
        subs” option first.
      </Alert>

      <Paper withBorder p="lg">
        <Stack>
          {CHANNELS.map((c) => (
            <ChannelRow key={c} channel={c} slot={slots[c]} targets={targetOpts}
              onChange={(s) => setSlots((p) => ({ ...p, [c]: s }))} />
          ))}
        </Stack>
      </Paper>

      <Paper withBorder p="lg">
        <Group align="flex-end" gap="sm" wrap="wrap">
          <Select label="Save into target" placeholder="Pick a target" searchable w={220}
            data={targetOpts} value={outputTarget} onChange={setOutputTarget} />
          <TextInput label="Output name" style={{ flex: 1, minWidth: 160 }}
            value={outputName} onChange={(e) => setOutputName(e.currentTarget.value)} />
          <Button leftSection={<IconPalette size={16} />} loading={combine.isPending}
            disabled={!canSubmit} onClick={() => combine.mutate()}>
            Combine
          </Button>
        </Group>
        {!canSubmit ? (
          <Text size="xs" c="dimmed" mt="xs">
            Assign at least one R/G/B (or an L) stack and choose where to save the result.
          </Text>
        ) : null}
      </Paper>
    </Stack>
  );
}
