# Current focus — AstroStack

*Last rewritten 2026-09-27. **The Scout rewrites this page** whenever the front of the
queue changes; it stays short (≤ 60 lines) and dated. Live rules are in `AGENTS.md`;
the backlog is `docs/IMPROVEMENTS.md`. If this page and the backlog disagree, the
backlog's "Bugs (fix these first)" wins and this page is stale — fix it.*

## Front of the queue

1. **"Combine into one deep target" (three bugs, filed 2026-09-26, reproduced).** The next
   scan silently undoes a merge; the merge drops the source target's notes, tags, saved
   stack settings, goal and cover pin; and the deep target's picture becomes the shallow
   carried one. The owner has been told not to use the button until these ship.
2. **Owner-approved, buildable now** (answers of 2026-09-25, on `main` via PR #981):
   - reconcile the 11 historical mosaic pairs (#878) through `merge.carry_stack_runs` —
     after item 1, since it uses the same merge;
   - `astroalign` for the WCS-free registration fallback;
   - auto-*apply* the classified object preset (with undo, a Settings switch, and never
     over a saved recipe);
   - a progression reel ordered by **capture night**, cumulative (the existing reel orders
     by stack time).
   *(The noise-delta picture shipped as v0.479.0.)*
3. **Open observer issues:** #878 (above), #880 (the Seestar's on-device mosaic output
   ingested as targets, and failing every reprocess), #903 (prevention by cover semantics
   still open; the existing damage now has a one-off repair, v0.479.3).

## Standing frontier (unchanged until a finding says otherwise)

- **Priority 1 is the editor, and it is not "well-hardened".** Judge Auto/editor on a
  tiled mosaic at the owner's scale (`--mosaic --editor --big`), never the 6-frame field.
- **Mosaic-scale and walk-away behaviour is the open frontier.** The single-field engine
  core (`seestack/stack`, `seestack/calibrate`) has passed twenty clean sweeps and is
  closed to re-sweeps until a new bug is found there.
- **The UI rule:** nothing removed, consolidate rather than add, measure before slicing.
  Current tallest pages and their baselines: `docs/PROCESS-NOTES.md`, "DOGFOOD BASELINE".
- **A beginner feature on a regular cadence** from "Features that serve real workflows".

## How the owner gets builds now

He deploys with `sudo scripts/deploy.sh` from the **`stable`** branch (advanced by
`.github/workflows/stable.yml` to the newest `main` commit ≥ 3 days old with green CI) or
from a release tag (`.github/workflows/release-tags.yml`). So a fix reaches him days after
it merges, not minutes — ship the follow-up to your own change *before* that soak ends.
