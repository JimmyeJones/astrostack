import { Alert, Text } from "@mantine/core";
import { IconSparkles } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";

/**
 * The guided first-run tour — one plain sentence per screen, shown **only while
 * you're looking at the sample target**.
 *
 * "Try it with a sample image" (v0.199.0) gives a newcomer real-looking data to
 * poke at before their first clear night, but the *screens* it drops them on are
 * still unlabelled: a first-timer on Target / Stack / Editor doesn't necessarily
 * know what they're looking at or what to press next. This is the missing
 * coaching — a small, non-modal, dismissible note that says what this screen is
 * for and where to go after it.
 *
 * Deliberately narrow so it can never become clutter:
 *
 * * It renders **only** when the sample demo is loaded *and* the target on
 *   screen is that sample — a real target never sees a word of it.
 * * Each step is dismissed independently and remembered in `localStorage`, so
 *   waving one away doesn't hide the rest of the tour (and reading the tour once
 *   doesn't nag you on the next visit).
 * * Removing the sample removes the whole tour with it — nothing to clean up.
 *
 * Frontend-only and read-only: it reuses the `GET /api/sample` status the
 * onboarding card already queries, so there is no new endpoint, no schema, and
 * nothing new stored server-side.
 */

/** The screens the tour covers, in the order a beginner meets them. */
export type SampleTourStep = "target" | "stack" | "editor";

interface StepCopy {
  title: string;
  body: string;
}

/** What each screen is for, in one calm sentence, plus what to do next. Exported
 * so the copy is unit-testable without rendering (and so it can't silently drift
 * out of sync with the steps the routes mount). */
export const SAMPLE_TOUR_COPY: Record<SampleTourStep, StepCopy> = {
  target: {
    title: "This is a target — one object, all its frames",
    body: "Everything you shoot of one object lives here. The table is your "
      + "individual frames (\"subs\"); green ones are kept, and quality control "
      + "has already measured how sharp each is. Nothing here changes your "
      + "files. When you're happy, head to Stack to combine them into one "
      + "clean picture.",
  },
  stack: {
    title: "Stacking combines your frames into one clean picture",
    body: "Adding frames together averages the noise away — that's the whole "
      + "trick, and it's why more subs make a better image. The defaults are "
      + "already sensible, so you can just press Start and watch. Afterwards "
      + "you'll land in the editor to bring out the detail.",
  },
  editor: {
    title: "This is the editor — nothing you do here is permanent",
    body: "Your stack is linear and dark until it's stretched, so it looks "
      + "nothing like the final picture yet. Press Auto for a good starting "
      + "point, then nudge anything you like — every change is a step you can "
      + "undo or reorder, and your stacked data is never overwritten. Export "
      + "when it looks right.",
  },
};

const LS_PREFIX = "astrostack.sampleTour.dismissed.";

function loadDismissed(step: SampleTourStep): boolean {
  try {
    return localStorage.getItem(LS_PREFIX + step) === "1";
  } catch {
    return false;
  }
}

function saveDismissed(step: SampleTourStep): void {
  try {
    localStorage.setItem(LS_PREFIX + step, "1");
  } catch {
    /* storage unavailable — the note just won't stay dismissed */
  }
}

/**
 * Render the tour note for one screen, or nothing at all.
 *
 * `safe` is the target currently on screen; the note appears only when it *is*
 * the loaded sample. Pass `null` (e.g. while the route is still resolving) and
 * it renders nothing.
 */
export function SampleTourNote({ step, safe }: {
  step: SampleTourStep;
  safe: string | null | undefined;
}) {
  const [dismissed, setDismissed] = useState(() => loadDismissed(step));
  // Shares the ["sample"] query key with the onboarding card, so this is a cache
  // read on any screen that already loaded it. Skipped entirely once the step is
  // dismissed (or before the route resolves a target), so the overwhelming
  // majority of page loads — established users, real targets after one dismissal
  // — cost nothing at all.
  const sample = useQuery({
    queryKey: ["sample"],
    queryFn: api.getSampleStatus,
    enabled: !dismissed && !!safe,
  });

  if (dismissed || !safe) return null;
  const status = sample.data;
  if (!status?.loaded || !status.safe || status.safe !== safe) return null;

  const copy = SAMPLE_TOUR_COPY[step];
  return (
    <Alert
      variant="light"
      color="grape"
      radius="md"
      icon={<IconSparkles size={18} />}
      title={copy.title}
      withCloseButton
      closeButtonLabel="Hide this tip"
      onClose={() => {
        saveDismissed(step);
        setDismissed(true);
      }}
    >
      <Text size="sm">{copy.body}</Text>
      <Text size="xs" c="dimmed" mt={4}>
        You're looking at the sample — these tips only show here.
      </Text>
    </Alert>
  );
}
