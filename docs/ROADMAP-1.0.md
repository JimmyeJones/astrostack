# AstroStack 1.0 — the plan

**Decided 2026-11-26 by the owner:** stop autonomous agent development and get to a fully
functional, excellent **1.0**. This page is the whole plan. It replaces the Builder/Scout
backlog as the source of truth until 1.0 ships. The evidence behind every item is the full
audit in [`docs/audit/2026-11-26/`](audit/2026-11-26/README.md).

**What 1.0 means.** Drop Seestar subs in, and get a picture he is proud of with as few clicks
as possible:
- every stack keeps faint nebulae, has no hot-pixel trails and no colour blotches;
- Auto produces a finished picture, not a screen stretch;
- the app is simple to find your way around;
- adding a night to a big target takes minutes, not a day;
- nothing he relies on is broken.

After 1.0 the app goes into **maintenance mode**: changes happen only when he asks.

## How the work happens

- **No more autonomous runs.** The owner switches off the Builder and Scout routines; the
  observer on the NAS can stay off too. Work happens in deliberate sessions with Claude,
  milestone by milestone.
- **Every milestone ends the same way:**
  1. it ships to `main`, with all tests passing;
  2. the owner updates;
  3. he spends **5–10 minutes** on a short checklist (below);
  4. we fix what he finds before moving on.
- **Release channel.** `stable` stops advancing automatically on a 3-day timer. It moves when a
  milestone is declared ready, so the Update button always gives him a finished milestone, not
  a half-done one.
- **Picture changes are always A/B first.** Each change that alters how pictures look ships
  with a side-by-side on *his own* targets (old vs new). It becomes the default only after he
  picks it.
- **Process paperwork stops.** `AGENTS.md`, the 4,600-line backlog, `SHIPPED.md` and
  `PROCESS-NOTES.md` get archived in one go (M1); this page plus a short `CHANGELOG.md` replace
  them. Tests stay; CI stays.

## Tests on his real data

He will not be asked to run scripts. Everything runs inside the app from **one button**:
**Settings → Maintenance → "Create a report for Claude"**. It produces a single file he
downloads and drops into the chat. The report holds numbers and small picture crops only. It
never includes his location, file paths or account names, and only read-only work is done.
`incoming/` is never written.

The report answers these questions, each of which decides how a 1.0 item gets built:

