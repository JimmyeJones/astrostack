import { Alert, Button, Group, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconSparkles } from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { AutoDrizzleCost } from "../api/client";
import { AUTO_DRIZZLE_WHY, autoDrizzleCostLine } from "../autoDrizzleNote";

/**
 * "Drizzling ×1.5 — about 14 h (a plain stack would take about 2 h)", on a
 * running job, with the two things to do about it.
 *
 * An unattended run can now turn drizzle on by itself when the subs can pay for
 * it (v0.494.0), and that costs about ×7 a plain sub (v0.494.2) — on the owner's
 * deepest targets, a night's stack becomes most of a day's. Asked whether a
 * hands-off run should refuse a long one he said no: **tell me the estimate
 * before it starts and let it run** (sign-off item 19, 2026-10-13). So there is
 * no threshold here and no new global setting; there is a sentence, and two
 * one-click answers to it.
 *
 * `onCancel` is the run in front of him — passed in, because each surface
 * already owns how it cancels a job. The second action is the standing one:
 * `drizzle: false` in this target's own saved defaults, which the unattended
 * chain reads as a choice made and never overrules. Both are reversible (tick
 * Drizzle back on in the target's Stack form), neither touches anything else the
 * target has saved, and nothing here can stop the run on its own.
 *
 * Renders nothing unless the job actually chose to drizzle, so it is invisible
 * on every other job and on an older backend that sends no `auto_drizzle`.
 */
export function AutoDrizzleNote(
  { cost, target, onCancel }: {
    cost: AutoDrizzleCost | null | undefined;
    /** The target's safe name — the opt-out is per target. */
    target: string | null | undefined;
    /** Stop this run. Omitted where the surface has its own cancel beside it. */
    onCancel?: () => void;
  },
) {
  const qc = useQueryClient();
  const standDown = useMutation({
    mutationFn: () => api.autoDrizzleOff(target as string),
    onSuccess: () => {
      notifications.show({
        message: "Saved — hands-off stacks of this target will stay plain from now on. "
          + "Tick Drizzle back on in its Stack form to undo.",
        color: "violet",
      });
      qc.invalidateQueries({ queryKey: ["stack-defaults", target] });
      qc.invalidateQueries({ queryKey: ["stack-defaults-pinned", target] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const line = autoDrizzleCostLine(cost);
  if (!line) return null;
  return (
    <Alert color="violet" variant="light" p="xs" mt="xs"
      icon={<IconSparkles size={18} />}
      data-testid="auto-drizzle-note">
      <Text size="sm" fw={500}>{line}</Text>
      <Text size="xs" c="dimmed" mt={2}>{AUTO_DRIZZLE_WHY}</Text>
      <Group gap="xs" mt={6}>
        {onCancel ? (
          <Button size="xs" variant="subtle" color="red" onClick={onCancel}>
            Stop this stack
          </Button>
        ) : null}
        {target ? (
          <Button size="xs" variant="subtle"
            loading={standDown.isPending}
            disabled={standDown.isSuccess}
            onClick={() => standDown.mutate()}>
            {standDown.isSuccess
              ? "Won't auto-drizzle this target"
              : "Don't auto-drizzle this target"}
          </Button>
        ) : null}
      </Group>
    </Alert>
  );
}
