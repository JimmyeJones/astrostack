import { Button } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

/** "Bring this folder in anyway" for a folder a scan skipped as the device's
 *  own picture.
 *
 *  Its own component so each caller's summary stays hook-free, and so each
 *  folder's button carries its own pending state — one drop can skip several
 *  folders and they are separate decisions.
 *
 *  It scans just that folder, which is the whole point: the alert's other advice
 *  is to rename the folder, and the rename would have to happen inside
 *  `incoming/`, where the owner's only copy of their raws lives. Nothing here
 *  writes there — a scan reads (AGENTS.md §10).
 *
 *  Shared by the Jobs page's per-scan alert and the Library's standing card, so
 *  the two cannot drift into asking for the folder differently. The Library card
 *  is the one that outlives the scan, so the scan's own result — which is what
 *  clears the card — is invalidated here for both.
 */
export function BringFolderInButton(
  { path, name }: { path: string; name: string },
) {
  const qc = useQueryClient();
  const scan = useMutation({
    mutationFn: () => api.scan(path),
    onSuccess: () => {
      notifications.show({
        message: `Bringing "${name}" in — watch the Jobs page for the result`,
        color: "violet",
      });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      // The standing card reads what the last scan remembered, and the scoped
      // scan this just fired is what drops this folder from it — but only once
      // the job finishes, so the card's own poll is what actually clears it.
      // Invalidating here just stops it lagging a poll behind.
      qc.invalidateQueries({ queryKey: ["skipped-folders"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });
  return (
    <Button size="xs" variant="light" color="yellow" mt={6}
      onClick={() => scan.mutate()} loading={scan.isPending}>
      {`Bring "${name}" in anyway`}
    </Button>
  );
}
