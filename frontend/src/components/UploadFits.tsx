import {
  Alert, Box, Button, Card, FileButton, Group, Stack, Text, TextInput,
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

/** Minimal shape of the (non-standard but universally-supported) HTML5
 *  FileSystem entry a drag-drop hands us via ``webkitGetAsEntry``. Kept as a
 *  local structural type so we can traverse — and unit-test — folder drops
 *  without pulling in a dependency. */
export interface FsEntry {
  isFile: boolean;
  isDirectory: boolean;
  // The entry's path within the dropped item (e.g. ``/M31/night1/Light_001.fit``);
  // this is what distinguishes two same-named subs in different session folders.
  fullPath?: string;
  file?: (onOk: (f: File) => void, onErr?: (e: unknown) => void) => void;
  createReader?: () => {
    readEntries: (onOk: (entries: FsEntry[]) => void, onErr?: (e: unknown) => void) => void;
  };
}

/** Recursively collect every file under a dropped FileSystem entry. A dropped
 *  *folder* is walked depth-first; a dropped *file* yields itself. Errors on any
 *  single entry are swallowed (that branch just contributes nothing) so one
 *  unreadable file never sinks a whole-folder drop.
 *
 *  A file's **relative path within the dropped folder** (its ``fullPath``) is
 *  preserved as the File's name, so two different subs that share a basename
 *  across session subfolders (Seestar restarts frame numbering each session) stay
 *  distinct on upload instead of one silently overwriting the other. The server
 *  flattens/sanitises the path back into one safe filename. */
export async function readEntryFiles(entry: FsEntry): Promise<File[]> {
  if (entry.isFile && entry.file) {
    const getFile = entry.file.bind(entry);
    const rel = (entry.fullPath || "").replace(/^\/+/, "");
    return new Promise<File[]>((resolve) => {
      getFile(
        (f) => resolve([
          rel && rel !== f.name
            ? new File([f], rel, { type: f.type, lastModified: f.lastModified })
            : f,
        ]),
        () => resolve([]),
      );
    });
  }
  if (entry.isDirectory && entry.createReader) {
    const reader = entry.createReader();
    const children: FsEntry[] = [];
    // The Directory reader returns entries in batches; it must be pumped until
    // it hands back an empty batch (that's how the API signals "done").
    await new Promise<void>((resolve) => {
      const pump = () => {
        reader.readEntries((batch) => {
          if (!batch.length) { resolve(); return; }
          children.push(...batch);
          pump();
        }, () => resolve());
      };
      pump();
    });
    const nested = await Promise.all(children.map(readEntryFiles));
    return nested.flat();
  }
  return [];
}

/** Flatten a drag-drop's payload into a plain File list — walking any dropped
 *  folders (so "drag a whole Seestar target folder onto the Library" works) and
 *  falling back to ``dataTransfer.files`` when the FileSystem-entry API is
 *  unavailable. FITS filtering happens downstream in ``onPick``. */
export async function collectDroppedFiles(dt: DataTransfer): Promise<File[]> {
  const items = dt.items;
  const entries: FsEntry[] = [];
  if (items && items.length && typeof (items[0] as unknown as {
    webkitGetAsEntry?: unknown;
  }).webkitGetAsEntry === "function") {
    for (let i = 0; i < items.length; i++) {
      const getEntry = (items[i] as unknown as {
        webkitGetAsEntry?: () => FsEntry | null;
      }).webkitGetAsEntry;
      const entry = getEntry ? getEntry.call(items[i]) : null;
      if (entry) entries.push(entry);
    }
  }
  if (entries.length) {
    const nested = await Promise.all(entries.map(readEntryFiles));
    return nested.flat();
  }
  return Array.from(dt.files ?? []);
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
  const [dragActive, setDragActive] = useState(false);

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

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    if (upload.isPending) return;
    void collectDroppedFiles(e.dataTransfer).then((dropped) => {
      if (dropped.length) onPick(dropped);
    });
  };

  const body = (
    <Box
      onDragOver={(e) => { e.preventDefault(); if (!dragActive) setDragActive(true); }}
      onDragLeave={(e) => { e.preventDefault(); setDragActive(false); }}
      onDrop={onDrop}
      p="xs"
      style={(theme) => ({
        borderRadius: theme.radius.sm,
        border: `1px dashed ${dragActive ? theme.colors.blue[5] : theme.colors.gray[4]}`,
        background: dragActive ? theme.colors.blue[0] : undefined,
        transition: "background 120ms, border-color 120ms",
      })}
    >
    <Stack gap="xs">
      <Text size="xs" c={dragActive ? "blue" : "dimmed"}>
        {dragActive
          ? "Drop your FITS files or folder here…"
          : "Drag your Seestar FITS files (or a whole target folder) here, or choose them below."}
      </Text>
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
    </Box>
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
