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

2. **Owner-approved, buildable now** (answers of 2026-09-25) — **empty; everything shipped and cut to
   [`SHIPPED.md`](SHIPPED.md).** astroalign single-field + mosaic (v0.482.0/v0.484.0), the cumulative-by-night
   reel (v0.483.0) and the reel-from-history + once-stacked-reel offer (v0.486.0/v0.487.0), the noise-delta
   picture (v0.479.0), the night-sky theme (v0.485.0), the 11 mosaic pairs now *offered* in the Library
   (v0.482.1/.2). The one item that turned out not to be a build — auto-*apply* the classified preset — is
   **⚪ CLOSED WITH THE NUMBER** (Builder 2026-09-29): `auto_recipe` already applies the archetype, and the only
   surviving delta costs +3–4 % sky chroma noise, so **do not re-pick it** except with a per-archetype
   data-driven rule.

3. **Open observer issues (all verified, filed, and awaiting the last mile — re-triaged 2026-09-30 Scout, no
   new issue since 2026-09-25):** #878 (the app now offers the reconcile; closes on a reading that shows the 11
   pairs gone — a click, not code), #880 (both live halves shipped v0.483.1/.2; only (a), the exception repr
   *stored* as a reject reason, is left — filed ⚪ storage hygiene, deliberately **not** a PRIORITY 3
   item), #903 (prevention by cover semantics still open; existing damage has a one-off repair,
   v0.479.3), #1015 (observer read a code version the app never ran; its repo-side ask — the version on
   `/api/health` — shipped v0.488.2, and the owner deliberately left it open to close on a reading that
   confirms the pin; the other half is an Observer-charter change, out of this repo). **Nothing newly
   actionable in the inbox this run — every open issue is awaiting an owner click/reading.**

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
- **The ASTAP/ffmpeg filesystem-side-effect rotation slot + the fresh post-v0.480 code (updates, new-subs,
  capture-nights, deepening/noise-delta reels) were swept 2026-09-30 (Scout) — CLEAN**, details in
  `docs/PROCESS-NOTES.md`. A `--mosaic --editor --big` dogfood the same day read clean (Auto trim 7.9 %, cards
  coherent, no overflow/console errors). Don't re-run these before a finding says to.
- **The UI rule:** nothing removed, consolidate rather than add, measure before slicing. Tallest
  pages and baselines: `docs/PROCESS-NOTES.md`, "DOGFOOD BASELINE".
- **A beginner feature on a regular cadence** from "Features that serve real workflows". **Re-stocked
  2026-09-30 (Scout): one buildable entry now sits at the top** — 🌟 **"Bring my pictures up to date"** (re-stack
  only the targets with new light, in one click, by adding a `new_light_only` scope to the hardened
  `reprocess_all` path). It serves the owner's exact stack→result-autonomy cadence (many targets, `auto_stack`
  off) and reuses the #903/#880 auto-edit + failure-summary handling; read its three non-optional constraints
  (§903 flattening, the single-worker queue / import-starvation interaction, §10) and its "settle before
  building" note — the read-only-by-design new-subs card is being reversed, so a Builder may route it to owner
  sign-off. The mature app makes obvious beginner features scarce — the annotation overlay, share caption, print
  sizes, framing/mosaic advice and moon notes are all already shipped — so **do not manufacture a marginal one
  (§4)**; grep `SHIPPED.md` before proposing another.

## How the owner gets builds now

He deploys with `sudo scripts/deploy.sh` from the **`stable`** branch (advanced by
`.github/workflows/stable.yml` to the newest `main` commit ≥ 3 days old with green CI) or from a
release tag. So a fix reaches him days after it merges — ship the follow-up to your own change
*before* that soak ends.
