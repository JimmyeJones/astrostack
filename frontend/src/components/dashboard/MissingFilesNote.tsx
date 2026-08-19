import { Alert, Button, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { libraryMissingFilesNote } from "./libraryMissingFiles";

/**
 * "Your subs aren't on disk" — said once for the whole library.
 *
 * The Target page has warned about this per target since v0.232.0, but the cause
 * almost never stops at one target: an unmounted drive or an offline NAS share
 * takes out every target at once, and the owner would have to open each one in
 * turn to find that out. Meanwhile nothing is obviously broken — the app looks
 * healthy, the frames are all still listed, and the first real symptom is a
 * walk-away stack coming out thin hours later. This is the same honesty at
 * library scale, on the page they land on first, while the drive is still there
 * to be reconnected.
 *
 * Self-hiding at zero, which is the overwhelmingly common case: on a healthy
 * install it renders nothing and the notice board folds nothing. It swallows a
 * failed read (an older backend has no such endpoint) rather than showing an
 * error — a missing answer is not a missing drive. Deliberately *not*
 * dismissable: unlike the un-exported-edits note, this isn't work the user chose
 * to defer, it is a live storage fault that resolves itself the moment the share
 * is back.
 */
export function MissingFilesNote() {
  const { data } = useQuery({
    queryKey: ["library-missing-files"],
    queryFn: () => api.getLibraryMissingFiles().catch(() => null),
    // Long on purpose: answering means opening every project and one stat() per
    // accepted frame. The server caches it too — this stale time is what keeps a
    // polling page from asking for it on every tick.
    staleTime: 300_000,
  });

  const note = libraryMissingFilesNote(data);
  if (!note) return null;

  return (
    <Alert
      color="yellow" variant="light" data-testid="missing-files-note"
      title={note.title}
    >
      <Text size="sm">{note.message}</Text>
      {/* One affected target can be pointed at directly; a library-wide outage
          can't, so that case sends them to the Library rather than picking an
          arbitrary target out of the list. */}
      <Button
        component={Link}
        to={note.onlyTargetSafe ? `/targets/${note.onlyTargetSafe}` : "/library"}
        size="xs" variant="light" color="yellow" mt="xs"
      >
        {note.onlyTargetSafe ? "Open this target" : "Open your library"}
      </Button>
    </Alert>
  );
}
