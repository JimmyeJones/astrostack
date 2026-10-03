# Current focus — AstroStack

*Last edited 2026-10-03 (Scout) — the front of the queue changed: a new ungated verified bug is now top of
"Bugs". **The Scout rewrites this page** whenever the front of the queue changes; it stays short (≤ 60 lines) and
dated. Live rules are in `AGENTS.md`; the backlog is `docs/IMPROVEMENTS.md`. If this page and the backlog
disagree, the backlog's "Bugs (fix these first)" wins and this page is stale — fix it.*

## Front of the queue

0. **One ungated verified bug is now top of "Bugs" — the first Builder work there in nine runs.** The Tonight /
   "Worth more time" planner (`GET /api/plan/best-tonight`) speaks a mosaic's *whole-target* total as its depth
   ("you've got 10 h so far" reads identically for a single field and a 12×8); reproduced through the pure
   `nightplan` functions, filed 2026-10-03 (Scout). PRIORITY 3, low severity, S–M — the next surface of the
   per-panel correction (v0.492.31's closing card was the sixth), with the datum (`field_fulls`) already on the row. **Everything else in "Bugs"
   stays gated** on owner data or stood down with numbers (enumerated in `docs/PROCESS-NOTES.md`). **Do not
   blind-flip a gated threshold or re-litigate a stand-down that carries numbers.** Grep `docs/SHIPPED.md` before
   building — the backlog has repeatedly carried shipped items.

1. **The editor (PRIORITY 1).** Judge Auto/editor on a tiled mosaic at the owner's scale
   (`--mosaic --editor --big`), never the 6-frame field. Its bug backlog is drained and re-audits come back
   clean, but AGENTS.md is explicit: **do not believe "well-hardened"** — a "What Auto did" trim above ~15 %
   of the canvas is a bug, not a ragged edge.

2. **Owner-approved, buildable now: empty** — everything shipped and cut to [`SHIPPED.md`](SHIPPED.md).

3. **Open observer issues — all four verified, filed, blocked on an owner click/reading, none on code**
   (re-triaged 2026-10-03 Scout; no new issue since 2026-09-25): #878 (reconcile shipped v0.482.1/.2 — closes on
   a reading that shows the 11 pairs gone; #878's 2026-10-02 Observer comment is evidence, not a new ask), #880
   (both live halves shipped v0.483.1/.2; only the ⚪ exception-repr-as-reject-reason remainder open), #903
   (prevention still open; existing damage has the v0.479.3 one-off repair), #1015 (repo half — version on
   `/api/health` — shipped v0.488.2; the other half is an Observer-charter change, out of this repo).

## Standing frontier (unchanged until a finding says otherwise)

- **Mosaic-scale and walk-away behaviour is the open frontier**, not the single-field engine core.
- **Rotation state.** (1) preview↔export parity on a mosaic canvas — **swept CLEAN 2026-10-02 (Scout)**: the
  full one-click Auto recipe renders proxy↔export with the global sky-anchor within |Δ|≤0.0004/channel at proxy
  step 4; all divergence enters at `tone.stretch` (its documented resolution dependence, within the ≤2 %
  decimation floor), every linear op before it agrees to ~0.0005, and every pixel-scaled op is still routed
  through `scaled_px` (details in `docs/PROCESS-NOTES.md`). **Slot (2): mosaic/walk-away divergence — a threshold
  taken from a whole-target or *peak* number that is really per-panel — swept 2026-10-03 (Scout), yielding the
  Tonight-planner bug now top of "Bugs"; the engine stacking side was otherwise clean** (per-panel handling
  re-confirmed across qc/grading, weighting, coverage/trim, stackhealth, cover-nudge, walk-away holds and
  canvas/memory guards — record in `docs/PROCESS-NOTES.md`). (3) ASTAP/ffmpeg filesystem side effects and (4) the
  webapp routers were swept 2026-09-30/2026-10-01 — don't re-run (1), (3) or (4) before a finding says to.
- **The single-field core is re-opened only narrowly** (two Builder findings named one class — a pixel-unit
  threshold tested on an eighth-size fixture). That class was swept across `stack`/`calibrate`/`edit`/`render`/
  `qc` on 2026-09-28 — CLEAN (details in `docs/PROCESS-NOTES.md`). Do **not** re-sweep `seestack/stack` or
  `seestack/calibrate` until a new bug is found there (AGENTS.md).
- **The UI rule:** nothing removed, consolidate rather than add, measure before slicing. Tallest pages and
  baselines: `docs/PROCESS-NOTES.md`, "DOGFOOD BASELINE".
- **A beginner feature on a regular cadence**, but the section is empty and the obvious ones are shipped
  (annotation overlay, share caption, print sizes, framing/mosaic advice, moon notes, "bring my pictures up to
  date") — **do not manufacture a marginal one (§4)**; grep `SHIPPED.md` before proposing another.

## How the owner gets builds now

He deploys with `sudo scripts/deploy.sh` from the **`stable`** branch (advanced by `.github/workflows/stable.yml`
to the newest `main` commit ≥ 3 days old with green CI) or from a release tag. So a fix reaches him days after it
merges — ship the follow-up to your own change *before* that soak ends.
