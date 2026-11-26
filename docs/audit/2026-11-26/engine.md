# Engine and image-quality audit (stack, bg, qc, debayer), AstroStack v0.511.5

Scratch experiments: `/tmp/claude-0/-home-user-astrostack/898c11c2-2328-5559-a5d0-f0f505498eb1/scratchpad/audit/engine/`
(`sim.py` simulates S30 subs: 3.99"/px, RGGB, camera RGB sensitivity 0.55/1/0.45, shot noise, LP gradient, field rotation and drift,
sensor-fixed hot pixels. Every number below comes from the repo's real functions or a real `run_stack`. Logs are `*.log`.)

## 1. Verdict

1. The stack is numerically sound. Flux is conserved (flux/truth 0.99–1.01 per channel), NaN/coverage handling is correct, R−B registration is 0.08 px, and centre/corner FWHM match. The agents' edge-case work held up.
2. The biggest loss of picture quality is a **default design choice**: the per-frame 128 px mesh sky flatten is a high-pass filter. It keeps only **6–31 %** of any nebula larger than ~20′, digs dark bowls around it, and makes one nebula **differ by up to ~65 % of its peak between overlapping mosaic panels**. That matters because the S30's 2.1° field is used for big targets (NA, Veil, Rosette, M31) and he shoots many mosaics.
3. Without darks, hot pixels are cleaned **after** the bilinear debayer has smeared them. The run still leaves about **70 % of the visible R/B hot-pixel residue**, which shows as coloured walking trails. A raw-domain repair removes ~99 % of it.
4. Colour and sharpness: bilinear debayer gives green-cored, magenta-haloed stars. The automatic drizzle costs ~×7 time and buys only 2.5 % FWHM, because it drizzles already-debayered data. A **Bayer (CFA) drizzle** on the same path gives −10 % FWHM in G and −19 % in R/B, with correct star colour.
5. Frame weighting is a diluted heuristic, not an SNR weight. On mixed moon/no-moon data it wastes 30–75 % of the integration time. The editor's handling of the stack is covered elsewhere; these five points are upstream of it.

## 2. Biggest meaningful improvements (ranked by visible benefit)

### I-1. Replace the per-frame mesh-128 flatten with a per-frame low-order (plane) fit, and leave curvature to one final-stack extraction. Size M–L. NEW.
- **What:** `seestack/bg/per_frame.subtract_background` defaults to photutils `Background2D` with box 128 and filter 3 (`BackgroundOptions`, `StackOptions.background_box_size=128`, `background_flatten=True`). Every sub of every walk-away stack runs it (`align.py:162`). Use `bg/sky_poly.fit_sky_poly(deg=1)` per frame instead (already in the repo, with the same object mask). The per-frame job is to remove the *changing* LP tilt. Any curvature should be removed once, on the deep stack, where the object mask can actually see faint nebulosity (`final_gradient` already builds that mask).
- **Measured** (`neb1.log`, `neb2.log`: 1080×1920 subs, linear LP gradient ±10 %, nebula colour R-heavy, same seeds with and without the nebula):

| nebula | mesh128 (default) kept R/G | mesh256 | plane (deg1) | deg2 |
|---|---|---|---|---|
| σ=120 px (8′) faint | 0.71/0.76 | 0.78/0.71 | **1.00/1.00** | 0.97 |
| σ=300 px (20′) faint | **0.06/0.09** | 0.31/0.35 | **1.00/1.00** | 0.32 |
| σ=300 px bright | 0.31/0.32 | 0.62 | **1.00** | 0.42 |
| σ=300 px off-centre | 0.31/0.30 | 0.54 | **0.95** | 0.60 |
| frame-filling σ=600 px | **0.06/0.07** | – | **1.00** | 0.02 |

  Residual sky gradient (127 px smooth, R): mesh128 rms 1.23 ADU, **plane 0.46 ADU**. The default also leaves a dark bowl of −8 to −16 % of the nebula peak around a large nebula.
- **Mosaic seams** (`seam1.py`): the same nebula, seen by two panels offset half a frame. In the shared sky the panels disagree by **max 35 ADU = 66 % of peak** (σ=150 px) and **63 %** (σ=300 px) with mesh128, against **6 % and 15 %** with a plane fit. No later leveling or gain match can undo a difference in structure, so this is a strong candidate for the nebula seams the editor audit saw.
- **Caveat and gate:** the synthetic gradient is linear, which favours a plane. Without flats, real vignetting is radial and multiplicative. The filed dark-rim entry's `sky_falloff v3` diagnostic measures exactly that, so read it before choosing deg1 vs a radial term. Changing it is a hot-path default change (§9), so ship it **opt-in first** ("Protect large nebulae") and ask the owner to make it the default. Auto-enable it on mosaics with sign-off.

### I-2. Make the automatic drizzle a Bayer (CFA) drizzle. Size M. NEW (only the Moon/Sun path has one, v0.502.0).
- **What:** `drizzle_path.DrizzleStacker.add_frame` receives the bilinear-debayered RGB. Feed each channel only its native photosites, with weight 0 elsewhere (`drizzle` accepts a weight map), and skip the interpolated values.
- **Measured** (`e2.log`, the same 24 subs through real `run_stack`; truth FWHM 2.2 px):
  - default: G 2.75, R/B 3.02/3.04
  - today's auto-drizzle ×1.5 pf0.8: G 2.68, R/B 2.96/2.98 (−2.5 %, for about ×7 the time per sub per the module's own measurement)
  - **CFA ×1.5: 2.42 / 2.41 / 2.41**
  - CFA ×1.0 pf1.0: 2.49 on all three channels
  - Flux conserved in every case.
