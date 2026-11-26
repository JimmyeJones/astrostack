# AstroStack performance audit at the owner's scale (main @ v0.511.5, 2026-11-26)

Box: 4 vCPU Intel Xeon @ 2.1 GHz (1 thread/core), 15 GB RAM, local SSD, no GPU. `OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=1`
on every stack run, as the app runs it. Other auditors were running for the first half of the session (load avg 6–17),
so **every wall-clock figure below was re-measured once the box was quiet (load ≤3)**, and contended numbers are used only as
CPU-seconds. Scripts and raw outputs: `/tmp/claude-0/-home-user-astrostack/898c11c2-2328-5559-a5d0-f0f505498eb1/scratchpad/audit/perf/`
(`run_one.py`, `batch*.out`, `stages.py`, `driz_add.py`, `api3.out`, `watch_scan.out`, `edit_time.out`).

## 1. Verdict

1. **Everyday use is fine at his scale. Re-stacking is not.** Every restack starts from scratch, and the default κ-σ stack reads and fully reprocesses every sub **twice** (`stacker.py:4091` pass 1, `:4166` pass 2). On this box that is 2.23 s a sub, so **≈22 h for his 35,894-sub target and ≈68 h to restack all ~110 k subs**. On the faster box that measured 0.78 s a sub on 2026-10-12, it is 7.8 h / 24 h.
2. **Drizzle ×1.5 with rejection is bounded by one serial thread**, so it barely gains from more cores: **≈51 h on one field and ≈80–90 h (3.5 days) on a large mosaic canvas** for the 35,894-sub target.
3. **Incremental stacking does not exist.** The `aligned_cache_path` column is never written, and "Bring my pictures up to date" restacks everything. Adding one night of 500 subs to the 35 k master costs the full ~22 h instead of ~10 minutes. This is the single largest win available.
4. **Memory:** the OOM guard's estimate is **1.5–1.7× low on mosaics** (the canvas share it charges), and **3.2× low on the whole process** once ~1.1 GB of 4-worker transients is counted. The post-stack phases (levelling, gradient, saving) reach the same peak as stacking and are not charged. An edited full-res export of an 8000×6000 mosaic takes **199 s on one thread and 4.85 GB**, and nothing guards it.
5. **API:** the polled endpoints are cheap (≤20 ms). The slow ones are page loads on the biggest target: the Target page pulls **20.6 MB of JSON in 7.6 s with no gzip**, and `rejection-outlook` takes **9 s cold** (1 s warm). Boot is ~1 s, but every restart re-fires a whole-library pipeline job.

## 2. Time budget (per sub; totals for 5,477 / 35,894 / 110,000 subs)

