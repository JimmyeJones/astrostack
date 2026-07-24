import { Alert, Badge, Button, Group, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconCopyOff, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, type CleanupSuggestion } from "../api/client";

// Remember which cleanup nudges the user dismissed, keyed per group so declining
// one (e.g. "these aren't real subs") doesn't also hide the other (e.g. "these
// are duplicates"). localStorage-only and defensively guarded so a
// disabled/broken store never breaks the page.
const JUNK_LS_KEY = "astrostack.cleanupSuggestions.dismissed";
const DUP_LS_KEY = "astrostack.cleanupSuggestions.duplicates.dismissed";

function loadDismissed(key: string): boolean {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function saveDismissed(key: string): void {
  try {
    localStorage.setItem(key, "1");
  } catch {
    /* storage unavailable — dismissal just won't persist */
  }
}

function reasonLabel(reason: CleanupSuggestion["reason"]): string {
  if (reason === "video") return "video";
  if (reason === "duplicate_sub") return "duplicate";
  return "on-device output";
}

/** One dismissible cleanup group (junk outputs/videos, or `_sub` duplicates).
 * Owns its own persisted dismissal so the two groups hide independently. */
function CleanupAlert({
  items,
  lsKey,
  icon,
  title,
  intro,
  onRemove,
  pending,
}: {
  items: CleanupSuggestion[];
  lsKey: string;
  icon: ReactNode;
  title: string;
  intro: ReactNode;
  onRemove: (items: CleanupSuggestion[]) => void;
  pending: boolean;
}) {
  const [dismissed, setDismissed] = useState<boolean>(() => loadDismissed(lsKey));
  if (dismissed || items.length === 0) return null;

  const dismiss = () => {
    setDismissed(true);
    saveDismissed(lsKey);
  };
  const removeNoun =
    items.length === 1 ? "this target" : `these ${items.length} targets`;
  const confirmMsg =
    items.length === 1
      ? `Remove the leftover target “${items[0].name}”? This only deletes the target record — your raw sub folders on disk are not touched.`
      : `Remove these ${items.length} leftover targets? This only deletes the target records — your raw sub folders on disk are not touched.`;
  const askRemove = () => {
    if (window.confirm(confirmMsg)) onRemove(items);
  };

  return (
    <Alert
      color="teal"
      variant="light"
      icon={icon}
      title={title}
      withCloseButton
      onClose={dismiss}
      closeButtonLabel="Dismiss"
      mb="md"
    >
      <Stack gap={8}>
        <Text size="sm">{intro}</Text>
        <Group gap={6}>
          {items.map((t) => (
            <Badge key={t.safe} variant="outline" color="gray" size="sm">
              {t.name} · {reasonLabel(t.reason)}
            </Badge>
          ))}
        </Group>
        <Group gap="xs">
          <Button size="xs" color="teal" loading={pending} onClick={askRemove}>
            Remove {removeNoun}
          </Button>
          <Button size="xs" variant="subtle" color="gray" onClick={dismiss}>
            Keep them
          </Button>
        </Group>
      </Stack>
    </Alert>
  );
}

/**
 * Friendly, dismissible Library cleanup nudges for the leftovers a pre-convention
 * scan produced. Two independent groups:
 *   • outputs/videos — the Seestar's own finished images / video clips ingested as
 *     if they were raw subs (can't be stacked into a good picture);
 *   • `<T>_sub` duplicates — the same raw subs the base target `<T>` now owns
 *     (harmless clutter + double compute, not corrupt data).
 * The backend detects both (read-only); this offers a one-confirmation
 * bulk-remove per group. It never touches the real `_sub` data on disk. Each
 * group self-hides when empty or dismissed.
 */
export function CleanupSuggestionsCard() {
  const qc = useQueryClient();
  const suggestions = useQuery({
    queryKey: ["cleanup-suggestions"],
    queryFn: api.cleanupSuggestions,
  });

  const remove = useMutation({
    mutationFn: async (targets: CleanupSuggestion[]) => {
      // Only remove the target records; the underlying raw ``_sub`` folders on
      // disk are never deleted (remove_files=false), so nothing real is lost.
      for (const t of targets) await api.deleteTarget(t.safe, false);
      return targets.length;
    },
    onSuccess: (n) => {
      notifications.show({
        message: `Removed ${n} leftover ${n === 1 ? "target" : "targets"}. Your raw sub folders on disk are untouched.`,
        color: "teal",
      });
      qc.invalidateQueries({ queryKey: ["targets"] });
      qc.invalidateQueries({ queryKey: ["cleanup-suggestions"] });
    },
    onError: (err) => {
      notifications.show({
        message: `Couldn't remove those targets: ${err instanceof Error ? err.message : String(err)}`,
        color: "red",
      });
      // Refresh so any that did delete drop out of the list.
      qc.invalidateQueries({ queryKey: ["targets"] });
      qc.invalidateQueries({ queryKey: ["cleanup-suggestions"] });
    },
  });

  const items = suggestions.data ?? [];
  const junk = items.filter((t) => t.reason !== "duplicate_sub");
  const dupes = items.filter((t) => t.reason === "duplicate_sub");
  const onRemove = (targets: CleanupSuggestion[]) => remove.mutate(targets);

  return (
    <>
      <CleanupAlert
        items={junk}
        lsKey={JUNK_LS_KEY}
        icon={<IconTrash size={18} />}
        title="Some targets look like Seestar outputs or videos, not raw subs"
        intro={
          <>
            An earlier scan picked up the Seestar's own finished images and video
            clips as if they were raw sub-frames. These can't be stacked into a
            good picture — remove them to tidy your library. Your raw sub folders
            on disk are never touched.
          </>
        }
        onRemove={onRemove}
        pending={remove.isPending}
      />
      <CleanupAlert
        items={dupes}
        lsKey={DUP_LS_KEY}
        icon={<IconCopyOff size={18} />}
        title="Some targets are duplicates left by an older scan"
        intro={
          <>
            An earlier scan added these “_sub” targets before the app learned to
            fold each Seestar raw-subs folder into its main target. They hold the
            same frames your main target already has, so they just clutter your
            library and re-stack the same subs twice. Removing them changes
            nothing about your pictures, and your files on disk are never touched.
          </>
        }
        onRemove={onRemove}
        pending={remove.isPending}
      />
    </>
  );
}