- **Trade-off:** per-pixel noise is higher (R σ 9.2 vs 4.2 at 24 subs), because bilinear interpolation only *hides* noise by correlating it. Auto-drizzle fires only at ≥200 samples per pixel, where this is fine. The owner already pays the drizzle cost; today he gets almost nothing for it.

### I-3. Learn a hot-pixel map from his own lights and repair it in the raw Bayer domain. Size M. NEW.
- **What:** take the per-CFA-site median of ~50–100 raw subs from **different targets**, so the sky cancels and only sensor defects stay. Flag sites with `calibrate/defects.find_sensor_defects` and repair them with the existing `DefectMap` in `apply_raw`, before debayering. This reuses machinery that today needs a master dark, and he has none: none of his 105 runs uses one. It shares step (1) of the HOLD sensor-pattern entry, but hot pixels do not need that hold.
- **Measured** (`hot2.py`/`hot3.log`: 30 subs, 400 sensor-fixed hot pixels of 150–3000 ADU, 6×4 px drift + 1° rotation, real default walk-away `run_stack`; residual = stack with hot pixels − identical stack without). Count of stack pixels >5σ:
  - suppression off: R 2910 / G 3594 / B 3122
  - **default: R 2025 / G 1015 / B 2259** (max 150–215σ)
  - raw-domain prototype: **R 16 / G 30 / B 65**
- The prototype was not fully star-safe (a G star core moved by up to 34σ), so a map built from the dark-like median is the safe form. In the stack, the walking residue is several frames deep per pixel, so κ-σ cannot reject it.

### I-4. Use a real SNR weight for frame weighting. Size S–M. NEW.
- **What:** weight ∝ (transparency ratio)² / (sky noise²), not a geometric mean of five clipped factors. QC already computes the sky σ (`qc/metrics.estimate_sky` returns it) but does not store it. Add an additive `sky_noise` column.
- **Measured** (`w1.py`, the real `compute_frame_weights`): with half the subs moonlit at 5× sky, the moonlit sub gets weight **0.95** where the optimum (1/var) is **0.20**. Stack noise is +32 % over optimal, which equals **74 % wasted integration time**. At 3× sky: weight 0.96, 31 % wasted. At 10× sky (20 % of subs): 84 % wasted.