Wall = this box with 4 workers (the app's `cpu_workers` default = cores). Totals are wall time on this box. "Oct box" = the
0.78 s/sub container `scripts/measure_drizzle_cost.py` was run on; I re-ran that exact script's frames here and got 2.23 s/sub,
and v0.502.26's code (`git archive`, oldest in the clone) gives 2.04 s/sub on the same frames. **So the 2.9× gap is the
hardware, not a code regression** (≤10 %, within noise). His NAS CPU is unknown: read the two columns as a range.

| Stage | CPU-s/sub (1 thread) | wall s/sub @4 | 5,477 | 35,894 | 110,000 | Method / caveat |
|---|---|---|---|---|---|---|
| Scan, first ingest | ~0.002 local header read | – | <1 min | ~1 min | ~4 min | `load_header` 1.8 ms. Over NFS, add one RTT-bound header read per sub (est. 5–20 ms) → 110 k ≈ 10–40 min |
| Scan, no-op rescan (every pipeline job) | 0.2 ms | – | – | – | **27 s wall / 23 s CPU** for 114,381 files | Measured. 2.5 M `lstat` from `os.path.realpath` ×2 per file (`ingest.py:144/369`). Slower over NFS |
| Watcher poll (every 300 s) | – | – | – | – | **10–12 s CPU** per poll | Measured, 114 k stats. Holds the GIL for that long each poll. NFS: est. 30–120 s |
| QC (`compute_for_db_row`) | 0.25 | ~0.07 | 6 min | 0.7 h | 2.1 h | Measured, ProcessPool |
| Plate solve (ASTAP) | **est.** 1–3 per rung | **est.** 0.3–0.8 | 0.5–1.2 h | 3–8 h | 9–24 h | Not installed. From code: 1 scratch copy + 1 ASTAP run per sub, up to 3 rungs × 60 s timeout on failure, failures re-offered **every scan** |
| Stack: κ-σ default (2 passes, hot-pixel + bg flatten) | **8.9** (4.2/pass) | **2.23** (Oct box 0.78) | **3.4 h** (1.2) | **22 h** (7.8) | **68 h** (24) | Measured slope at 12→24 subs, 3.7 cores busy |
| Stack: one pass (min/max or no clip) | 4.7 | ~1.2 | 1.8 h | 12 h | 37 h | Contended CPU-s; ≈ half of κ-σ |
| Stack: mosaic κ-σ (5×2, 3467×4545 canvas) | ~9 | ~2.3 plus ~56 s fixed per run | ≈3.5 h | ≈23 h | – | Fixed per run: levelling 9 s, gradient 13 s, save 34 s. ≈3 min at 8000×6000 |
| Stack: drizzle ×1.5 + reject, one field | 10–12 | **5.13** (Oct box 5.68) | **7.8 h** | **51 h** | 157 h | Measured slope 6→12 subs, quiet box |
| Stack: drizzle ×1.5 + reject, big mosaic | serial add_frame 7.6–9 s/sub (2 passes) | **≈8–9** | ≈13 h | **≈80–90 h** | – | `driz_add.py`: serial `add_frame` per pass 2.0/2.7 s (2880×1620 out) → 3.65/4.0 s (6818×5206) → 4.05/4.86 s (12000×9000) |
| Auto (proxy + `auto_recipe`), 8000×6000 master | – | 0.5 + 1.3 s | – | – | – | Measured |
| Editor preview render (1334×1000 proxy) | 6.6 | ~7–19 s wall here | – | – | – | Measured; the wall time was I/O-noisy |
| Full-res PNG, unedited, 8000×6000 | 20.7 | 20.8 s, 1.96 GB, 42.6 MB | – | – | – | Measured |
| Full-res PNG, **edited** (Auto recipe), 8000×6000 | **198** (single thread) | **199 s, 4.85 GB peak, 110 MB** | – | – | – | Measured. Spread over ops: gradient 49 s, coverage levelling 37 s, denoise 30 s, chroma denoise 25 s, colour calibration 18 s, curves 12 s, sharpen 10 s (profile at 4000 px out) |

**Top 5 functions by time, one stack sub** (cProfile of `align_one`, 3 subs, 14.2 s total):
1. `scipy.ndimage.rank_filter` (hot-pixel 3×3 median, ×3 channels): 2.9 s
2. `ndarray.partition` (full-frame medians in hot-pixel/bg): 2.0 s
3. `ndimage.zoom` (background-model upsample): 1.6 s
4. astropy `s2p` + `_all_pix2world` (full-grid `pixel_to_pixel` in reproject): 2.4 s together
5. `ndimage.geometric_transform` / `map_coordinates`: 0.9 s

Stage split for one pass, single thread: debayer 0.25, **hot pixels 1.27, background flatten 1.72, reproject 1.12** = 4.15 s. Every one of these is recomputed identically in pass 2 and on every restack.
GIL probe (`gil.py`): each of these releases the GIL 70–100 % of the time, so the threads really do scale (3.7 of 4 cores busy).

**Caching / repetition:**
- `FrameRow.aligned_cache_path` (`project.py:105/283`) is never written or read anywhere. It is dead schema.
- With `copy_to_cache` off, nothing per-sub is cached. Each κ-σ restack reads every 4 MB raw twice; that is ~290 GB of NAS reads for the 35 k target.
- I/O is not the bottleneck: 2 × 4 MB per 2.2 s per worker is under 15 MB/s. The cost is CPU.

**Incremental stacking: possible, not implemented.**
- `WeightedSumAccumulator` (Σw·x, Σw) and `WelfordAccumulator` (n, mean, M2) are both additive, and a new frame's κ-σ test only needs the existing mean/σ.
- With N_old = 35,894, adding 500 frames moves the mean/σ by about 1.4 %. That makes "clip the new frames against the stored mean/σ, then add them to the stored sums" a negligible approximation.
- Min/max rejection is not additive (a top/bottom-k buffer would have to be persisted, which is feasible but large). Drizzle is additive too: `out_img`/`out_wht` plus the squares for the stats pass.

## 3. Biggest improvements (ranked by hours saved)

### I-1. Incremental "add new subs to the master" (NEW). Saves ~20 h per nightly update of the 35 k target
- **Measurement:** today's update costs N_total × 2.23 s (22.2 h here). Incrementally it costs N_new × 1.2 s: 500 subs ≈ 10 min, which is 130× less. Across 105 targets, his "bring my pictures up to date" falls from ~68 h to the new subs only.
- **Design:**
  - After a κ-σ or weighted-mean stack, persist a sidecar run artefact `<run>_accum.npz` (or FITS) holding the pre-post-processing state: Σw·x[3], Σw[3], Welford n/mean/M2, the frame coverage, the canvas WCS, the exact frame-id set, and the options/calibration hash.
  - On restack, if the hash matches, the canvas is unchanged (same reference and union; a mosaic that grows a new panel falls back to a full stack), and the old frame set ⊂ the new accepted set, then run **one** pass over the new frames only: clip against the stored mean/σ, add to the sums, update Welford.
  - Then rerun the cheap post steps (levelling, gradient, colour, save).
  - A frame un-accepted since the last run falls back to a full stack. That is simplest; subtracting it is possible later.
- **Disk:** 12 floats/px ≈ 100 MB for a single field and ≈ 2.3 GB for an 8000×6000 mosaic. It must go in `targets/…/output`, never in `incoming/`.
- **Size L. Risk M:** results differ from a full restack at the 1e-3 level, so a test should pin the bound against a full stack, and the UI should say "added 500 subs" with a "rebuild from scratch" button.
- Off by default, or on for unattended updates only with owner sign-off. It is a new on-disk artefact (additive; §9-safe).

### I-2. κ-σ pass 1 on a stratified sample when N is large (NEW). Saves ~45 % of every big plain stack (≈10 h on the 35 k target)
- **Measurement:** pass 1 is exactly half the per-sub cost (4.2 + 4.2 CPU-s). Mean/σ estimated from ~300 samples per pixel have a σ error of about 4 %, which is irrelevant to a κ = 3 clip.
- **Design:** when the accepted count is above a threshold (e.g. 600), pass 1 consumes every k-th frame **per pointing group / panel** (`pointings.py` already groups them), so each panel keeps ≥ 300 samples. Thin panels use all their frames. Pass 2 is unchanged.
- **Size M. Risk M:** this is the hot path, so it needs a parity test (clip mask agreement ≥ 99.x %) on a mosaic with one deep and one thin panel. Per AGENTS it would need care, and arguably owner sign-off, as a default change.

### I-3. Drizzle: take the serial consumer off the critical path (partly NEW). Saves ≈25–50 h on a drizzled 35 k target
- **Measurement:** `DrizzleStacker.add_frame` runs on one thread and costs 2.0–2.7 s per sub per pass on a single field, and 3.6–4.9 s on a mosaic canvas. Of that:
  - `_build_pixmap` (full-grid `pixel_to_pixel`, float64): 0.7–0.9 s. It is pure per-frame work and could move into the parallel `prepare()` (`stacker.py:~4965`).
  - Three full-canvas `out_wht.copy()`, a full-canvas `>` compare, and `self._count += deposited` (`drizzle_path.py:~340-366`): 0.6–1.5 s per sub on a mosaic canvas, though a sub covers ~1/20 of it. Restrict them to the pixmap's bounding box.
  - `cdrizzle.tdriz`: 1.5 s for 3 channels. Run the 3 channels in 3 threads if `tdriz` releases the GIL (check first). Otherwise this remains the floor.
- **Expected:** serial cost ~4.7 s → ~1.5–2 s per sub on a single field; ~8.5 s → ~2 s on a mosaic.
- **Size M. Risk L–M:** a pure optimisation with bit-identical output. Test it with the existing drizzle parity tests. The `out_wht.copy` overhead was noted in an old audit (`SHIPPED.md:32171`) and never fixed.

### I-4. Cheaper per-sub preprocessing (NEW, idea). 30–50 % of every pass
- Hot-pixel suppression spends 1.27 s running a 3×3 median on three debayered channels plus full-frame medians. Doing it on the raw CFA plane (1 plane, before debayer) and taking the robust statistics on a 1/16 stride (`homog.py` measured a ~10× cheaper median) would cut most of that.
- Background flatten (1.72 s) is dominated by sigma-clipped box statistics and `zoom`. It could run on a 2× decimated frame.
- Reproject (1.12 s) could evaluate `pixel_to_pixel` on a coarse grid and interpolate. A TAN→TAN mapping over one 1080×1920 frame is smooth: the `homog.py` 5×5-control-point homography test is in the scratch dir.
- Each of these changes pixels, so each needs a quality-parity measurement. **Size M each. Risk M** (image quality).

### I-5. Stop re-solving known failures on every scan (FILED, LEAD at `IMPROVEMENTS.md` ~l.390)
- `build_solve_arglist` (`solve/runner.py:~375`) re-offers every `solve_failed:` frame on every pipeline run. Each one can cost up to 3 rungs × `astap_timeout_s` (60 s).
- With even 1 % unsolvable subs (~1,100) that is up to ~14 h of ASTAP **per pipeline job**, and every watcher batch and every restart (D-6) starts one.
- Fix: a per-frame attempt counter (an additive column) with back-off, e.g. retry at most once a week or after the ASTAP/DB settings change. **Size S–M.**

### I-6. gzip the API (NEW). The Target page on the 35 k target goes 20.6 MB → ~1.9 MB
- There is no `GZipMiddleware` (`webapp/main.py`). The JSON compresses to 9 %, and the 929 KB index bundle also ships uncompressed.
- Fix: one line, `app.add_middleware(GZipMiddleware, minimum_size=4096)`. **Size S. Risk L** (check SSE/streaming endpoints are excluded). The win is mainly for phone/Wi-Fi use.

## 4. Defects

| # | Sev | Defect | Evidence | Where | Fix | Status |
|---|---|---|---|---|---|---|
| D-1 | 🟠 | **OOM guard underestimates mosaics** | Drizzle ×1.5 + reject, 5×2 mosaic (out 6818×5200): peak RSS **4.81 GB vs guard 2.84 GB (1.69×)**; the peak is hit in pass 1 *and* in "Removing residual gradient" (4.80 GB). Plain κ-σ mosaic 4545×3467: **2.33 GB vs 0.72 GB**; the canvas share alone is ~1.1 GB (1.5×), peaking in levelling/gradient/saving, which the guard does not charge. ~1.1 GB is 4 workers' `align_one` transients (`_memory_bounded_in_flight` charges 25 MB per in-flight frame; the real working set is ~250 MB per worker). Extrapolated to an 8000×6000 base with drizzle: estimate 8.65 GB, real ≈12–13 GB. With the budget at 0.7 × available RAM, a run the guard passes near the limit can OOM | `stacker.py:246-290` (`_estimate_peak_bytes`), `:293-330`; post phases | Charge post-stack phases and a per-worker working set (~10× the frame buffer), or measure peak per phase in a test at mosaic scale | NEW |
| D-2 | 🟠 | Drizzle's serial consumer does whole-canvas work per sub, so its cost scales with mosaic size and it does not parallelise | `add_frame` per pass: 2.0 s (2880×1620) → 4.05 s (12000×9000); pixmap 0.7–0.9 s serial | `drizzle_path.py:251-366`, `stacker.py:4917-5030` | I-3 | NEW (overhead noted `SHIPPED.md:32171`) |
| D-3 | 🟡 | Edited full-res export/download of a big mosaic: 199 s on one thread, 4.85 GB peak, no memory guard. The cache signature includes `APP_VERSION`, so every update discards every cached render. The whole-library full-size archive renders each pick serially with `write=False` | 8000×6000, Auto recipe, measured | `pipeline.py:2749-2900`, `full_res_png_signature` ~l.3406 | Guard by canvas size; tile or thread the heavy ops; key the cache on a renderer version, not the app version | NEW |
| D-4 | 🟡 | `/rejection-outlook` cold **9.2 s** (17.7 s profiled) on the 35,894-sub target, rebuilt after any frame change (every import or grade); **~1.0 s warm on every Target-page load** (the `frames_fingerprint` `SELECT *` hash). `/stack-estimate` 1.1–1.3 s | `compute_mosaic_canvas` 12.6 s / 33,780 `wcs_from_text` in profile | `webapp/estimate_cache.py:59`, `mosaic.py:301` | Persist per-frame footprints (corners) in the frame row at solve time, so the canvas is a min/max over stored numbers; cheaper fingerprint (`max(rowid)`, `total_changes`, per-row `updated_at`) | FILED (Performance LEAD; shapes a–d shipped, the residue at 35 k is unmeasured there) |
| D-5 | 🟡 | Target/Stack page `api.listFrames` on 35,894 subs: 18 requests, **20.6 MB JSON**, 7.6 s server CPU (this box, under load; 2.4 s per v0.471.1's own measure); not gzipped | `api3.out` | `frontend/src/api/client.ts:3952`; `webapp/main.py` (no gzip) | I-6, and/or trim unused fields (24 fields, 612 B/row) | SHIPPED (paging) / NEW (gzip) |
| D-6 | 🟡 | **Every container restart re-fires a whole-library pipeline job.** `StabilityTracker` starts empty, so on the second poll all 114 k files go "newly stable", and `_on_batch_ready` enqueues scan → QC → solve. Measured no-op rescan: 27 s locally (2.5 M lstat), much longer over NFS, plus D-7's solve retries | Code path traced; scan timed | `webapp/watcher.py:52-110, 272-330` | Seed the tracker from the library's known `(source_path, size, mtime)` at start, so only unknown files count as new | NEW |
| D-7 | 🟡 | Watcher poll stats all 114 k files every 300 s: 10–12 s CPU per poll locally, holding the GIL against API threads; estimated tens of seconds over NFS | `watch_scan.out` | `watcher.py:284`, `ingest.find_fits_files` (glob `**/*` + `is_file` + stat) | `os.scandir` walk with `DirEntry.stat()` (one syscall); skip folders whose mtime is unchanged (directory mtime changes when files are added) | NEW |
| D-8 | 🟡 | `_dedup_key` calls `os.path.realpath` on every stored row and every scanned file, every scan: 229 k realpaths → 2.5 M lstat, 18 s of a 50 s profiled no-op scan | `watch_scan.out` | `seestack/io/ingest.py:144, 369-371` | Cache realpath per directory (resolve the parent once, then join the name); only fall back for symlinked entries | NEW |
| D-9 | 🟢 | `aligned_cache_path` column is dead schema: never written or read, though documented as "stage-2 warped float16 mmap" | grep | `seestack/io/project.py:105, 283` | Leave it (§9), but document it as unused or use it for I-1 | NEW |
| D-10 | 🟢 | Drizzle cost note is box-specific: "×7 a plain sub" was measured on a box where plain was 0.78 s. Here plain is 2.23 s and drizzle 5.13 s (×2.3), because drizzle is serial-bound and plain scales with cores. The ratio does **not** transfer between machines, contrary to the docstring | Measured both | `autodrizzle.py:40-60`, `config.py:283` | Say "serial-bound: ≈5 s/sub regardless of core count" | NEW |
| D-11 | 🟢 | PNG encoded at zlib level 6: on the 8000×6000 unedited render level 6 takes 12.6 s for 42.6 MB, level 1 takes 5.5 s for 51 MB (JPEG q95 0.23 s, 16.6 MB) | `edit_time.out` | `pipeline.py` `img.save(buf, "PNG")`, `thumbnail.py` | `compress_level=1–3` for interactive downloads | NEW |
| D-12 | 🟢 | Frontend: 2 `lazy()` routes; the index chunk is 929 KB (277 KB gz) and mantine 475 KB, served uncompressed (~1.7 MB on first load); Aladin (2.39 MB) is lazy | `webapp/static/assets` | `frontend/src/main.tsx` | Lazy-load the heavy routes (Editor, Jobs, Sky); gzip (I-6) | NEW (minor) |

## 5. Measured and found fine
- **Polled endpoints** with 105 targets / 114 k frame rows: `/api/jobs` (every 2 s) 5–9 ms, `/api/stats` (every 10 s) 6–14 ms warm (167 ms cold), `/api/incoming-lag` 4 ms warm, `/api/jobs/queue-health` 5 ms, `/api/library/summary` 5 ms, `/api/targets` 6 ms / 33 KB, target detail 5 ms, `/api/diagnostics` 3 ms. There is no N+1 problem on the polled paths.
- **Slower but not polled:** `/api/storage` ~1 s (opens 105 DBs); `/api/plan/best-tonight` 1 s cold, 40 ms warm (`registry_cache`); `/api/gallery` 0.25 s / 263 KB. In an earlier contended sweep, `/api/activity-calendar`, `/api/library/missing-files`, `/api/calibration/incoming` and `/api/last-night` took 2–3.5 s cold and <20 ms warm.
- **Boot:** `create_app` 0.7 s, lifespan 0.3 s. The backfill and diagnostics jobs are queued, not run inline.
- **Thread scaling of the plain path:** 3.7 of 4 cores busy; the hot numpy/scipy/wcslib calls release the GIL.
- **Single-field stack memory:** ~1.25 GB total at 4 workers (canvas share tiny). Drizzle single field 1.25 GB vs estimate 0.37 GB, which is the same per-worker transient as D-1.
- **QC:** 0.25 s CPU per sub, parallel. Not a concern.
- **Editor on a big master:** proxy build 0.5 s CPU (decimated 1334×1000), Auto 1.3 s. Unedited full-res PNG 21 s / 2 GB (cached beside the run).
- **Raw I/O:** reading a 4 MB sub from page cache takes 9 ms; network I/O is under 15 MB/s per stack, so CPU dominates.
- **No code regression:** v0.502.26 and v0.511.5 run the same frames at 2.04 vs 2.23 s per sub (within noise).

**Not measured (estimated from code):** ASTAP solve time (not installed), NFS stat/realpath latency, and the owner's CPU speed. Totals scale linearly with per-sub cost, so read the two columns in §2 as a range.
