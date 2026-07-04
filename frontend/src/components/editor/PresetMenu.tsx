import { ActionIcon, Button, Group, Menu, Modal, TextInput } from "@mantine/core";
import { IconBookmark, IconChevronDown, IconDeviceFloppy, IconStar, IconStarOff, IconTrash }
  from "@tabler/icons-react";
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
  /** Apply a preset's ops. `source` lets the caller treat built-in presets
   * (which carry generic default sizes) differently from user presets (which the
   * user tuned deliberately) — e.g. seed built-in sizes from the target's data. */
  onApply: (ops: OpInstance[], source: "builtin" | "user") => void;
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

  // The user's library-wide default recipe ("my house style"): setting it lets the
  // editor offer it as a one-click seed on any run with no saved edit. Off until set.
  const defaultRecipe = useQuery({
    queryKey: ["default-recipe"], queryFn: api.getDefaultRecipe });
  const setDefault = useMutation({
    mutationFn: () => api.putDefaultRecipe(currentOps),
    onSuccess: (d) => {
      notifications.show({
        message: `Saved as your default edit (${d.count} step${d.count === 1 ? "" : "s"}) `
          + "— offered on new runs with no edit yet", color: "teal" });
      qc.invalidateQueries({ queryKey: ["default-recipe"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const clearDefault = useMutation({
    mutationFn: () => api.deleteDefaultRecipe(),
    onSuccess: () => {
      notifications.show({ message: "Cleared your default edit", color: "gray" });
      qc.invalidateQueries({ queryKey: ["default-recipe"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  const hasDefault = (defaultRecipe.data?.count ?? 0) > 0;

  const builtin = presets.data?.builtin ?? [];
  const user = presets.data?.user ?? [];

  // Applying a preset replaces the whole pipeline — confirm if that throws away work.
  const applyPreset = (p: Preset, source: "builtin" | "user") => {
    if (currentOps.length && !window.confirm(
      `Apply "${p.label}"? This replaces your current ${currentOps.length}-operation pipeline.`)) {
      return;
    }
    onApply(toOps(p), source);
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
            <Menu.Item key={p.id} onClick={() => applyPreset(p, "builtin")}>{p.label}</Menu.Item>
          ))}
          {user.length ? <Menu.Label>My presets</Menu.Label> : null}
          {user.map((p) => (
            <Menu.Item key={p.id} onClick={() => applyPreset(p, "user")}
              rightSection={
                <ActionIcon size="xs" variant="subtle" color="red" component="div"
                  aria-label={`Delete preset ${p.label}`}
                  onClick={(e) => { e.stopPropagation(); del.mutate(p.id); }}>
                  <IconTrash size={12} />
                </ActionIcon>
              }>{p.label}</Menu.Item>
          ))}
          <Menu.Divider />
          <Menu.Item leftSection={<IconDeviceFloppy size={14} />} onClick={saveCtl.open}>
            Save current as preset…
          </Menu.Item>
          <Menu.Item leftSection={<IconStar size={14} />}
            disabled={!currentOps.length || setDefault.isPending}
            onClick={() => setDefault.mutate()}>
            Set current as my default
          </Menu.Item>
          {hasDefault ? (
            <Menu.Item leftSection={<IconStarOff size={14} />} color="red"
              disabled={clearDefault.isPending}
              onClick={() => clearDefault.mutate()}>
              Clear my default edit
            </Menu.Item>
          ) : null}
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
