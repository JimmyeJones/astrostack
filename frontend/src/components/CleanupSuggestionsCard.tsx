import { Alert, Badge, Button, Group, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconArrowMerge, IconCopyOff, IconTrash } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, type CleanupSuggestion } from "../api/client";
import { WRAPPING_BADGE } from "../badgeFit";
import { mergeCoverClause, mergeKeptClause } from "./mergeSuggestions";

// Remember which cleanup nudges the user dismissed, keyed per group so declining
// one (e.g. "these aren't real subs") doesn't also hide the other (e.g. "these
// are duplicates"). localStorage-only and defensively guarded so a
// disabled/broken store never breaks the page.
const JUNK_LS_KEY = "astrostack.cleanupSuggestions.dismissed";
const DUP_LS_KEY = "astrostack.cleanupSuggestions.duplicates.dismissed";
const MIXED_LS_KEY = "astrostack.cleanupSuggestions.mixedDrop.dismissed";
const COMBINE_LS_KEY = "astrostack.cleanupSuggestions.combine.dismissed";

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
  if (reason === "photo") return "photo";
  if (reason === "temp_folder") return "temp folder";
  if (reason === "duplicate_sub") return "duplicate";
  if (reason === "duplicate_sub_merge") return "duplicate with pictures";
  if (reason === "legacy_mixed_drop") return "mixed drop";
  return "on-device output";
}

/** One dismissible cleanup group (junk outputs/videos, `_sub` duplicates, or the
 * duplicates that hold pictures and are combined rather than removed).
 * Owns its own persisted dismissal so the groups hide independently.
 *
 * `action` is what the group's button does. It defaults to the removal this card
 * has always offered; the combine group passes its own wording and mutation,
 * because deleting one of those targets would take the owner's pictures with it. */
