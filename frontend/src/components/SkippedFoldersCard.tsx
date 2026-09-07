import { Alert, Button, Group, Stack, Text } from "@mantine/core";
import { IconFolderQuestion } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type SkippedIncomingFolder } from "../api/client";
import { BringFolderInButton } from "./BringFolderInButton";

/** Folders the owner has already decided about, by path. Per-folder rather than
 *  one flag for the card, so dismissing "I know about NGC 6888" never hides a
 *  *different* folder that goes missing next month. localStorage-only and
 *  defensively guarded, like the other Library nudges. */
const LS_KEY = "astrostack.skippedFolders.dismissed";

export function loadDismissed(): string[] {
  try {
    const raw = JSON.parse(localStorage.getItem(LS_KEY) || "[]");
    return Array.isArray(raw) ? raw.filter((p): p is string => typeof p === "string") : [];
  } catch {
    return [];
  }
}

function saveDismissed(paths: string[]): void {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(paths));
  } catch {
    /* storage unavailable — the dismissal just won't persist */
  }
}

/** The folders still worth showing (pure, tested).
 *
 * A folder the user dismissed stays hidden — but only that folder: a new skip
 * appearing later is a new fact and must be able to speak. */
export function undismissedFolders(
  folders: SkippedIncomingFolder[], dismissed: string[],
): SkippedIncomingFolder[] {
  const hidden = new Set(dismissed);
  return folders.filter((f) => !hidden.has(f.path));
}

/** The one-line count that heads the alert (pure, tested). */
export function skippedFoldersLead(folders: SkippedIncomingFolder[]): string {
  const files = folders.reduce((n, f) => n + f.n_unrecognised, 0);
  const where = folders.length === 1
    ? `A folder in your incoming folder`
    : `${folders.length} folders in your incoming folder`;
  return `${where} hold${folders.length === 1 ? "s" : ""} `
    + `${files.toLocaleString()} file${files === 1 ? "" : "s"} that aren't reaching `
    + `${folders.length === 1 ? "a picture" : "your pictures"}.`;
}

/**
 * "Some of your subs may not be reaching a picture" — the standing home for a
 * scan's unexplained folder skips.
 *
 * The Seestar convention skips a bare `<T>/` folder sitting beside `<T>_sub/`,
 * because on a Seestar that folder is the finished picture the scope made for
 * itself. When the files inside it are *not* named like the device's output, the
 * scan has walked past frames it cannot account for — and the owner's library has
 * exactly that shape (an `NGC 6888` of 4,815 files beside an `NGC 6888_SUB` of
 * 3,110 different ones).
 *
 * That has been reported since v0.329.2 and actionable since v0.378.0, but only
 * on the **Jobs page**, attached to one scan's result — and the scan that finds
 * it is usually the watcher's, fired while nobody is at the screen. This is the
 * same finding where the owner will actually meet it.
 *
 * Silent on a healthy library (the endpoint returns nothing), silent once the
 * folder has been brought in (the backend drops it), and dismissible per folder
 * for one the owner is deliberately leaving out. It never deletes, moves or
 * renames anything: bringing a folder in is a *read* of `incoming/`.
 */
export function SkippedFoldersCard() {
  const [dismissed, setDismissed] = useState<string[]>(() => loadDismissed());
  const q = useQuery({
    queryKey: ["skipped-folders"],
    queryFn: api.skippedFolders,
  });

  const folders = undismissedFolders(q.data ?? [], dismissed);
  if (!folders.length) return null;

  const dismiss = () => {
    const next = Array.from(new Set([...dismissed, ...folders.map((f) => f.path)]));
    setDismissed(next);
    saveDismissed(next);
  };

  return (
    <Alert
      color="yellow"
      variant="light"
      icon={<IconFolderQuestion size={18} />}
      title="Some of your subs may not be reaching a picture"
      mb="md"
    >
      <Stack gap={6}>
        <Text size="sm">
          {skippedFoldersLead(folders)}
          {" A folder named the same as one of your \"_sub\" folders is normally "}
          {"the finished picture your Seestar made on the scope, so it isn't "}
          {"stacked with your raw subs — but these hold files that don't look "}
          {"like your Seestar's own pictures."}
        </Text>
        <Stack gap={2}>
          {folders.map((f) => (
            <div key={f.path}>
              <Text size="xs">
                {`${f.name}: ${f.n_files.toLocaleString()} file`}
                {f.n_files === 1 ? "" : "s"}
                {` skipped, ${f.n_unrecognised.toLocaleString()} of them not `}
                {"recognised as your Seestar's own picture."}
              </Text>
              <BringFolderInButton path={f.path} name={f.name} />
            </div>
          ))}
        </Stack>
        <Text size="xs" c="dimmed">
          {"Bringing a folder in adds its frames to the target of the same name, "}
          {"and leaves out any of your Seestar's own finished pictures inside it. "}
          {"Nothing on your disk is deleted, moved or renamed."}
        </Text>
        <Group gap="xs">
          <Button size="xs" variant="subtle" color="gray" onClick={dismiss}>
            {folders.length === 1 ? "Leave it out" : "Leave them out"}
          </Button>
        </Group>
      </Stack>
    </Alert>
  );
}
