import { Alert, Badge, Button, Group, Stack, Text, Tooltip } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconFlask, IconSparkles } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, type IncomingCalibrationFolder } from "../api/client";
import {
  folderSummaryLine, offerHeadline, whatItDoes, whyWeThinkSo,
} from "./incomingCalibration";

const KIND_COLORS: Record<string, string> = {
  dark: "indigo", flat: "teal", bias: "grape",
};

/** "You already have darks" — the calibration frames sitting in `incoming/`,
 *  with a one-click build.
 *
 *  The Calibration page otherwise asks a beginner to know what a master dark is,
 *  find the folder on their NAS, and type its path into a form. The frames are
 *  usually already there, and — crucially — they say so themselves: the server
 *  only lists a folder whose own `IMAGETYP` cards declare a calibration kind, so
 *  nothing here is guessed from a folder's name. On a camera that writes no such
 *  card the list is empty and this card renders nothing at all.
 *
 *  Only ever *offers*: no master is built until the button is pressed, and
 *  building one still doesn't apply it to anything (calibration stays opt-in).
 *  Folders already covered by a master are shown greyed with "you already have
 *  this one" rather than inviting a duplicate. */
export function IncomingCalibrationCard({ onBuilt }: { onBuilt?: () => void }) {
  const found = useQuery({
    queryKey: ["calibration-incoming"],
    queryFn: api.calibrationIncoming,
    // The server caches the folder walk; this is a cheap re-read of it.
    refetchInterval: 120_000,
  });

  const build = useMutation({
    mutationFn: (folderId: string) => api.buildMasterFromIncoming(folderId),
    onSuccess: () => {
      notifications.show({
        message: "Building master — watch the Jobs page", color: "violet",
      });
      onBuilt?.();
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const folders = found.data?.folders ?? [];
  const headline = offerHeadline(folders);
  // Self-hiding: nothing found, or everything found is already built.
  if (!headline) return null;

  return (
    <Alert icon={<IconSparkles size={16} />} color="violet" variant="light"
      title={headline}>
      <Stack gap="xs">
        <Text size="sm">
          These are sitting in your incoming folder — AstroStack can turn them
          into a master for you. Nothing is applied to your pictures until you
          pick it on the Stack form.
        </Text>
        {folders.map((f) => (
          <FolderRow key={f.id} folder={f}
            pending={build.isPending && build.variables === f.id}
            onBuild={() => build.mutate(f.id)} />
        ))}
      </Stack>
    </Alert>
  );
}

function FolderRow({ folder, pending, onBuild }: {
  folder: IncomingCalibrationFolder;
  pending: boolean;
  onBuild: () => void;
}) {
  const covered = !!folder.have_master;
  return (
    <Group gap="sm" wrap="wrap" align="center" opacity={covered ? 0.6 : 1}>
      <Badge color={KIND_COLORS[folder.kind] ?? "gray"} variant="light">
        {folder.kind}
      </Badge>
      <div style={{ flex: 1, minWidth: 200 }}>
        <Text size="sm" fw={500}>{folder.rel_path}</Text>
        <Text size="xs" c="dimmed">
          {folderSummaryLine(folder)} — {whyWeThinkSo(folder)}
        </Text>
        {covered ? (
          <Text size="xs" c="dimmed">
            You already have this one: <b>{folder.have_master?.name}</b>
          </Text>
        ) : (
          <Text size="xs" c="dimmed">{whatItDoes(folder.kind)}</Text>
        )}
      </div>
      {covered ? null : (
        <Tooltip label={`Build "${folder.suggested_name}"`}>
          <Button size="xs" variant="light" loading={pending}
            leftSection={<IconFlask size={14} />} onClick={onBuild}>
            Build master {folder.kind}
          </Button>
        </Tooltip>
      )}
    </Group>
  );
}
