import { ActionIcon, Button, Group, Menu, Modal, TextInput } from "@mantine/core";
import { IconBookmark, IconChevronDown, IconDeviceFloppy, IconTrash } from "@tabler/icons-react";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type OpInstance, type Preset } from "../../api/client";

function toOps(preset: Preset): OpInstance[] {
  return preset.ops.map((o, i) => ({
    uid: o.uid ?? `${Date.now()}_${i}`,
    id: o.id, enabled: o.enabled ?? true, params: o.params,
  }));
}

export function PresetMenu({ currentOps, onApply }: {
  currentOps: OpInstance[];
  onApply: (ops: OpInstance[]) => void;
}) {
  const qc = useQueryClient();
  const presets = useQuery({ queryKey: ["presets"], queryFn: api.listPresets });
  const [saveOpen, saveCtl] = useDisclosure(false);
  const [name, setName] = useState("");

  const save = useMutation({
    mutationFn: () => api.createPreset(name.trim() || "My preset", currentOps),
    onSuccess: () => {
      notifications.show({ message: "Preset saved", color: "teal" });
      qc.invalidateQueries({ queryKey: ["presets"] });
      saveCtl.close();
      setName("");
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const del = useMutation({
    mutationFn: (id: string) => api.deletePreset(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["presets"] }),
  });

  const builtin = presets.data?.builtin ?? [];
  const user = presets.data?.user ?? [];

  // Applying a preset replaces the whole pipeline — confirm if that throws away work.
  const applyPreset = (p: Preset) => {
    if (currentOps.length && !window.confirm(
      `Apply "${p.label}"? This replaces your current ${currentOps.length}-operation pipeline.`)) {
      return;
    }
    onApply(toOps(p));
  };

  return (
    <>
      <Menu shadow="md" position="bottom-start" width={240}>
        <Menu.Target>
          <Button variant="light" leftSection={<IconBookmark size={16} />}
            rightSection={<IconChevronDown size={14} />}>Presets</Button>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Label>Built-in</Menu.Label>
          {builtin.map((p) => (
            <Menu.Item key={p.id} onClick={() => applyPreset(p)}>{p.label}</Menu.Item>
          ))}
          {user.length ? <Menu.Label>My presets</Menu.Label> : null}
          {user.map((p) => (
            <Menu.Item key={p.id} onClick={() => applyPreset(p)}
              rightSection={
                <ActionIcon size="xs" variant="subtle" color="red" component="div"
                  onClick={(e) => { e.stopPropagation(); del.mutate(p.id); }}>
                  <IconTrash size={12} />
                </ActionIcon>
              }>{p.label}</Menu.Item>
          ))}
          <Menu.Divider />
          <Menu.Item leftSection={<IconDeviceFloppy size={14} />} onClick={saveCtl.open}>
            Save current as preset…
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>

      <Modal opened={saveOpen} onClose={saveCtl.close} title="Save preset" centered>
        <TextInput label="Preset name" value={name} data-autofocus
          onChange={(e) => setName(e.currentTarget.value)} placeholder="e.g. My nebula look" />
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={saveCtl.close}>Cancel</Button>
          <Button loading={save.isPending} onClick={() => save.mutate()}>Save</Button>
        </Group>
      </Modal>
    </>
  );
}
