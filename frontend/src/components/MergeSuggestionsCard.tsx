import { Alert, Badge, Button, Group, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconLayersUnion } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type MergeSuggestion } from "../api/client";
import { formatIntegration } from "../format";
import {
  describeMergeSuggestion,
  mergeInto,
  mergeSources,
  mergeSuggestionSignature,
} from "./mergeSuggestions";

// Remember which suggestions the user dismissed, keyed by a stable membership
// signature, so a declined nudge stays gone across reloads (and only reappears
// if a new same-object folder joins the group). localStorage-only and defensively
// guarded so a disabled/broken store never breaks the page.
const LS_KEY = "astrostack.mergeSuggestions.dismissed";

function loadDismissed(): Set<string> {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw) as unknown;
    return new Set(Array.isArray(arr) ? arr.filter((x): x is string => typeof x === "string") : []);
  } catch {
    return new Set();
  }
}

function saveDismissed(s: Set<string>): void {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify([...s]));
  } catch {
    /* storage unavailable — dismissal just won't persist */
  }
}

/**
 * "Same object? Combine these into one deep picture" — a friendly, dismissible
 * Library nudge. The Seestar app writes a new folder per night, so a beginner who
 * shoots one object across several nights silently ends up with several separate,
 * shallow targets instead of one deep one. The backend detects those same-object
 * clusters by plate-solved centre; this offers the one-click merge (into the
 * deepest member) that makes the deep image "just happen". Self-hides when there's
 * nothing to suggest.
 */
export function MergeSuggestionsCard() {
  const qc = useQueryClient();
  const suggestions = useQuery({
    queryKey: ["merge-suggestions"],
    queryFn: api.mergeSuggestions,
  });
  const [dismissed, setDismissed] = useState<Set<string>>(loadDismissed);

  const merge = useMutation({
    mutationFn: (s: MergeSuggestion) => api.mergeTargets(mergeInto(s), mergeSources(s)),
    onSuccess: (_data, s) => {
      const label = s.object_name || s.targets[0]?.name || "target";
      notifications.show({
        message: `Combined ${s.targets.length} folders of ${label} into one deep target. Re-stack it to get the deeper picture.`,
        color: "grape",
      });
      // The merge removed the source targets and moved their frames — refresh the
      // library grid and the suggestions themselves.
      qc.invalidateQueries({ queryKey: ["targets"] });
      qc.invalidateQueries({ queryKey: ["merge-suggestions"] });
    },
    onError: (err) => {
      notifications.show({
        message: `Couldn't combine those targets: ${err instanceof Error ? err.message : String(err)}`,
        color: "red",
      });
    },
  });

  const dismiss = (s: MergeSuggestion) => {
    const next = new Set(dismissed);
    next.add(mergeSuggestionSignature(s));
    setDismissed(next);
    saveDismissed(next);
  };

  const visible = (suggestions.data ?? []).filter(
    (s) => !dismissed.has(mergeSuggestionSignature(s)),
  );
  if (visible.length === 0) return null;

  return (
    <Stack gap="xs" mb="md">
      {visible.map((s) => (
        <Alert
          key={mergeSuggestionSignature(s)}
          color="grape"
          variant="light"
          icon={<IconLayersUnion size={18} />}
          title="Same object in more than one folder?"
          withCloseButton
          onClose={() => dismiss(s)}
          closeButtonLabel="Dismiss"
        >
          <Stack gap={8}>
            <Text size="sm">{describeMergeSuggestion(s)}</Text>
            <Group gap={6}>
              {s.targets.map((t) => (
                <Badge key={t.safe} variant="outline" color="gray" size="sm">
                  {t.name} · {t.n_frames_accepted} subs · {formatIntegration(t.total_exposure_s)}
                </Badge>
              ))}
            </Group>
            <Group gap="xs">
              <Button
                size="xs"
                color="grape"
                loading={merge.isPending && merge.variables === s}
                onClick={() => merge.mutate(s)}
              >
                Combine into one deep target
              </Button>
              <Button size="xs" variant="subtle" color="gray" onClick={() => dismiss(s)}>
                Not the same object
              </Button>
            </Group>
            <Text size="10px" c="dimmed">
              Merges into “{s.targets[0]?.name}” (your deepest folder) and keeps every sub — nothing is deleted.
            </Text>
          </Stack>
        </Alert>
      ))}
    </Stack>
  );
}
