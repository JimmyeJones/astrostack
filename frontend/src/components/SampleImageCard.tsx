import { Button, Group, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconPlayerPlay, IconSparkles, IconTrash, IconWand } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { StackRun } from "../api/client";

/**
 * The sample's run the "Edit it" button opens: the newest one with a picture,
 * else the newest — the same fallback the Target page uses for *the* picture,
 * so the card and the page it leads to edit the same thing. `null` while the
 * sample has no stack (or the runs list is unknown), which keeps the card on its
 * "Stack it" wording.
 */
export function sampleRunToEdit(runs: StackRun[] | undefined): StackRun | null {
  if (!runs || runs.length === 0) return null;
  return runs.find((r) => r.has_preview) ?? runs[0];
}

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
  // Has the sample been stacked yet? Same key as the Target and History pages,
  // so the answer is shared and a finished stack there updates this card. Once
  // it has, "Stack it" would only make a duplicate of the picture he already
  // has — the next step on the journey this card exists for is the editor.
  const sampleSafe = sample.data?.loaded ? sample.data.safe : null;
  const runs = useQuery({
    queryKey: ["runs", sampleSafe],
    queryFn: () => api.listStackRuns(sampleSafe as string),
    enabled: !!sampleSafe,
  });

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
    const editRun = sampleRunToEdit(runs.data);
    const stacked = editRun !== null;
    return (
      <Paper withBorder radius="md" p="md">
        {/* Wraps, and the wording column is based on 240 px rather than 0 — see
            the note on the identical row below. */}
        <Group justify="space-between" gap="md">
          <Group gap="sm" wrap="nowrap"
                 style={{ flex: "1 1 240px", minWidth: 0 }}>
            <ThemeIcon variant="light" color="violet" size="lg" radius="md"
                       style={{ flexShrink: 0 }}>
              <IconSparkles size={20} />
            </ThemeIcon>
            <Stack gap={2} style={{ minWidth: 0 }}>
              {stacked ? (
                <>
                  <Text fw={600} size="sm">Your sample is stacked — try the editor next</Text>
                  <Text size="xs" c="dimmed">
                    Open its picture in the editor to try Auto-process and export it —
                    just like your own frames. Remove it any time; nothing else is touched.
                  </Text>
                </>
              ) : (
                <>
                  <Text fw={600} size="sm">Your sample target is ready</Text>
                  <Text size="xs" c="dimmed">
                    Open it to try QC, stacking, editing and exporting — just like your
                    own frames. Remove it any time; nothing else is touched.
                  </Text>
                </>
              )}
            </Stack>
          </Group>
          <Group gap="xs" style={{ flexShrink: 0 }}>
            {stacked && (
              <Button size="xs" color="violet"
                leftSection={<IconWand size={14} />}
                onClick={() => sample.data?.safe
                  && navigate(`/targets/${sample.data.safe}/edit/${editRun.id}`)}>
                Edit it
              </Button>
            )}
            {/* Kept once stacked (nothing is removed — AGENTS.md's UI rule), but
                as a quiet "Stack again" so it no longer reads as the next step. */}
            <Button size="xs" color="violet" variant={stacked ? "subtle" : "filled"}
              leftSection={<IconPlayerPlay size={14} />}
              loading={stack.isPending}
              onClick={() => sample.data?.safe && stack.mutate(sample.data.safe)}>
              {stacked ? "Stack again" : "Stack it"}
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
      {/* The row may wrap, and the wording column is based on 240 px rather
          than 0. With `wrap="nowrap"` and a `minWidth: 0` text column beside a
          `flexShrink: 0` button group, a phone-width card squeezed the words
          into a one-word-per-line ribbon ~25 lines tall — flexbox will shrink a
          zero-basis child below its own content rather than wrap the row. A
          real basis makes the buttons drop to their own line instead; on a
          desktop card the row is unchanged. */}
      <Group justify="space-between" gap="md">
        <Group gap="sm" wrap="nowrap" style={{ flex: "1 1 240px", minWidth: 0 }}>
          <ThemeIcon variant="light" color="violet" size="lg" radius="md"
                     style={{ flexShrink: 0 }}>
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
