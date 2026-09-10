import { Alert, Button, Text } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { sharePctLabel } from "../editor/mosaicTrim";

/** A keep-fraction as the editor's own share wording ("about 3%", "under 1%"),
 * so this note and the editor's never report one measurement two ways. */
function pct(frac: number | null | undefined): string {
  return sharePctLabel(frac ?? 0);
}

/**
 * "An older version trimmed this picture too far" — on the page where the owner
 * is looking at the picture in question.
 *
 * The D1 border-trim bugs cropped a **mosaic** to its panel overlaps: right on a
 * single field, a sliver on a union canvas. They were fixed across
 * v0.386–v0.399, and every one of those fixes re-derives the *trim*. Nothing
 * re-derives a crop that was already **saved** into a run's recipe — which is
 * what this page's hero image, the Library card and the share sheet all replay.
 * So a target Auto-edited on an affected build still shows the sliver, and until
 * now nothing anywhere said so.
 *
 * This is the middle of three surfaces on one definition
 * (`webapp/stale_crop.py`): the Dashboard counts them library-wide, this names
 * the one you are looking at, and the editor is where the single click that
 * fixes it lives — so the button here is a link into the editor rather than an
 * action, because the fix should be seen against the picture before it is saved.
 *
 * **It never acts.** A small crop may be the owner's own framing, so nothing is
 * rewritten for them; and the stack itself was never touched by any of this,
 * which the copy says out loud because "my picture is wrong" is the frightening
 * reading. Best-effort: a failed fetch or an older backend renders nothing.
 */
export function OverTrimmedTargetNote({
  safe,
  runId,
}: {
  safe: string;
  runId: number;
}) {
  const health = useQuery({
    // The same key the editor uses, so opening one after the other doesn't refetch.
    queryKey: ["crop-health", safe, runId],
    queryFn: () => api.cropHealth(safe, runId).catch(() => null),
    enabled: !!safe && Number.isFinite(runId),
    staleTime: 60_000,
    retry: false,
  });
  const d = health.data;
  if (!d?.stale) return null;

  return (
    <Alert color="orange" variant="light" data-testid="over-trimmed-target-note"
      icon={<IconAlertTriangle size={18} />}
      title="An older version trimmed this picture too far">
      <Text size="sm">
        {`This picture's saved edit is showing ${pct(d.stored_keep_fraction)} of the `
          + `frame, but ${pct(d.suggested_keep_fraction)} of it is well covered. `
          + "An older version of AstroStack cut the ragged mosaic border back too far, "
          + "and the crop it chose was saved with the edit — so it's what you see here, "
          + "on the Library card, and anywhere you share it. Your stack itself was "
          + "never changed, and putting the border back takes one click."}
      </Text>
      <Button component={Link} to={`/targets/${safe}/edit/${runId}`}
        size="compact-xs" variant="light" color="orange" mt="xs">
        Open the editor to fix it
      </Button>
    </Alert>
  );
}
