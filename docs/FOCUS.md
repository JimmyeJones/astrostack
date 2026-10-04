# Current focus — AstroStack

*Last edited 2026-10-04 (Builder — item 0 and the seam paragraph corrected, both named a bug that is now on
`main`, and the `sky_sigma` lead promoted to a verified bug after running the gate its own entry set; the
Scout's own 2026-10-04 text is otherwise untouched). `--mosaic` dogfood and the ASTAP/ffmpeg sweep both CLEAN (records in
`docs/PROCESS-NOTES.md`). **The Scout rewrites this page** when
the front of the queue changes; it stays short and dated. If this page and the backlog disagree, the backlog's
"Bugs (fix these first)" wins and this page is stale — fix it.*

## Front of the queue

0. **"Bugs (fix these first)" holds ONE ungated item — the `sky_sigma` stride bug promoted on 2026-10-04
   (below); everything else in it is a gated LEAD or a ⚪ note.**
   🟠 **The seam finding shipped as v0.492.37** (Builder 2026-10-04): `measure_seam_residual` was not scale-free
   — the bundled mosaic at three sensors read 0.4520 → 0.7075 → 0.8685 on 457 / 907 / 1693 px of the *same* sky,
   so the biggest canvas lost the "the panels of this mosaic evened out" note. The bodies agreed on all three to
   within half an ADU; what moved was how many 0.2–0.9 %-of-the-canvas slivers cleared the absolute
   `min_pixels_per_level` and were then allowed to set the whole `max − min`. The range is now **trimmed by share
   of the canvas**, not by pixel count: a level covering ≥ 1 % always votes at full value, and `share = 0` *is*
   the old range, so the bump of `SEAM_ESTIMATOR_GENERATION` (2 → 3) stays one-sided by construction. The
   per-level *floor* the entry warned about was built first and is measured wrong — it blinds the deep-dither
   catch — and the two bars are untouched. After: 0.0616 / 0.0931 / 0.0000.
   🟡 **#1063 shipped as v0.492.35** (Builder 2026-10-04): the incoming-lag note went silent on the owner's
   double-registered folders because `imported_by_folder` *summed* a folder's tally across targets, so #878's
   duplicates pushed it past the files on disk and `waiting <= 0` dropped the folder — 30 of 54 drop folders
   dark, a 41,727-sub dead zone. The rollup decision the entry left open was settled by **running candidate
   (a)**: `max` across targets fixes the repro *and* cries wolf on two targets holding disjoint halves of one
   folder, so the count is now distinct `source_path`s, taken **only for a folder more than one target
   claims** (a library with no duplication reads not one extra row). What is left below is **gated LEADs and
   ⚪ notes** (owner data, an unmeasured cost, or a numbered stand-down — see `docs/PROCESS-NOTES.md`; the
   2026-10-04 ⚪ is `classify_target`'s `confidence` pinned to 1.0, filed-not-fixed because nothing reads it).
   **Do not blind-flip a gated threshold or re-litigate a numbered stand-down.** Grep `docs/SHIPPED.md`
   before building.

1. **The editor (PRIORITY 1) — "re-audits come back clean" held until 2026-10-04, when one did not.** Judge
   Auto/editor on a tiled mosaic at the owner's scale (`--mosaic --editor --big`); a "What Auto did" trim
   above ~15 % of the canvas is a bug. **v0.492.33**: the preset chip called all three bundled star-only
   samples a *galaxy* at proxy step 1 and a star cluster at step 2, `classify_target`'s opening footprint
   being a fixed 7×7 in **proxy** pixels while `starmask.star_mask` next door had always scaled its own.
   **Reuse the instrument that found it** — the two bundled mosaic samples "differ in scale alone", so asking
   both the same question and diffing the answers tests any claim that should not depend on canvas size
   (lead filed under Infra).

2. **Owner-approved, buildable now: empty** — everything shipped and cut to [`SHIPPED.md`](SHIPPED.md).
3. **Open observer issues — four open (triaged 2026-10-04 Scout; #1063 closed by v0.492.35).** **None carries
   code work.** All four are blocked on an owner click/reading: #878 (reconcile shipped v0.482.1/.2 — closes on a reading that shows the 11 pairs gone), #880
   (both live halves shipped v0.483.1/.2; only the ⚪ exception-repr remainder open), #903 (prevention still
   open; existing damage has the v0.479.3 repair), #1015 (repo half shipped v0.488.2; the clone-pin + token-mint
   remainder is out of this repo — its 2026-10-03 follow-up is the same ask, wider window, not a new one).

## Standing frontier (unchanged until a finding says otherwise)

