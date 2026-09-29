# Current focus — AstroStack

*Last re-cut 2026-09-28 (Scout) — the previous page ran 25 lines over its own budget after a
fortnight of same-day strikes, so this is a fresh cut, not an edit. **The Scout rewrites this page**
whenever the front of the queue changes; it stays short (≤ 60 lines) and dated. Live rules are in
`AGENTS.md`; the backlog is `docs/IMPROVEMENTS.md`. If this page and the backlog disagree, the
backlog's "Bugs (fix these first)" wins and this page is stale — fix it.*

## Front of the queue

1. **The editor (PRIORITY 1).** Judge Auto/editor on a tiled mosaic at the owner's scale
   (`--mosaic --editor --big`), never the 6-frame field. Its bug backlog is drained and re-audits
   come back clean, but AGENTS.md is explicit: **do not believe "well-hardened"** — a "What Auto did"
   trim above ~15 % of the canvas is a bug, not a ragged edge.

2. **Owner-approved, buildable now** (answers of 2026-09-25). All but two of this group have shipped
   (astroalign single-field + mosaic → v0.482.0/v0.484.0; the cumulative-by-night reel → v0.483.0; the
   noise-delta picture → v0.479.0; the 11 mosaic pairs are now *offered* in the Library → v0.482.1/.2).
   **One remainder, plus one that is closed below:**
   - **auto-*apply* the classified object preset** — two Builders have costed it and both landed on
     "the honest next step is a **measurement**, not a build". Read the two ⚠ notes on its backlog
     entry before touching it; the literal build is an image-quality downgrade.
   - ~~**the reel-*from-history* half**~~ — **✅ SHIPPED v0.486.0** (Builder 2026-09-29). A history that
     already nests night-wise is reported and labelled as "night 1; nights 1–2; …"
     (`capture_nights.cumulative_night_steps`, `night_steps` on `/deepening-reel/info`), with `None` for
     every series that cannot be *shown* to nest. **The progression-video entry is now closed** bar one
     shape code cannot reach from history — a target stacked *once* across several nights — filed as a
     sized lead under "Features that serve real workflows".

   - ~~**NEW, owner-requested 2026-09-28: the night-sky theme**~~ — **✅ SHIPPED v0.485.0** (Builder
     2026-09-29). Deep-navy sky + three drifting star layers, `prefers-reduced-motion`/hidden-tab still, a
     per-device switch in Settings → *This device*, and a **plain neutral surround on the editor, Compare and
     the two three.js routes** — `frontend/src/nightsky/surround.ts` is where that decision lives, so a new
     picture-judging route has one line to add. Entry in [`SHIPPED.md`](SHIPPED.md).

3. **Open observer issues (all verified, filed, and awaiting the last mile — no new issue since
   2026-09-25):** #878 (the app now offers the reconcile; closes on a reading that shows the 11 pairs
   gone — a click, not code), #880 (both live halves shipped v0.483.1/.2; only (a), the exception repr
   *stored* as a reject reason, is left — filed ⚪ storage hygiene, deliberately **not** a PRIORITY 3
   item), #903 (prevention by cover semantics still open; existing damage has a one-off repair,
   v0.479.3).

## Standing frontier (unchanged until a finding says otherwise)

- **Mosaic-scale and walk-away behaviour is the open frontier**, not the single-field engine core.
- **The single-field core is re-opened, narrowly.** Two Builder findings (v0.480.6: `output.py`
  wrote a drizzle-off single-field master with no WCS at all; v0.483.3: the star matcher placed
  nothing on a real-Seestar-sized sub) named one class — **a threshold/buffer/limit whose units are
  *pixels*, tested only on a fixture an eighth of the real frame's size.** ↳ **The Scout swept that
  class across `stack`/`calibrate`/`edit`/`render`/`qc` on 2026-09-28 — CLEAN** (details in
  `docs/PROCESS-NOTES.md`): every such threshold is either normalised to the canvas (overlapgain's
  ~400-px fold, coverage-leveling's stride scaling, the editor ops' `proxy_scale`), dominated by a
  fraction term (`max(256, 8 % × n)`), or guarded by an identical-sampling check (noise-ratio,
  noise-delta). ↳ **The sweep that one suggested — "what else does the engine write out, and what does
  it put in the file?" — ran 2026-09-28 and is CLOSED with a finding; do not re-run it.** The FITS
  *writers* are clean; one card's **value** was not — `REJREACH` stamped from `coverage_max`, the
  deepest pixel, which on a mosaic is the corner where panels meet (v0.484.6; the class it generalises
  to is in `docs/PROCESS-NOTES.md`).
- **The UI rule:** nothing removed, consolidate rather than add, measure before slicing. Tallest
  pages and baselines: `docs/PROCESS-NOTES.md`, "DOGFOOD BASELINE".
- **A beginner feature on a regular cadence** from "Features that serve real workflows" — ⚠️ **thinner
  than this line claimed** (Builder, 2026-09-28): what was costed is struck, declined or closed, and
  the reel-*from-history* remainder is largely delivered by v0.480.0. **Scout: re-stock it** — and
  still do not manufacture a marginal one (§4).

## How the owner gets builds now

He deploys with `sudo scripts/deploy.sh` from the **`stable`** branch (advanced by
`.github/workflows/stable.yml` to the newest `main` commit ≥ 3 days old with green CI) or from a
release tag. So a fix reaches him days after it merges — ship the follow-up to your own change
*before* that soak ends.
