import { Alert, Badge, Button, Group, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type CleanupSuggestion } from "../api/client";

// Remember which cleanup nudges the user dismissed, keyed by the flagged
// targets' safe-names, so a declined nudge stays gone across reloads (and only
// reappears if a different junk target turns up). localStorage-only and
// defensively guarded so a disabled/broken store never breaks the page.
const LS_KEY = "astrostack.cleanupSuggestions.dismissed";

function loadDismissed(): boolean {
  try {
    return localStorage.getItem(LS_KEY) === "1";
  } catch {
    return false;
  }
}

function saveDismissed(): void {
  try {
    localStorage.setItem(LS_KEY, "1");
  } catch {
    /* storage unavailable — dismissal just won't persist */
  }
}

function reasonLabel(reason: CleanupSuggestion["reason"]): string {
  return reason === "video" ? "video" : "on-device output";
}

/**
 * "These look like Seestar outputs/videos, not raw subs — remove?" — a friendly,
 * dismissible Library cleanup nudge. An older scan (before the scanner learned
 * the Seestar folder convention) ingested the Seestar's own single stacked
 * *output* folders and ``_video`` folders as if they were raw sub-frames,
 * leaving junk targets that "stack" to one lower-resolution frame. The backend
 * detects those (read-only); this offers a one-confirmation bulk-remove. It
 * never touches the real ``_sub`` data. Self-hides when there's nothing to
 * clean up.
 */
export function CleanupSuggestionsCard() {
  const qc = useQueryClient();
  const suggestions = useQuery({
    queryKey: ["cleanup-suggestions"],
    queryFn: api.cleanupSuggestions,
  });
  const [dismissed, setDismissed] = useState<boolean>(loadDismissed);

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

  const dismiss = () => {
    setDismissed(true);
    saveDismissed();
  };

  const items = suggestions.data ?? [];
  if (dismissed || items.length === 0) return null;

  const onRemove = () => {
    const msg =
      items.length === 1
        ? `Remove the leftover target “${items[0].name}”? This only deletes the target record — your raw sub folders on disk are not touched.`
        : `Remove these ${items.length} leftover targets? This only deletes the target records — your raw sub folders on disk are not touched.`;
    if (window.confirm(msg)) remove.mutate(items);
  };

  return (
    <Alert
      color="teal"
      variant="light"
      icon={<IconTrash size={18} />}
      title="Some targets look like Seestar outputs or videos, not raw subs"
      withCloseButton
      onClose={dismiss}
      closeButtonLabel="Dismiss"
      mb="md"
    >
      <Stack gap={8}>
        <Text size="sm">
          An earlier scan picked up the Seestar's own finished images and video
          clips as if they were raw sub-frames. These can't be stacked into a
          good picture — remove them to tidy your library. Your raw sub folders
          on disk are never touched.
        </Text>
        <Group gap={6}>
          {items.map((t) => (
            <Badge key={t.safe} variant="outline" color="gray" size="sm">
              {t.name} · {reasonLabel(t.reason)}
            </Badge>
          ))}
        </Group>
        <Group gap="xs">
          <Button
            size="xs"
            color="teal"
            loading={remove.isPending}
            onClick={onRemove}
          >
            Remove {items.length === 1 ? "this target" : `these ${items.length} targets`}
          </Button>
          <Button size="xs" variant="subtle" color="gray" onClick={dismiss}>
            Keep them
          </Button>
        </Group>
      </Stack>
    </Alert>
  );
}