- **Mosaic-scale and walk-away behaviour is the open frontier**, not the single-field engine core.
- **Rotation state.** (1) preview↔export parity on a mosaic canvas — **swept CLEAN 2026-10-02 (Scout)**: the
  one-click Auto recipe renders proxy↔export within |Δ|≤0.0004/channel at proxy step 4, all divergence entering
  at `tone.stretch`'s documented resolution dependence, every pixel-scaled op still routed through `scaled_px`.
  (2) mosaic/walk-away divergence — a threshold taken from a whole-target or *peak* number that is really
  per-panel — swept 2026-10-03 (Scout); it yielded the Tonight-planner bug, **shipped v0.492.32**, and the
  engine stacking side was otherwise clean. (3) ASTAP/ffmpeg filesystem side effects — **re-swept CLEAN
  2026-10-04 (Scout)**: ASTAP still copies each frame into a `TemporaryDirectory` before `-f` (no `-update`),
  `video/ffmpeg.py` only reads (output over a pipe, never an output path), and the stub-binary readonly-guard
  layers all pass. (4) the webapp routers were swept 2026-10-01. Details in `docs/PROCESS-NOTES.md`; don't
  re-run (1), (3) or (4) before a finding says to. **The fifth question — does a measurement change when only
  the canvas does? — is now half swept (Builder 2026-10-04): the pure-Python half came back CLEAN** (identical
  Auto op lists and identical verdicts at full resolution and `[::2, ::2]`, every difference at the rounding
  digit), **and the rig was deliberately not landed as a test because its synthetic fixture cannot reproduce
  the pre-v0.492.33 defect** — a green tick with no sensitivity. **The `--big` sample-pair half is now SHIPPED as
  v0.492.36** (`scripts/dogfood_scale_pair.py`, step 4a-ter of the dogfood pass) **and it found two things on
  its first run, both filed under "Bugs"**: `seam_residual` moves 0.6998 → 1.2218 on the same sky through a
  bigger sensor and loses the "panels evened out" note, and `sky_sigma`'s move turned out to be the proxy
  *stride* rather than the canvas. **The seam one is now SHIPPED as v0.492.37** (item 0 above):
  the entry's reproduction recipe held (0.4520 → 0.7075 → 0.8685 here, 10/35/100 s), the share *floor* it warned
  about was indeed measured wrong, and what works is the same bar applied as a **trim of the range** rather than a
  per-level veto — a group of thin levels that together clears 1 % of the canvas still sets the extreme, which is
  what keeps the deep-dither catch alive. Neither bar was flipped. **`sky_sigma` is now the front of the queue**: its
  entry's own gate was run and it opened — the ×1.57 step-1→step-3 factor is a property of the reprojection's
  correlation (identical at σ 0.002/0.02/0.2, and 1.00 for white noise), and on the same pixels it flips `noisy`
  and moves Auto's crossfade weight 0.241 → 0.804. **Measure before you correct it**: all three candidate
  corrections are named in the entry and each needs a decision, and the bars must not simply be moved.
  So question 5 is **answered where it could be asked, and one of its two consequences is drained.**
  Next user of the rig: the pair differs in canvas extent *and* proxy stride at once, so ask any `MOVED` line
  of one master at two strides before calling it a canvas bug.
  Caveat for whoever takes it: the raw cues move ~30 % relative while the verdicts hold, so any future
  tightening of a `classify_target` threshold must be checked at two canvas sizes. Details in
  `docs/PROCESS-NOTES.md` and the Infra lead.
- **The single-field core is re-opened only narrowly** (a pixel-unit threshold tested on an eighth-size
  fixture; swept across `stack`/`calibrate`/`edit`/`render`/`qc` 2026-09-28 — CLEAN). Do **not** re-sweep
  `seestack/stack` or `seestack/calibrate` until a new bug is found there (AGENTS.md).
- **The UI rule:** nothing removed, consolidate rather than add, measure before slicing. Tallest pages and
  baselines: `docs/PROCESS-NOTES.md`, "DOGFOOD BASELINE".
- **A beginner feature on a regular cadence**, but the section is empty and the obvious ones are shipped
  (annotation overlay, share caption, print sizes, framing/mosaic advice, moon notes, "bring my pictures up
  to date") — **do not manufacture a marginal one (§4)**; grep `SHIPPED.md` before proposing another.

## How the owner gets builds now

He deploys with `sudo bash scripts/deploy.sh` from the **`stable`** branch (advanced by `.github/workflows/stable.yml`
to the newest `main` commit ≥ 3 days old with green CI) or from a release tag. So a fix reaches him days after it
merges — ship the follow-up to your own change *before* that soak ends.
