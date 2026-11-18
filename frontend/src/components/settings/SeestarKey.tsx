import { Badge, Button, FileButton, Group, Stack, Text } from "@mantine/core";
import { IconKey } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import { seestarKeyError, seestarKeyLine } from "./seestarKey";

/**
 * "Add your Seestar key file" — inside the existing Telescope (Seestar) group
 * on Settings → This device (⭐ Seestar-page upgrade, slice 1).
 *
 * The file is read in the browser and sent once as JSON; the server checks it
 * is a usable RSA key, stores it 0600 and from then on only ever answers
 * "installed / not installed". Choosing a file saves it straight away (it is not
 * part of the page's Save button, which writes settings, not files).
 */
/** The chosen file's text. `FileReader` rather than `File.text()`, which some
 * older browsers (and jsdom) lack. */
function readText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result ?? ""));
    r.onerror = () => reject(new Error("AstroStack couldn't read that file."));
    r.readAsText(file);
  });
}

export function SeestarKeyBox() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["seestar-key"], queryFn: api.getSeestarKey });
  const [error, setError] = useState<string | null>(null);
  const done = (s: unknown) => {
    setError(null);
    qc.setQueryData(["seestar-key"], s);
  };
  const upload = useMutation({
    mutationFn: async (file: File) => api.uploadSeestarKey(await readText(file)),
    onSuccess: done,
    onError: (e) => setError(seestarKeyError(e)),
  });
  const remove = useMutation({
    mutationFn: api.removeSeestarKey,
    onSuccess: done,
    onError: (e) => setError(seestarKeyError(e)),
  });
  const installed = Boolean(status.data?.installed);
  const busy = upload.isPending || remove.isPending;

  return (
    <Stack gap={6} data-testid="seestar-key">
      <Group gap={6}>
        <IconKey size={16} />
        <Text fw={500} size="sm">Seestar key file</Text>
        <Badge variant="light" color={installed ? "teal" : "gray"}>
          {installed ? "installed" : "not installed"}
        </Badge>
      </Group>
      <Text size="sm" c="dimmed">{seestarKeyLine(status.data)}</Text>
      <Group gap="xs">
        <FileButton
          onChange={(f) => { if (f) upload.mutate(f); }}
          accept=".pem,.key,.txt,application/x-pem-file,text/plain"
        >
          {(props) => (
            <Button {...props} size="xs" variant="light" loading={upload.isPending}
              disabled={busy && !upload.isPending}>
              {installed ? "Replace the key file" : "Add your Seestar key file"}
            </Button>
          )}
        </FileButton>
        {installed && (
          <Button size="xs" variant="subtle" color="red" loading={remove.isPending}
            disabled={busy && !remove.isPending} onClick={() => remove.mutate()}>
            Remove the key
          </Button>
        )}
      </Group>
      {error && <Text size="sm" c="red" role="alert">{error}</Text>}
    </Stack>
  );
}
