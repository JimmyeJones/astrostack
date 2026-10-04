# Current focus — AstroStack

*Last edited 2026-10-04 (Builder) — item 1 said editor re-audits come back clean, and one did not: v0.492.33.
Corrected here rather than left, because the next run reads this page first. **The Scout rewrites this page**
whenever the front of the queue changes; it stays short (≤ 60 lines) and dated. Live rules are in `AGENTS.md`;
the backlog is `docs/IMPROVEMENTS.md`. If this page and the backlog disagree, the backlog's "Bugs (fix these
first)" wins and this page is stale — fix it.*

## Front of the queue

0. **"Bugs (fix these first)" still holds no ungated work.** Its last ungated entry shipped as v0.492.32
   (`nightplan._have_phrase` / `TonightPick.field_fulls`). What is left is **two gated LEADs and the ⚪
   notes** — gated on owner data, on an unmeasured cost, or stood down with numbers (enumerated in
   `docs/PROCESS-NOTES.md`); one ⚪ is new on 2026-10-04 (`classify_target`'s galaxy/nebula `confidence` is
   pinned to 1.0 by its own gates — filed, not fixed, because nothing reads it). **Do not blind-flip a gated
   threshold or re-litigate a stand-down that carries numbers.** Grep `docs/SHIPPED.md` before building — the
   backlog has repeatedly carried shipped items.

1. **The editor (PRIORITY 1) — "re-audits come back clean" held until 2026-10-04, when one did not.** Judge
   Auto/editor on a tiled mosaic at the owner's scale (`--mosaic --editor --big`); a "What Auto did" trim
   above ~15 % of the canvas is a bug. **v0.492.33**: the preset chip called all three bundled star-only
   samples a *galaxy* at proxy step 1 and a star cluster at step 2, `classify_target`'s opening footprint
   being a fixed 7×7 in **proxy** pixels while `starmask.star_mask` next door had always scaled its own.
   **Reuse the instrument that found it** — the two bundled mosaic samples "differ in scale alone", so asking
   both the same question and diffing the answers tests any claim that should not depend on canvas size
   (lead filed under Infra).

2. **Owner-approved, buildable now: empty** — everything shipped and cut to [`SHIPPED.md`](SHIPPED.md).
3. **Open observer issues — all four verified, filed, blocked on an owner click/reading, none on code**
   (re-triaged 2026-10-03 Scout; no new issue since 2026-09-25): #878 (reconcile shipped v0.482.1/.2 — closes
   on a reading that shows the 11 pairs gone; its 2026-10-02 comment is evidence, not a new ask), #880 (both
   live halves shipped v0.483.1/.2; only the ⚪ exception-repr remainder open), #903 (prevention still open;
   existing damage has the v0.479.3 repair), #1015 (repo half shipped v0.488.2; the rest is out of this repo).

## Standing frontier (unchanged until a finding says otherwise)

- **Mosaic-scale and walk-away behaviour is the open frontier**, not the single-field engine core.
- **Rotation state.** (1) preview↔export parity on a mosaic canvas — **swept CLEAN 2026-10-02 (Scout)**: the
  one-click Auto recipe renders proxy↔export within |Δ|≤0.0004/channel at proxy step 4, all divergence entering
  at `tone.stretch`'s documented resolution dependence, every pixel-scaled op still routed through `scaled_px`.
  (2) mosaic/walk-away divergence — a threshold taken from a whole-target or *peak* number that is really
  per-panel — swept 2026-10-03 (Scout); it yielded the Tonight-planner bug, **shipped v0.492.32**, and the
  engine stacking side was otherwise clean. (3) ASTAP/ffmpeg filesystem side effects and (4) the webapp routers
  were swept 2026-09-30/2026-10-01. Details for all four in `docs/PROCESS-NOTES.md`; don't re-run (1), (3) or
  (4) before a finding says to. **A fifth question is now open and unswept: does a measurement change when only
  the canvas does?** (item 1).
- **The single-field core is re-opened only narrowly** (a pixel-unit threshold tested on an eighth-size
  fixture; swept across `stack`/`calibrate`/`edit`/`render`/`qc` 2026-09-28 — CLEAN). Do **not** re-sweep
  `seestack/stack` or `seestack/calibrate` until a new bug is found there (AGENTS.md).
- **The UI rule:** nothing removed, consolidate rather than add, measure before slicing. Tallest pages and
  baselines: `docs/PROCESS-NOTES.md`, "DOGFOOD BASELINE".
- **A beginner feature on a regular cadence**, but the section is empty and the obvious ones are shipped
  (annotation overlay, share caption, print sizes, framing/mosaic advice, moon notes, "bring my pictures up
  to date") — **do not manufacture a marginal one (§4)**; grep `SHIPPED.md` before proposing another.

## How the owner gets builds now

He deploys with `sudo scripts/deploy.sh` from the **`stable`** branch (advanced by `.github/workflows/stable.yml`
to the newest `main` commit ≥ 3 days old with green CI) or from a release tag. So a fix reaches him days after it
merges — ship the follow-up to your own change *before* that soak ends.