function CleanupAlert({
  items,
  lsKey,
  icon,
  title,
  intro,
  onRemove,
  pending,
  action,
}: {
  items: CleanupSuggestion[];
  lsKey: string;
  icon: ReactNode;
  title: string;
  intro: ReactNode;
  onRemove: (items: CleanupSuggestion[]) => void;
  pending: boolean;
  action?: {
    label: (items: CleanupSuggestion[]) => string;
    confirm: (items: CleanupSuggestion[]) => string;
    badge?: (item: CleanupSuggestion) => string;
  };
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
  const buttonLabel = action ? action.label(items) : `Remove ${removeNoun}`;
  const askRemove = () => {
    if (window.confirm(action ? action.confirm(items) : confirmMsg)) onRemove(items);
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
            <Badge key={t.safe} variant="outline" color="gray" size="sm"
              styles={WRAPPING_BADGE}>
              {action?.badge ? action.badge(t) : `${t.name} · ${reasonLabel(t.reason)}`}
            </Badge>
          ))}
        </Group>
        <Group gap="xs">
          <Button size="xs" color="teal" loading={pending} onClick={askRemove}>
            {buttonLabel}
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
 * scan produced. Independent groups:
 *   • outputs/videos/photos/temp folders — the Seestar's own finished images,
 *     video clips and single snapshots, plus another program's scratch folder
 *     sharing the astro share, ingested as if they were raw subs (can't be
 *     stacked into a good picture);
 *   • `<T>_sub` duplicates — the same raw subs the base target `<T>` now owns
 *     (harmless clutter + double compute, not corrupt data);
 *   • the duplicates that *also* hold pictures or notes of their own, which are
 *     combined into the base rather than removed, so those travel instead of
 *     being lost with the target record.
 * The backend detects them all (read-only); this offers a one-confirmation bulk
 * action per group. It never touches the real `_sub` data on disk. Each group
 * self-hides when empty or dismissed.
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

  // The other half of the duplicate story. These leftovers hold the owner's own
  // pictures or notes, so the backend refuses to offer a delete — combining
  // carries the runs (with their output files and saved recipes), the notes, the
  // tags and the target preferences into the base target first, then tidies the
  // leftover away. Sequential rather than parallel: each merge rewrites the
  // library registry, and one failure must not leave the rest half-applied.
  const combine = useMutation({
    mutationFn: async (targets: CleanupSuggestion[]) => {
      let n = 0;
      // The same two facts the merge *nudge* reports, because this is the same
      // `POST /api/targets/merge`: how many finished pictures came across, and
      // whether the destination had its own picture pinned as the cover to stop
      // a carried one-night stack replacing it. Both were being thrown away
      // here, so one operation described itself two ways depending on which
      // Combine button the owner happened to press — and this is the button the
      // duplicate-target reconciliation is offered on.
      let pictures = 0;
      let pinned = false;
      for (const t of targets) {
        if (!t.merge_into_safe) continue;
        const res = await api.mergeTargets(t.merge_into_safe, [t.safe]);
        pictures += res?.pictures_kept ?? 0;
        pinned = pinned || !!res?.picture_pinned;
        n += 1;
      }
      return { n, pictures, pinned };
    },
    onSuccess: ({ n, pictures, pinned }) => {
      notifications.show({
        message: `Combined ${n} leftover ${n === 1 ? "target" : "targets"} into your main ${n === 1 ? "target" : "targets"}.`
          + ` Your pictures and notes moved across; your files on disk are untouched.`
          + `${mergeKeptClause(pictures)}${mergeCoverClause(pinned)}`,
        color: "teal",
      });
      qc.invalidateQueries({ queryKey: ["targets"] });
      qc.invalidateQueries({ queryKey: ["cleanup-suggestions"] });
      qc.invalidateQueries({ queryKey: ["merge-suggestions"] });
    },
    onError: (err) => {
      notifications.show({
        message: `Couldn't combine those targets: ${err instanceof Error ? err.message : String(err)}`,
        color: "red",
      });
      qc.invalidateQueries({ queryKey: ["targets"] });
      qc.invalidateQueries({ queryKey: ["cleanup-suggestions"] });
    },
  });

  const items = suggestions.data ?? [];
  const junk = items.filter(
    (t) =>
      t.reason === "video" ||
      t.reason === "photo" ||
      t.reason === "on_device_output" ||
      t.reason === "temp_folder",
  );
  const dupes = items.filter((t) => t.reason === "duplicate_sub");
  const mixed = items.filter((t) => t.reason === "legacy_mixed_drop");
  const combinable = items.filter(
    (t) => t.reason === "duplicate_sub_merge" && !!t.merge_into_safe,
  );
  const onRemove = (targets: CleanupSuggestion[]) => remove.mutate(targets);
  const onCombine = (targets: CleanupSuggestion[]) => combine.mutate(targets);

  return (
    <>
      <CleanupAlert
        items={junk}
        lsKey={JUNK_LS_KEY}
        icon={<IconTrash size={18} />}
        title="Some targets look like Seestar outputs, videos or photos — or another program's working folder — not raw subs"
        intro={
          <>
            An earlier scan picked up the Seestar's own finished images, video
            clips and single snapshots — and any scratch folder another stacking
            program left in the same share — as if they were raw sub-frames.
            These can't be stacked into a good picture — remove them to tidy your
            library. Your raw sub folders on disk are never touched.
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
      <CleanupAlert
        items={combinable}
        lsKey={COMBINE_LS_KEY}
        icon={<IconArrowMerge size={18} />}
        title="Some duplicate targets also hold pictures you've already made"
        intro={
          <>
            An earlier scan added these before the app learned to fold each
            Seestar raw-subs folder into its main target. They hold the same
            frames your main target already has — but you've also stacked
            pictures from them, or written notes on them, so simply removing them
            would take those with them. Combining moves the pictures, notes and
            tags across into the main target first, so nothing is lost. Your
            files on disk are never touched.
          </>
        }
        onRemove={onCombine}
        pending={combine.isPending}
        action={{
          label: (list) =>
            list.length === 1
              ? "Combine it into the main target"
              : `Combine these ${list.length} into their main targets`,
          confirm: (list) =>
            list.length === 1
              ? `Combine “${list[0].name}” into “${list[0].merge_into_name}”? Its pictures, notes and tags move across first, then the leftover target is tidied away. Your raw sub folders on disk are not touched.`
              : `Combine these ${list.length} leftover targets into their main targets? Their pictures, notes and tags move across first, then the leftovers are tidied away. Your raw sub folders on disk are not touched.`,
          badge: (t) => `${t.name} → ${t.merge_into_name}`,
        }}
      />
      <CleanupAlert
        items={mixed}
        lsKey={MIXED_LS_KEY}
        icon={<IconCopyOff size={18} />}
        title="A target looks like a whole Seestar card dropped in at once"
        intro={
          <>
            An earlier scan lumped a whole Seestar card or share into a single
            target, mixing several different objects' subs together (plus the
            Seestar's own finished images and videos), so it can't stack into a
            clean picture. The app has since re-sorted those frames into their own
            proper targets, so this jumbled one is now a stale duplicate. Removing
            it changes nothing about your pictures, and your files on disk are
            never touched.
          </>
        }
        onRemove={onRemove}
        pending={remove.isPending}
      />
    </>
  );
}
