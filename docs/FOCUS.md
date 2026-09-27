# Current focus — AstroStack

*Last rewritten 2026-09-27 (front-of-queue item 1 struck by the Builder the same day it
shipped; two of item 2's four struck by the Builder the same evening — v0.482.1/.2 and v0.483.0; item 3's #880
struck the same night — v0.483.1/.2). **The Scout rewrites this page** whenever the front of the
queue changes; it stays short (≤ 60 lines) and dated. Live rules are in `AGENTS.md`;
the backlog is `docs/IMPROVEMENTS.md`. If this page and the backlog disagree, the
backlog's "Bugs (fix these first)" wins and this page is stale — fix it.*

## Front of the queue

1. ~~**"Combine into one deep target" (three bugs)**~~ — **all three shipped 2026-09-27**
   (v0.480.2 the rescan undo, v0.480.3 the dropped notes/tags/preferences/frame columns,
   v0.480.4 the swapped picture). The button is safe to use again; `merge.carry_stack_runs`
   is now the vehicle item 2's mosaic reconciliation can build on.
2. **Owner-approved, buildable now** (answers of 2026-09-25, on `main` via PR #981):
   - ~~reconcile the 11 historical mosaic pairs (#878) through `merge.carry_stack_runs`~~ —
     **offered in the app 2026-09-27 (v0.482.1 + v0.482.2).** The pairs were invisible to library
     hygiene because the base target was looked up by a *computed* safe name the hash-suffixed base
     does not have (v0.482.1, a bug found while costing this); with that fixed, each twin that carries
     pictures is offered **Combine into `<T> (mosaic)`** on the Library's cleanup card, carrying runs,
     recipes, notes, tags and preferences (v0.482.2). **What is left is the owner clicking it** — this
     closes on the next observer reading that shows the pairs gone, not on more code;
   - ~~`astroalign` for the WCS-free registration fallback~~ — **shipped 2026-09-27 in two halves.**
     v0.481.0 built the similarity transform inside the bootstrap rescue, closing a silent mis-placement bug
     on the way (phase correlation never declines, so a night of alt-az field rotation was being propagated as
     a confident wrong answer). v0.482.0 took it stacker-wide for a **single field**: `star_match_unsolved`
     (off by default) lets `run_stack` place its accepted-but-unsolved subs, so a target where 40 of 300
     solved can stack all of them. **What is left is the mosaic**, where an unsolved sub has no pointing and so
     nothing says which panel to offer it — a design question, not a slice (shape to cost is in the backlog
     entry). The owner is a heavy mosaic user, so it is worth real thought;
   - auto-*apply* the classified object preset (with undo, a Settings switch, and never
     over a saved recipe);
   - ~~a progression reel ordered by **capture night**, cumulative~~ — **shipped 2026-09-27
     (v0.483.0), for the price of one stack.** The `save_progress` clip's pass-1 snapshots now land on
     capture-night boundaries instead of every Nth frame, so one ordinary stack yields "night 1;
     nights 1–2; …", each frame captioned with its date range and sub count. Off by default, no new
     option. **What is left of the entry** is the reel-*from-history* half: reusing existing runs whose
     sub set matches a cumulative step, so a target gets the reel without being re-stacked at all.
   *(The noise-delta picture shipped as v0.479.0.)*
   *(After the two strikes above, the only unbuilt item here is the auto-apply preset — and two
   Builders have now costed it and landed on "the honest next step is a measurement, not a build";
   read the ⚠ notes on its backlog entry before picking it up.)*
3. **Open observer issues:** #878 (above — the app now offers the fix), ~~#880~~ (**its two live halves shipped
   2026-09-27**: the accepted-but-unreadable frames that failed 61 batch reprocesses over seven weeks are set
   aside by `qc/runner.reconcile_unreadable_frames`, v0.483.1, and the batch summary that would not say *why*
   now groups its failures by cause, v0.483.2. What is left of #880 is (a) alone — the exception repr *stored*
   as a reject reason, which no surface shows; it is storage hygiene, filed as ⚪ and explicitly **not** a
   PRIORITY 3 item), #903 (prevention by cover semantics still open; the existing damage now has a one-off
   repair, v0.479.3).

## Standing frontier (unchanged until a finding says otherwise)

- **Priority 1 is the editor, and it is not "well-hardened".** Judge Auto/editor on a
  tiled mosaic at the owner's scale (`--mosaic --editor --big`), never the 6-frame field.
- **Mosaic-scale and walk-away behaviour is the open frontier.** The single-field engine
  core (`seestack/stack`, `seestack/calibrate`) has passed twenty clean sweeps and is
  closed to re-sweeps until a new bug is found there.
  **↳ One has been (Builder 2026-09-27, observer [#989](https://github.com/JimmyeJones/astrostack/issues/989),
  fixed as v0.480.6): `stack/output.py::_write_fits` wrote every single-field drizzle-off
  master with no WCS at all.** The Scout decides what that reopens; the Builder's finding
  is narrower than "the core is unsafe" and is about *fixtures*, not about the combine
  maths — every stacker fixture set `wcs_json` from the **WCS-only**
  `synth.make_synth_wcs_text`, i.e. the one header shape that could not exhibit it. The
  realistic whole-header fixture now exists (`synth.make_synth_frame_header_text`), and
  the cheap sweep it enables is "what else does this engine write out, and what does it
  put in the file?" rather than another pass over the combine path.
- **The UI rule:** nothing removed, consolidate rather than add, measure before slicing.
  Current tallest pages and their baselines: `docs/PROCESS-NOTES.md`, "DOGFOOD BASELINE".
- **A beginner feature on a regular cadence** from "Features that serve real workflows".

## How the owner gets builds now

He deploys with `sudo scripts/deploy.sh` from the **`stable`** branch (advanced by
`.github/workflows/stable.yml` to the newest `main` commit ≥ 3 days old with green CI) or
from a release tag (`.github/workflows/release-tags.yml`). So a fix reaches him days after
it merges, not minutes — ship the follow-up to your own change *before* that soak ends.
