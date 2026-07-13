import {
  Alert, Button, Card, FileButton, Group, Stack, Text, TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconFileUpload, IconUpload } from "@tabler/icons-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type UploadResult } from "../api/client";

// Match the server's accepted FITS suffixes (seestack.io.ingest.FITS_SUFFIXES).
const FITS_ACCEPT = ".fit,.fits,.fts";

/** True when the filename is one the server will accept — so we don't bother
 *  uploading a stray .txt/.jpg the user grabbed alongside their subs. */
export function isFitsFilename(name: string): boolean {
  return /\.(fit|fits|fts)$/i.test(name);
}

/** One plain-language line summarising an upload's outcome. */
export function uploadSummary(r: UploadResult): string {
  const parts: string[] = [];
  if (r.saved.length) parts.push(`Uploaded ${r.saved.length} ${r.saved.length === 1 ? "sub" : "subs"}`);
  if (r.skipped.length) parts.push(`${r.skipped.length} already there`);
  if (r.rejected.length) parts.push(`${r.rejected.length} skipped`);
  if (!parts.length) return "Nothing to upload.";
  const where = r.target ? ` into “${r.target}”` : "";
  return parts.join(" · ") + where + ".";
}

/**
 * Drag-a-folder / multi-select FITS upload. Streams the chosen subs to the
 * watched ``incoming/`` folder (optionally under a named target) and kicks the
 * existing scan → QC → solve pipeline — the beginner on-ramp that removes the
 * "mount the NAS share" step. Non-FITS files are filtered client-side and any
 * the server rejects are reported back with a reason.
 */
export function UploadFits({ compact = false }: { compact?: boolean }) {
  const qc = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [target, setTarget] = useState("");
  const [result, setResult] = useState<UploadResult | null>(null);

  const upload = useMutation({
    mutationFn: () => api.uploadFits(files, target),
    onSuccess: (r) => {
      setResult(r);
      setFiles([]);
      notifications.show({ message: uploadSummary(r), color: r.saved.length ? "teal" : "yellow" });
      // New subs → new/updated targets + a running scan job.
      qc.invalidateQueries({ queryKey: ["targets"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (e: Error) => notifications.show({ message: e.message, color: "red" }),
  });

  const onPick = (picked: File[] | null) => {
    if (!picked) return;
    const fits = picked.filter((f) => isFitsFilename(f.name));
    setResult(null);
    setFiles(fits);
    const dropped = picked.length - fits.length;
    if (dropped > 0) {
      notifications.show({
        message: `Ignored ${dropped} non-FITS ${dropped === 1 ? "file" : "files"}.`,
        color: "yellow",
      });
    }
  };

  const body = (
    <Stack gap="xs">
      <Group gap="xs" wrap="wrap" align="flex-end">
        <FileButton onChange={onPick} accept={FITS_ACCEPT} multiple>
          {(props) => (
            <Button {...props} variant="light" leftSection={<IconFileUpload size={16} />}>
              Choose FITS files…
            </Button>
          )}
        </FileButton>
        <TextInput
          label="Target folder (optional)"
          placeholder="e.g. M31"
          value={target}
          onChange={(e) => setTarget(e.currentTarget.value)}
          w={{ base: "100%", xs: 180 }}
          size="sm"
        />
        <Button
          onClick={() => upload.mutate()}
          disabled={files.length === 0}
          loading={upload.isPending}
          leftSection={<IconUpload size={16} />}
        >
          Upload {files.length ? `${files.length} ${files.length === 1 ? "file" : "files"}` : ""}
        </Button>
      </Group>

      {files.length > 0 && !upload.isPending ? (
        <Text size="xs" c="dimmed">
          {files.length} FITS {files.length === 1 ? "file" : "files"} ready
          {target.trim() ? ` — will go into “${target.trim()}”` : " — will go to Unsorted"}.
        </Text>
      ) : null}

      {result ? (
        <Alert
          color={result.saved.length ? "teal" : "yellow"}
          variant="light"
          title={uploadSummary(result)}
        >
          <Stack gap={4}>
            {result.saved.length ? (
              <Text size="sm">
                Scanning them now — QC &amp; plate-solving run automatically.{" "}
                <Text component={Link} to="/jobs" c="blue" span>Watch progress</Text>.
              </Text>
            ) : null}
            {result.rejected.length ? (
              <Text size="xs" c="dimmed">
                Skipped: {result.rejected.slice(0, 5).map((f) => `${f.name} (${f.reason})`).join(", ")}
                {result.rejected.length > 5 ? ` +${result.rejected.length - 5} more` : ""}
              </Text>
            ) : null}
          </Stack>
        </Alert>
      ) : null}
    </Stack>
  );

  if (compact) return body;

  return (
    <Card withBorder padding="md">
      <Stack gap="xs">
        <Group gap="xs">
          <IconFileUpload size={18} />
          <Text fw={600}>Upload subs from your computer</Text>
        </Group>
        <Text size="sm" c="dimmed">
          No NAS share needed — pick your Seestar FITS files (or a whole folder) and they’ll
          drop straight into the pipeline.
        </Text>
        {body}
      </Stack>
    </Card>
  );
}
