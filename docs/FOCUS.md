# Current focus — AstroStack

*Last rewritten 2026-09-27 (front-of-queue item 1 struck by the Builder the same day it
shipped). **The Scout rewrites this page** whenever the front of the
queue changes; it stays short (≤ 60 lines) and dated. Live rules are in `AGENTS.md`;
the backlog is `docs/IMPROVEMENTS.md`. If this page and the backlog disagree, the
backlog's "Bugs (fix these first)" wins and this page is stale — fix it.*

## Front of the queue

1. ~~**"Combine into one deep target" (three bugs)**~~ — **all three shipped 2026-09-27**
   (v0.480.2 the rescan undo, v0.480.3 the dropped notes/tags/preferences/frame columns,
   v0.480.4 the swapped picture). The button is safe to use again; `merge.carry_stack_runs`
   is now the vehicle item 2's mosaic reconciliation can build on.
2. **Owner-approved, buildable now** (answers of 2026-09-25, on `main` via PR #981):
   - reconcile the 11 historical mosaic pairs (#878) through `merge.carry_stack_runs` —
     **unblocked now item 1 has shipped**;
   - ~~`astroalign` for the WCS-free registration fallback~~ — **the similarity transform itself shipped
     2026-09-27 as v0.481.0**, inside the bootstrap rescue, and it closed a silent mis-placement bug on the
     way (phase correlation never declines, so a night of alt-az field rotation was being propagated as a
     confident wrong answer). What is left of the entry is the *stacker-wide* half — registering every
     accepted-but-unsolved sub, not just the opt-in rescue's members — now sized M;
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
