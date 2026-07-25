import { Button, Group, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconPlayerPlay, IconSparkles, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

/**
 * "Try it with a sample image" — the empty-app onboarding card.
 *
 * A brand-new owner who installs AstroStack before their first clear night has
 * nothing to do: every screen is blank until real Seestar frames arrive. This
 * card offers a one-tap generated demo target so they can walk the real journey
 * — QC → stack → edit → export — on real-looking data before they've captured a
 * thing, and remove it in one click when they're done.
 *
 * Self-hiding by design: the "try it" offer shows only while the library is
 * empty (so it never nags an established user), and once the sample is loaded it
 * switches to a small "sample is ready / remove it" card that stays reachable
 * even after real data arrives — so the demo is always easy to clean up.
 */
export function SampleImageCard() {
  const qc = useQueryClient();
  const navigate = useNavigate();

  const sample = useQuery({ queryKey: ["sample"], queryFn: api.getSampleStatus });
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.getStats });

  const load = useMutation({
    mutationFn: api.loadSample,
    onSuccess: (status) => {
      qc.invalidateQueries({ queryKey: ["sample"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["targets"] });
      notifications.show({
        message: "Sample loaded. This is what you'll see with your own frames — "
          + "run QC, stack it, then edit and export.",
        color: "teal",
      });
      if (status.safe) navigate(`/targets/${status.safe}`);
    },
    onError: (err) => {
      notifications.show({
        message: `Couldn't load the sample: ${err instanceof Error ? err.message : String(err)}`,
        color: "red",
      });
    },
  });

  // One-tap "see the payoff": stack the demo with sane defaults and drop the
  // newcomer on its Target page to watch the finished picture appear — so they
  // don't have to hunt for the Stack control to see why stacking matters.
  const stack = useMutation({
    mutationFn: (safe: string) => api.triggerStack(safe, {}),
    onSuccess: (_res, safe) => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      notifications.show({
        message: "Stacking the sample — watch it come together on the target page.",
        color: "teal",
      });
      navigate(`/targets/${safe}`);
    },
    onError: (err) => {
      notifications.show({
        message: `Couldn't stack the sample: ${err instanceof Error ? err.message : String(err)}`,
        color: "red",
      });
    },
  });

  const remove = useMutation({
    mutationFn: api.removeSample,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sample"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["targets"] });
      notifications.show({ message: "Sample removed.", color: "teal" });
    },
    onError: (err) => {
      notifications.show({
        message: `Couldn't remove the sample: ${err instanceof Error ? err.message : String(err)}`,
        color: "red",
      });
    },
  });

  if (!sample.data) return null;
  const loaded = sample.data.loaded;
  const libraryEmpty = (stats.data?.n_targets ?? 0) === 0;

  // Nothing to show once the user has real data and no demo lingering.
  if (!loaded && !libraryEmpty) return null;

  if (loaded) {
    return (
      <Paper withBorder radius="md" p="md">
        <Group justify="space-between" wrap="nowrap" gap="md">
          <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
            <ThemeIcon variant="light" color="violet" size="lg" radius="md">
              <IconSparkles size={20} />
            </ThemeIcon>
            <Stack gap={2} style={{ minWidth: 0 }}>
              <Text fw={600} size="sm">Your sample target is ready</Text>
              <Text size="xs" c="dimmed">
                Open it to try QC, stacking, editing and exporting — just like your
                own frames. Remove it any time; nothing else is touched.
              </Text>
            </Stack>
          </Group>
          <Group gap="xs" wrap="nowrap" style={{ flexShrink: 0 }}>
            <Button size="xs" color="violet"
              leftSection={<IconPlayerPlay size={14} />}
              loading={stack.isPending}
              onClick={() => sample.data?.safe && stack.mutate(sample.data.safe)}>
              Stack it
            </Button>
            <Button size="xs" variant="light" color="violet"
              onClick={() => sample.data?.safe && navigate(`/targets/${sample.data.safe}`)}>
              Open sample
            </Button>
            <Button size="xs" variant="subtle" color="gray"
              leftSection={<IconTrash size={14} />}
              loading={remove.isPending}
              onClick={() => remove.mutate()}>
              Remove
            </Button>
          </Group>
        </Group>
      </Paper>
    );
  }

  return (
    <Paper withBorder radius="md" p="md">
      <Group justify="space-between" wrap="nowrap" gap="md">
        <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
          <ThemeIcon variant="light" color="violet" size="lg" radius="md">
            <IconSparkles size={20} />
          </ThemeIcon>
          <Stack gap={2} style={{ minWidth: 0 }}>
            <Text fw={600} size="sm">New here? Try it with a sample image</Text>
            <Text size="xs" c="dimmed">
              No frames yet? Load a small demo target and walk the whole journey —
              quality-check, stack, edit and export — before your first clear night.
            </Text>
          </Stack>
        </Group>
        <Button size="sm" color="violet" style={{ flexShrink: 0 }}
          leftSection={<IconSparkles size={16} />}
          loading={load.isPending}
          onClick={() => load.mutate()}>
          Try it
        </Button>
      </Group>
    </Paper>
  );
}
