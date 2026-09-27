import { Button, Group, Paper, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

type Preview = Awaited<ReturnType<typeof api.refinishPreview>>;

/** The sentence under the heading, or null when there is nothing to give back.
 *  Pure so it is tested without rendering. */
export function refinishSummary(p: Preview | undefined): { lead: string; byHand: string | null } | null {
  const n = p?.refinish.length ?? 0;
  if (!p || n === 0) return null;
  const pics = n === 1 ? "1 target is" : `${n} targets are`;
  const byHandN = p.left_alone.by_hand?.length ?? 0;
  return {
    lead:
      `${pics} showing a flat, unedited stack where the app had earlier finished the `
      + "picture with Auto — usually because \"Reprocess everything\" ran with auto-edit off. "
      + "This re-applies Auto to the picture now shown. Earlier results stay in History, "
      + "and every edit can be undone in the editor.",
    byHand: byHandN === 0 ? null
      : `${byHandN === 1 ? "1 other flat target" : `${byHandN} other flat targets`} had a picture `
        + "you finished yourself. Those are left alone — open them to redo your edit.",
  };
}

/** Settings → Maintenance: give back the pictures a restack flattened (observer
 *  #903). Self-hides when there are none, so it disappears once the repair ran. */
export function RefinishPicturesCard() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const preview = useQuery({ queryKey: ["refinish-preview"], queryFn: api.refinishPreview, staleTime: 60_000 });
  const start = useMutation({
    mutationFn: api.startRefinish,
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: ["refinish-preview"] });
      notifications.show({
        color: "teal",
        message: res.already_running
          ? "Already re-finishing pictures — watch it on the Jobs page."
          : "Re-finishing pictures — watch progress on the Jobs page.",
      });
      navigate("/jobs");
    },
    onError: (e: Error) =>
      notifications.show({ color: "red", title: "Couldn't start", message: e.message }),
  });
  const summary = refinishSummary(preview.data);
  if (!summary) return null;
  const n = preview.data!.refinish.length;
  const onClick = () => {
    if (window.confirm(
      `Re-apply the Auto look to ${n} ${n === 1 ? "picture" : "pictures"}?\n\n`
      + "Only targets whose earlier picture the app finished with Auto are touched. "
      + "Anything you edited by hand is left exactly as it is.",
    )) start.mutate();
  };
  return (
    <Paper withBorder p="lg">
      <Stack gap="xs">
        <Text fw={600}>Give back pictures a restack flattened</Text>
        <Text size="sm">{summary.lead}</Text>
        {summary.byHand && <Text size="sm" c="dimmed">{summary.byHand}</Text>}
        <Group>
          <Button onClick={onClick} loading={start.isPending}>
            Re-finish {n} {n === 1 ? "picture" : "pictures"}
          </Button>
        </Group>
      </Stack>
    </Paper>
  );
}