### I-5. Use a higher-order reprojection kernel. Size S. NEW.
- `reproject_rgb_windowed(order=1)` is bilinear. With order=3 (scipy spline), stack G FWHM goes **2.75 → 2.60 (−5.5 %)**, R 3.02 → 2.88 (`e2.log`). Siril defaults to Lanczos. Cost: one spline prefilter per channel per sub. Needs NaN-edge care (a prefilter spreads the NaN border; reuse the inset).

### I-6. Measure, then fix, registration precision. Size S (diagnostic) + M. NEW.
- Registration uses only the ASTAP WCS. `subpixel_refine` (translation only) is off by default.
- Simulated solve error vs stack G FWHM (`e1b.log`): perfect 2.75; 0.3 px rms 2.89 (+5 %); 0.6 px **3.23 (+17 %)**, which `subpixel_refine` restores to 2.90.
- The real ASTAP error on S30 subs is unknown (there is no binary here). `stack_runs.stack_fwhm_px` and the frames' `fwhm_px` are already stored, so ship a `diag/` diagnostic that reports the ratio of stack FWHM to median sub FWHM across his runs. Above ~1.1, build star-based affine refinement (astroalign is already a dependency) or turn refine on.

## 3. Defects (ranked)

| # | Title | Sev | Confidence | Where | What the owner sees | Fix | Status |
|---|---|---|---|---|---|---|---|
| 1 | Per-frame mesh-128 flatten removes most of every nebula larger than ~10–20′ and digs a dark bowl around it | **High** | CONFIRMED (6–31 % kept at σ≥300 px; bowl −8…−16 %) | `bg/per_frame.py:76-90,287-345`; `stacker.py:552-556` defaults | Faint NA/Veil/Rosette/M31 outskirts missing; Auto cannot bring back signal the stack subtracted | I-1 | NEW (only the dark rim at sub edges is FILED) |
| 2 | The same flatten makes the same nebula differ between overlapping mosaic panels | **High** (mosaics) | CONFIRMED synthetic: max diff 63–66 % of peak vs 6–15 % for a plane | same | Seams and tile steps inside nebulosity on mosaics that leveling cannot remove | I-1 | NEW |
| 3 | `luminance` flatten mode subtracts the luma background shape **unscaled** from R, G and B, so weak channels go negative inside a nebula. The app's own `bg_advice` hint recommends this mode for big emission nebulae | **Med-High** | CONFIRMED: large faint nebula kept R/G/B = 0.20 / −0.02 / **−0.45** (`neb1`); 0.40 / −0.06 (`neb2`) | `bg/per_frame.py:192-240` (comment at :92 says "scaled by per-channel level"; the code doesn't scale); `bg_advice.py` | Following the app's advice turns the nebula a saturated red with blue/green holes | Fit a per-channel scale on sky pixels before subtracting, or retire the hint until I-1 lands | NEW |
| 4 | Hot/cold-pixel suppression runs after the bilinear debayer: 30–38 % of an R/B defect's energy (13–25 % G) survives as a 3×3 blob | **High** (no darks) | CONFIRMED: single-frame `hot1.py`; stack `hot3.log`: R/B >5σ residue 2025/2259 px vs 2910/3122 unsuppressed vs 16/65 in the raw domain | `bg/hot_pixels.py:99-158`, called at `stack/align.py:158` | Coloured specks and walking trails in every dark-less stack, worst in single fields | I-3 | NEW |
| 5 | Automatic drizzle (on by default, `Settings.auto_drizzle=True`) drizzles debayered data: about ×7 time for −2.5 % FWHM | Med | CONFIRMED (`e2.log`) | `stack/drizzle_path.py:251+`, `stack/autodrizzle.py` | Days of stacking on deep targets for no visible gain | I-2 | NEW |
| 6 | Plain bilinear debayer: star cores ~10 % green, halos 22–43 % magenta; R/B FWHM +7–11 % over G | Med | CONFIRMED (`demo1.py`: FWHM 2.2 → core R/G 0.90, halo 1.22; FWHM 1.8 → 0.87 / 1.38). Malvar–He–Cutler tested and rejected: negative halos, worse colour | `io/fits_loader.py:233` | Faintly green stars with magenta rims after stretch | I-2 at depth; at low depth, a superpixel or colour-aware option | NEW |
| 7 | Quality weights are diluted: geometric mean with neutral factors, each clipped at 1.0, sky factor square-rooted and including the ADU pedestal | Med | CONFIRMED (`w1.py`: 0.95 vs 0.20 optimal at 5× sky) | `stack/weighting.py:141-215` | Moonlit or hazy nights add noise instead of depth | I-4 | NEW |
| 8 | Bilinear reprojection (order=1) softens the stack | Low-Med | CONFIRMED (−5.5 % FWHM with order 3) | `stack/align.py:248-306` | Slightly softer stars and detail | I-5 | NEW |
| 9 | Registration is WCS-only, with `subpixel_refine` off and no rotation/distortion refinement | Med? | SUSPECTED (synthetic sensitivity only; real ASTAP error unmeasured) | `align.py:87`, `StackOptions.subpixel_refine=False` | Fatter stars than the subs, worst on multi-night alt-az data | I-6 diagnostic first | NEW |
| 10 | κ-σ pass 2 re-loads, re-debayers, re-flattens and re-reprojects every sub; there is no aligned-frame cache | Low (time, not pixels) | READ (`stacker.py` `_pass` runs twice) | `stacker.py` ~3911/3984 | A 35,894-sub target takes twice the wall-clock; drizzle+reject pays it again | Cache per-sub aligned windows when disk allows, or a streaming one-pass robust estimator | NEW |
| 11 | Sky σ is computed in QC and thrown away | Low | READ (`qc/metrics.estimate_sky` returns `std`; there is no `FrameRow` column) | `qc/metrics.py:111`, `io/project.py:277` | Blocks I-4 | Additive schema column | NEW |

