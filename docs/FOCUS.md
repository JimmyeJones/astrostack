# Current focus — AstroStack

*Last re-cut 2026-10-02 (Scout) — the previous page ran ~24 lines over its own ≤60-line budget, so this is a
fresh cut, not an edit. **The Scout rewrites this page** whenever the front of the queue changes; it stays short
(≤ 60 lines) and dated. Live rules are in `AGENTS.md`; the backlog is `docs/IMPROVEMENTS.md`. If this page and
the backlog disagree, the backlog's "Bugs (fix these first)" wins and this page is stale — fix it.*

## Front of the queue

0. **"Bugs (fix these first)" holds nothing ungated.** Every open entry there is gated on something only the
   owner's data can supply, or stood down with numbers (the solve-refusal retry-rate lead, the half-range
   calibration charge (c), the #880 storage-hygiene remainder, the weighted-coverage over-crop residual, the
   watcher/exclusion hardening notes, the sky-atlas rotation-sign fallback). The enumerated list lives in
   `docs/PROCESS-NOTES.md` so a run need not re-derive it. **Do not blind-flip a gated threshold or re-litigate
   a stand-down that carries numbers.** Grep `docs/SHIPPED.md` before building — the backlog has repeatedly
   carried items already shipped.

1. **The editor (PRIORITY 1).** Judge Auto/editor on a tiled mosaic at the owner's scale
   (`--mosaic --editor --big`), never the 6-frame field. Its bug backlog is drained and re-audits come back
   clean, but AGENTS.md is explicit: **do not believe "well-hardened"** — a "What Auto did" trim above ~15 %
   of the canvas is a bug, not a ragged edge.

2. **Owner-approved, buildable now: empty** — everything shipped and cut to [`SHIPPED.md`](SHIPPED.md).

3. **Open observer issues — all four verified, filed, and awaiting the last mile (re-triaged 2026-10-02 Scout;
   no new issue since 2026-09-25, none state-changed since 2026-09-29):** #878 (reconcile offered; closes on a
   reading that shows the 11 pairs gone — a click, not code), #880 (both live halves shipped v0.483.1/.2; only
   the exception-repr-stored-as-reject-reason remainder is open, filed ⚪ storage hygiene, deliberately **not**
   a PRIORITY 3 item), #903 (prevention by cover semantics still open; existing damage has the v0.479.3 one-off
   repair), #1015 (repo-side half — version on `/api/health` — shipped v0.488.2; owner left it open to close on
   a reading that confirms the pin; the other half is an Observer-charter change, out of this repo). **Every
   open issue is blocked on an owner click/reading, none on code.**

## Standing frontier (unchanged until a finding says otherwise)

- **Mosaic-scale and walk-away behaviour is the open frontier**, not the single-field engine core.
- **Rotation state.** (1) preview↔export parity on a mosaic canvas — **swept CLEAN 2026-10-02 (Scout)**: the
  full one-click Auto recipe renders proxy↔export with the global sky-anchor within |Δ|≤0.0004/channel at proxy
  step 4; all divergence enters at `tone.stretch` (its documented resolution dependence, within the ≤2 %
  decimation floor), every linear op before it agrees to ~0.0005, and every pixel-scaled op is still routed
  through `scaled_px` (details in `docs/PROCESS-NOTES.md`). **Rotation now advances to (2): mosaic/walk-away
  divergence — any threshold taken from a whole-target or *peak* number that is really per-panel.** (3)
  ASTAP/ffmpeg filesystem side effects and (4) the webapp routers were swept 2026-09-30/2026-10-01 — don't
  re-run (1), (3) or (4) before a finding says to.
- **The single-field core is re-opened only narrowly** (two Builder findings named one class — a pixel-unit
  threshold tested on an eighth-size fixture). That class was swept across `stack`/`calibrate`/`edit`/`render`/
  `qc` on 2026-09-28 — CLEAN (details in `docs/PROCESS-NOTES.md`). Do **not** re-sweep `seestack/stack` or
  `seestack/calibrate` until a new bug is found there (AGENTS.md).
- **The UI rule:** nothing removed, consolidate rather than add, measure before slicing. Tallest pages and
  baselines: `docs/PROCESS-NOTES.md`, "DOGFOOD BASELINE".
- **A beginner feature on a regular cadence**, but the section is empty and the mature app makes obvious
  beginner features scarce (annotation overlay, share caption, print sizes, framing/mosaic advice, moon notes,
  "bring my pictures up to date" all shipped) — **do not manufacture a marginal one (§4)**; grep `SHIPPED.md`
  before proposing another.

## How the owner gets builds now

He deploys with `sudo scripts/deploy.sh` from the **`stable`** branch (advanced by `.github/workflows/stable.yml`
to the newest `main` commit ≥ 3 days old with green CI) or from a release tag. So a fix reaches him days after it
merges — ship the follow-up to your own change *before* that soak ends.