| # | Test on his data | What it decides |
|---|---|---|
| R1 | **Library inventory:** targets, subs, mosaics and their panel counts, nights, exposure/gain, solve success rate, rejection reasons, duplicate targets (#878), largest canvases | Scale assumptions, duplicate clean-up |
| R2 | **Hardware and timing:** CPU, cores, RAM, disk free; seconds per sub for the last real stacks (from job history); one timed mini-stack of 50 subs | Real stack times; whether drizzle stays automatic |
| R3 | **Sensor colour pattern by temperature** (`sensor_pattern_by_temperature` v2) | The colour-blotch fix: one pattern scaled, or one per temperature range |
| R4 | **Sky falloff / vignetting** (`sky_falloff` v3) | The replacement for the per-frame sky flatten (plane vs a learned flat) |
| R5 | **Hot-pixel census:** a median of ~200 subs across targets, unaligned | Whether a hot-pixel map learned from his lights is reliable |
| R6 | **Registration accuracy:** star size in each stack vs in its subs, for his top 10 targets | Whether plate-solve-only alignment is costing sharpness (adds star refinement or not) |
| R7 | **Mosaic panel layout and offsets** (`mosaic_panel_hints` v2) | The mosaic-levelling fix and the streak guard |
| R8 | **Picture A/B, the acceptance test:** on 5 of his targets (a galaxy, an emission nebula, a big nebula mosaic, a star cluster, a thin/faint target), each candidate pipeline is rendered side by side as small JPEG crops | Which look becomes the 1.0 default; he picks |
| R9 | **Seestar connection:** key accepted? scope found? stays connected over an hour? | The Seestar fixes |

R1–R7 and R9 ship in **M1**. R8 is re-run at the end of M2 and M3 with the new pipeline.

## Milestones

### M1 — Foundations (no visible picture change)
1. ✅ (0.512.0) **"Create a report for Claude" button**, running R1–R7 and R9 as one
   background job. It gets a results view and a download, so the diagnostics no longer
   depend on the NAS observer.
2. **Safety and reliability** (from `backend.md`, `subsystems.md`). Shipped:
   - ✅ the ASTAP path (0.511.6);
   - ✅ password checks off the event loop (0.511.8);
   - ✅ boots on a full disk (0.511.9);
   - ✅ a failed update keeps the old version and the real rollback point (0.511.13);
   - ✅ a damaged config is kept (0.511.12);
   - ✅ no re-solving of failed subs on every import or restart (0.511.14);
   - ✅ Host-header check (0.512.0).

   Still open: deploy-snapshot pruning (needs the owner's OK — it deletes old backups).
   The original list:
   - Host-header check, so a web page can't drive a password-less install;
   - password checks no longer run on the main thread for every request;
   - `deploy.sh` builds before it stops the app, and never overwrites `last-good` with an
     unstarted version;
   - the app boots on a full disk;
   - a damaged `config.json` no longer silently drops the password or turns auto-stack on;
   - deploy snapshots are pruned;
   - stop re-solving the same failed subs on every import, and on every restart.
3. **Seestar** (✅ all three: 0.511.7, 0.512.0):
   - the connection thread survives the scope going offline;
   - discovery falls back to a TCP sweep of the subnet, so it can find his scope from inside
     Docker;
   - validate the `{ip}` parameter.
4. **Housekeeping:**
   - ✅ archive the agent process docs (0.512.0);
   - ✅ `stable` moves only when a milestone is declared ready (0.512.0);
   - ✅ close the four stale observer issues with a note (#878, #880, #903, #1015);
   - ~~remove dead code (`aligned_cache_path`)~~ — kept: it is a database column, and
     migrations are additive only (AGENTS.md §9), so dropping it is not a safe upgrade.

**His check:** update; press the report button and send the file; open the Seestar page and
confirm it finds the scope.

### M2 — The stack keeps everything (picture quality, part 1) — after R3–R7
1. **Replace the per-frame sky flatten** (128 px boxes, which erase 70–94 % of a big nebula)
   with a gentle per-frame model chosen from R4: a plane, or a learned flat. Do one gradient
   removal on the finished stack instead.
2. **Hot-pixel map learned from his own subs**, repaired in the raw Bayer data before debayer.
   The repair code in `calibrate/defects.py` already exists.
3. **The colour-blotch fix:** a sensor pattern learned from his lights, per temperature range
   if R3 says so, and subtracted before debayer.
4. **Frame weighting that actually down-weights moonlit and hazy subs.**
5. **Drizzle:** switch to a Bayer drizzle, or stop auto-drizzling (R2 decides). Today it costs
   ~7× the time for 2.5 % sharper stars.
6. *(If R6 shows a loss)* star-based refinement on top of the plate-solve alignment.

**His check:** look at R8's side-by-sides on his 5 targets and pick old or new.

### M3 — Auto makes a finished picture (picture quality, part 2)
1. **Auto aims at a finished look:**
   - sky ≈ 0.10 instead of 0.14–0.24;
   - "Hold back highlights" on (in tests: grain halved, white-clipped stars 72 % → 0 %).
2. **Correct colour:** a linked, sky-anchored stretch, and stop the gradient step undoing the
   star colour calibration. Fixes the teal sky, cyan stars and washed-out red nebula.
3. **Mosaics:** fix the panel levelling that creates seams on nebula-filled mosaics, and apply
   noise reduction more strongly on thin panels.
4. **Editor preview** at full single-field resolution (today it shows half).
5. **Moon & Sun:**
   - fix the drizzle mesh on flickering frames;
   - fix the partial-phase Moon alignment.

**His check:** R8 again; open 3 of his favourite targets, press Auto, and judge.

### M4 — Fast at his scale
1. **"Add tonight's subs" incremental stacking:** keep the running sums next to each stack,
   and process only new subs. 500 new subs: ~10 min instead of ~8–22 h.
2. **A cheaper first rejection pass** on big targets (about −45 % of a big stack).
3. ✅ (0.512.2: pixmap on the workers, bookkeeping bounded to the sub's footprint;
   `tdriz` holds the GIL, so the kernel itself stays serial) **Drizzle off its single thread**, and bounded to each sub's footprint.
4. **An honest memory guard for mosaics** (today it underestimates by 1.7–3.2×).
5. **Smaller page loads:** gzip on API responses (20 MB → 2 MB on his biggest target), and the
   Target page loads planning data only when that tab opens (9–18 s → ~1 s).
6. A full-res export that doesn't take 200 s and 5 GB, with a cache that survives updates.

**His check:** shoot a night, and see the targets update themselves in minutes.

### M5 — Simple (UX), nothing removed
1. **Navigation down to Home · Pictures · Plan · Tools**, plus header icons for Jobs, Help and
   Settings. Every page stays within two clicks. The pages he never asked for are folded under
   "Extras", not deleted: year recap, universe map, keepsake, life list and similar.
2. ✅ (0.512.2) **Editor:** the picture stays in view while the controls scroll, and the explanation cards
   fold into one "About this picture" tab.
3. ✅ (0.512.2, header) **Target page:** one big picture with "Edit" as the main button. Everything else goes into
   tabs (Frames, Plan, History).
4. ✅ (0.512.2) **Stack form:** "Start" at the top, expert switches folded away, and a finished stack goes
   straight to "Open in editor".
5. **One notice board per page:** the top 1–2 notices as one-line headlines with "Why?"; the
   rest folded.
6. **A clutter check that measures the rendered page**, not the route file. It caps the
   top-level blocks, notices and words above the fold, and requires the main thing to start in
   the top half of the screen.

**His check:** a 10-minute click-through of a written list: find a picture, stack, edit,
export, plan tonight.

### M6 — 1.0 release candidate → 1.0
1. **Full regression pass:** the whole test suite, the dogfood on mosaic/big/editor data, and
   R8 one last time.
2. **One "What's new in 1.0" page in the app**, plus a plain `CHANGELOG.md`.
3. **Rollback rehearsal:** deploy RC, roll back, re-deploy, on his NAS, with a snapshot taken
   first.
4. **Tag `v1.0.0`;** move `stable`.
5. **Maintenance mode** from here on.

## Explicitly *not* in 1.0

Mono/LRGB/narrowband extensions, new planning features, new "fun" pages, Seestar mount
automation beyond what already works (no skyline scan, no free slewing), and anything needing
internet. Deprioritised features stay as they are and keep working.

## Decisions the owner makes along the way

1. **M2/M3:** for each picture change, old or new look (from R8 on his targets).
2. **M4:** keep automatic drizzle or make it a manual "extra sharp" option (R2 numbers).
3. **M5:** which pages go under "Extras" (a short list, proposed by Claude).
4. **M6:** go / no-go for 1.0.