(Already filed, not re-derived: the fixed sensor colour pattern, ⏸ on `sensor_pattern_by_temperature v2`; the dark rim from the per-frame flatten at sub edges, ⏸ on `sky_falloff v3`. I-1 likely fixes the rim too, since it is the same mesh's edge behaviour; a plane has no half-box edge lag.)

## 4. Checked and found sound
- **Default walk-away options:** `StackOptions` defaults + `auto_reject` + `quality_weighted` + `auto_drizzle` posture + `unattended`, via `_stack_target(auto=True)` (`webapp/pipeline.py` ~5420-5540, `walkaway.py`). `default_stack_options` is empty by default, so the per-frame flatten (per_channel, box 128), hot-pixel σ5, κ3 and WCS bilinear reprojection all run on his install.
- **Photometry:** flux conserved to ±1 % per channel on the default, drizzle, CFA-drizzle and order-3 paths. Centre and corner FWHM identical, so there is no field-dependent misregistration on synthetic data. R−B centroid offset 0.08–0.13 px.
- **Rejection:** `WelfordAccumulator` (NaN-aware, n<2 → keep-all) and `_kappa_sigma_keep_mask` (NaN mean/σ widening). The `kappa_min_frames` maths is correct (lone-outlier z-max (n−1)/√n), and `auto_reject` switches to min/max below it.
- **Debayer:** CFA phase handling for the four patterns, zero-fill edges, integer overflow guard.
- **Reprojection:** windowed bbox and 3 px edge inset; `pixel_to_pixel` honours SIP when present.
- **Drizzle:** `disable_ctx=True` keeps memory bounded; memory guard and scale step-down. Mosaic photometric and quality medians are per panel.
- **Not swept:** `calibrate/` beyond `defects.py` (he uses no masters), `solve/` internals, `render/`, `post/color_cal` (off by default; colour is the editor's job and the editor audit covers it).
