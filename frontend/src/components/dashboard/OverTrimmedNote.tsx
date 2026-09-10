import { Alert, Anchor, Button, Group, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { loadDismissedSig, saveDismissedSig } from "../../dismissal";
import { sharePctLabel } from "../editor/mosaicTrim";

const DISMISS_KEY = "astrostack.dashboard.overTrimmedDismissed";

// How many targets the note names outright before it stops listing and points at
// the Library instead — the same bound the new-subs and un-exported-edits notes
// use, because three is what fits on one line on a phone.
const NAMED = 3;

/** A keep-fraction as the editor's own share wording ("about 3%", "under 1%"),
 * so this note, the Target page's and the editor's never report one measurement
 * three ways. */
function pct(frac: number | null | undefined): string {
  return sharePctLabel(frac ?? 0);
}

/**
 * "Some of your pictures were trimmed too far by an older version."
 *
 * The D1 border-trim bugs cropped a **mosaic** to its panel overlaps: correct on
 * a single field, a sliver on a union canvas. Those were fixed across
 * v0.386–v0.399, and every one of the fixes re-derives the *trim*. Nothing
 * re-derives a crop that was already **saved** — and a saved recipe is what the
 * editor, the hero image, the Library card, the thumbnail and the share sheet all
 * replay. So a target Auto-edited on an affected build still shows the sliver
 * today, under a stored auto-note that reports the 97% trim as if it were right.
 * The 2026-09-10 external audit reproduced exactly that in the shipped image.
 *
 * The per-picture version of this note lives in the editor, where the fix is one
 * click. This is its library-wide half, for the same reason `NewSubsWaitingNote`
 * has one: the owner processed many mosaics on those builds, and the question
 * after upgrading — *which* pictures do I need to look at? — had no surface at
 * all. You had to open each target to find out.
 *
 * Self-hides at zero, which is every healthy install and every library on the
 * very first render, and is dismissable by *signature*, so "not now" quiets
 * exactly this set and a picture that turns up later still speaks.
 *
 * **Advisory, and it never acts.** A small crop may be the owner's own framing,
 * so nothing here rewrites a recipe and there is deliberately no "fix them all"
 * button: each link lands in that picture's editor, where the one-click re-seed
 * is, and where you can see the before and after for yourself.
 */
export function OverTrimmedNote() {
  const { data } = useQuery({
    queryKey: ["over-trimmed-pictures"],
    queryFn: api.getOverTrimmedPictures,
    // Long on purpose: this is a cross-target read on a polling page, and it is
    // about recipes already on disk. Once per visit is plenty.
    staleTime: 300_000,
  });
  const [dismissedSig, setDismissedSig] = useState(() => loadDismissedSig(DISMISS_KEY));

  const count = data?.count ?? 0;
  if (count === 0) return null;

  const items = data?.items ?? [];
  // The signature carries which pictures, so re-seeding some and leaving others
  // makes the note speak again about what is left rather than staying quiet.
  const sig = `${count}|${items.map((i) => `${i.safe}:${i.run_id}`).join(",")}`;
  if (sig === dismissedSig) return null;

  const named = items.slice(0, NAMED);
  const worst = items[0];
  const title = count === 1
    ? "A picture was trimmed too far by an older version"
    : `${count} pictures were trimmed too far by an older version`;

  return (
    <Alert
      color="orange" variant="light" data-testid="over-trimmed-note"
      withCloseButton closeButtonLabel="Not now"
      onClose={() => { setDismissedSig(sig); saveDismissedSig(DISMISS_KEY, sig); }}
      title={title}
    >
      <Text size="sm">
        {count === 1
          ? "An older version of AstroStack cut away too much of this picture's edge "
          : "An older version of AstroStack cut away too much of these pictures' edges "}
        when it trimmed the ragged mosaic border, and the crop it chose is saved in
        {count === 1 ? " that picture's" : " each picture's"} edit — so you are still
        seeing the cropped version everywhere it appears.
        {worst?.stored_keep_fraction != null && worst?.suggested_keep_fraction != null
          ? ` The worst is showing ${pct(worst.stored_keep_fraction)} of the frame `
            + `where ${pct(worst.suggested_keep_fraction)} is good.`
          : ""}
        {" "}Opening {count === 1 ? "it" : "one"} lets you put the border back in one
        click. Nothing has been changed for you — your stacks are untouched, and the
        edit is undoable.
      </Text>
      <Group gap="sm" mt="xs" wrap="wrap">
        {named.map((it) => (
          <Button
            key={it.safe}
            component={Link} to={`/targets/${it.safe}/edit/${it.run_id}`}
            size="compact-xs" variant="light" color="orange"
          >
            {`${it.target_name} · showing ${pct(it.stored_keep_fraction)}`}
          </Button>
        ))}
        {/* Deliberately *not* "see all N in the Library": the Library doesn't
            single these out, and a link that promises a list nobody wrote is the
            kind of small untruth this app keeps having to unpick. */}
        {count > named.length ? (
          <Anchor component={Link} to="/library" size="xs">
            {`${count - named.length} more in your Library →`}
          </Anchor>
        ) : null}
      </Group>
    </Alert>
  );
}
