import { Button, Divider, Group, Paper, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

type Preview = Awaited<ReturnType<typeof api.refinishPreview>>;
type UneditedPreview = Awaited<ReturnType<typeof api.finishUneditedPreview>>;

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

/** "Finish my unedited pictures": the sentences, or null when every picture
 *  has been edited (or there are none). Pure so it is tested without rendering. */
export function finishUneditedSummary(p: UneditedPreview | undefined): { lead: string; leftAlone: string | null } | null {
  const n = p?.finish.length ?? 0;
  if (!p || n === 0) return null;
  const pics = n === 1 ? "1 picture has" : `${n} pictures have`;
  const parts: string[] = [];
  const count = (k: string) => p.left_alone[k]?.length ?? 0;
  if (count("has_edit")) parts.push(`${count("has_edit")} with an edit you saved`);
  if (count("cover_pinned")) parts.push(`${count("cover_pinned")} you pinned as the cover`);
  if (count("auto_edit_off")) parts.push(`${count("auto_edit_off")} with auto-editing turned off`);
  return {
    lead:
      `${pics} never been edited, so they show the plain stack — usually a little flat, with a `
      + "ragged, speckled edge where only a few subs overlap. This applies the editor's one-click "
      + "Auto to each of them. Your stacked files are not changed, earlier results stay in "
      + "History, and Reset in the editor puts any picture back.",
    leftAlone: parts.length === 0 ? null : `Left alone: ${parts.join(", ")}.`,
  };
}

/** The repair's preview minus the targets "Finish my unedited pictures" would
 *  finish anyway. Pure, tested. */
export function withoutCovered(p: Preview | undefined, u: UneditedPreview | undefined): Preview | undefined {
  if (!p || !u) return p;
  const covered = new Set(u.finish.map((t) => t.safe_name));
  return { ...p, refinish: p.refinish.filter((t) => !covered.has(t.safe_name)) };
}

/** Settings → Maintenance: the two one-click "finish these pictures" repairs —
 *  give back pictures a restack flattened (observer #903), and finish every
 *  picture nobody ever edited (owner, 2026-10-28). Each half self-hides when it
 *  has nothing to do, and the card with them. */
export function RefinishPicturesCard() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const preview = useQuery({ queryKey: ["refinish-preview"], queryFn: api.refinishPreview, staleTime: 60_000 });
  const unedited = useQuery({
    queryKey: ["finish-unedited-preview"], queryFn: api.finishUneditedPreview, staleTime: 60_000,
  });
  const started = (busy: string, go: string) => (res: { already_running: boolean }) => {
    void qc.invalidateQueries({ queryKey: ["refinish-preview"] });
    void qc.invalidateQueries({ queryKey: ["finish-unedited-preview"] });
    notifications.show({
      color: "teal",
      message: res.already_running
        ? `Already ${busy} — watch it on the Jobs page.`
        : `${go} — watch progress on the Jobs page.`,
    });
    navigate("/jobs");
  };
  const failed = (e: Error) =>
    notifications.show({ color: "red", title: "Couldn't start", message: e.message });
  const start = useMutation({
    mutationFn: api.startRefinish,
    onSuccess: started("re-finishing pictures", "Re-finishing pictures"),
    onError: failed,
  });
  const startUnedited = useMutation({
    mutationFn: api.startFinishUnedited,
    onSuccess: started("finishing pictures", "Finishing your pictures"),
    onError: failed,
  });
  const uneditedSummary = finishUneditedSummary(unedited.data);
  // A flattened picture is also an unedited one, so "Finish my unedited
  // pictures" already covers it: the repair is offered only for what it alone
  // would reach, never as a second button for the same targets.
  const summary = refinishSummary(withoutCovered(preview.data, unedited.data));
  if (!summary && !uneditedSummary) return null;
  const n = withoutCovered(preview.data, unedited.data)?.refinish.length ?? 0;
  const m = unedited.data?.finish.length ?? 0;
  const onClick = () => {
    if (window.confirm(
      `Re-apply the Auto look to ${n} ${n === 1 ? "picture" : "pictures"}?\n\n`
      + "Only targets whose earlier picture the app finished with Auto are touched. "
      + "Anything you edited by hand is left exactly as it is.",
    )) start.mutate();
  };
  const onClickUnedited = () => {
    if (window.confirm(
      `Finish ${m} unedited ${m === 1 ? "picture" : "pictures"} with Auto?\n\n`
      + "Only pictures with no saved edit are touched. Anything you edited, and any cover "
      + "you pinned, is left exactly as it is.",
    )) startUnedited.mutate();
  };
  return (
    <Paper withBorder p="lg">
      <Stack gap="xs">
        {summary && (
          <>
            <Text fw={600}>Give back pictures a restack flattened</Text>
            <Text size="sm">{summary.lead}</Text>
            {summary.byHand && <Text size="sm" c="dimmed">{summary.byHand}</Text>}
            <Group>
              <Button onClick={onClick} loading={start.isPending}>
                Re-finish {n} {n === 1 ? "picture" : "pictures"}
              </Button>
            </Group>
          </>
        )}
        {summary && uneditedSummary && <Divider my="xs" />}
        {uneditedSummary && (
          <>
            <Text fw={600}>Finish my unedited pictures</Text>
            <Text size="sm">{uneditedSummary.lead}</Text>
            {uneditedSummary.leftAlone && <Text size="sm" c="dimmed">{uneditedSummary.leftAlone}</Text>}
            <Group>
              <Button onClick={onClickUnedited} loading={startUnedited.isPending}>
                Finish {m} {m === 1 ? "picture" : "pictures"}
              </Button>
            </Group>
          </>
        )}
      </Stack>
    </Paper>
  );
}
