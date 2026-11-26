# Audit: image editor and one-click Auto-process (v0.511.5)

Scratch folder (scripts, PNGs, logs): `/tmp/claude-0/-home-user-astrostack/898c11c2-2328-5559-a5d0-f0f505498eb1/scratchpad/audit/editor/` — called `$S` below.

All test data is synthetic linear OSC (Moffat stars with colour, extended object, LP gradient, reprojection-correlated noise, sensor saturation), built by `$S/scenes.py`. Auto was built with the real `build_auto_recipe_for_run`, previews with `render_run_display_array`, exports with `_render_recipe_fullres`. Timings are single-threaded on a machine shared with other auditors, so treat them as upper-ish bounds.

## 1. Verdict

- Auto produces a **screen stretch, not a finished picture**: sky at 47–55/255 with 15–26 levels of luminance grain (26–39 per channel), blown white cores, and three quarters of medium-bright stars clipped to colourless white.
- On a **nebula-filling frame** (the owner's main mosaic subject) Auto's colour is wrong: true sky comes out teal, stars cyan, and the red emission is washed to pink.
- On a **nebula-filled mosaic**, the coverage-leveling pass Auto always prepends *creates* visible panel seams on a stack that had none.
- Two existing knobs alone (`target_bg` 0.10, `highlights` 0.6) fix most of the galaxy case; the nebula case needs a linked stretch, which the app does not have.
- The plumbing is sound: NaN handling, preview/export agreement, memory and op robustness all held up. The backlog says "nothing ungated is open" while the picture-quality items sit gated on owner data that synthetic tests answer.

## 2. Biggest meaningful improvements (ranked)

### 1. Re-aim Auto's stretch at a finished picture — S, low risk, NEW specifics (generic "Weak default result" idea is open at IMPROVEMENTS.md ~L1115)
- **What:** lower Auto's sky target (now clamped 0.14–0.24, `seestack/edit/presets.py:1279`) to about 0.10–0.12, and turn "Hold back highlights" on by default (now `0.0`, `presets.py:1271`). Stop sharpening "clean" stacks at the pixel scale before the grain is dealt with.
- **Why:** STF puts black at median − 2σ (`seestack/render/thumbnail.py:1229`) and sky at 20 % grey, so *every* stack, however deep, is stretched until its noise is the same visible size. Auto's "clean vs noisy" measurement is in linear units, so a deep stack gets no denoise and a sharpen on top.
- **Evidence (galaxy, `$S/variants.py`):**

| Variant | Sky (of 255) | Sky grain L / per-channel (levels) | Star peaks pure white | Blown-white area |
|---|---|---|---|---|
| A Auto as shipped | 48 | 15.6 / 25.6 | 72 % | 0.120 % |
| B same recipe, `target_bg` 0.10 + `highlights` 0.6 | 24 | 8.8 / 14.3 | 0 % | 0.000 % |
| C = B + denoise 0.6, no sharpen | 24 | 7.4 / 11.8 | 0 % | 0.000 % |
| R reference (linked stretch) | 27 | 8.3 / 13.2 | 1 % | 0.001 % |

- Pictures: `$S/galaxyz_ABCR_grid.png` (A top-left, B top-right, C bottom-left, R bottom-right), `$S/galaxy_auto_export.png`, `$S/cluster_auto_export.png`, `$S/cluster_export_crop.png`.
- Caveat: a default change on the Auto path is a behaviour change on a live install (§9); it needs the owner's nod or an opt-in "Auto v2" look.

### 2. Linked, sky-anchored stretch and background for nebula frames — M, medium risk, NEW
- **What:** add a linked STF mode (one shadow point and one midtone for R, G and B, anchored on the darkest sky tiles rather than each channel's frame median), ideally colour-preserving above the sky. Have Auto use it when the frame is nebula-filled, and anchor the gradient fit the same way.
- **Why:** star colour calibration makes stars white, then two later steps undo it. `background.final_gradient` (`match_channels`) treats the frame's nebula as sky and drives true sky negative in red; per-channel STF then pins each channel's *median* (which is nebula) to the same grey.
- **Evidence (`$S/decompose.py` on the nebula scene):** dark-sky red goes 0.0044 → −0.0043 after gradient removal; after the stretch the true sky is (0.061, 0.113, 0.097) and star R/G falls from 1.086 to 0.906. In the export the darkest true sky is RGB 15/22/25 and mean star colour (0.87, 0.96, 0.97). The reference gives sky 23/26/26 and vivid red nebula.
- Pictures: `$S/nebulaz_AvsR_centre.png` (Auto left, reference right), `$S/nebula_auto_export.png`.

### 3. Fix mosaic leveling on nebula-filled canvases — M–L, medium risk, NEW
- **What:** estimate panel steps from pixel differences across coverage seams (both sides share the same sky), or have Auto skip `background.level_coverage` when the canvas is mostly nebula.
- **Why:** the pass reads each coverage level's "sky" from pixels that are faint nebula, so each level gets a different over-subtraction.
- **Evidence (`$S/mos_small.py`, 2250×1500, 12 panels, zero injected offsets):** median seam step in red rises from 0.3e-4 to 2.5e-4 after leveling. Seams are plainly visible in `$S/mos_clean_leveling_top_vs_none_bottom.png` (top = Auto's default, bottom = leveling disabled, seamless). Also visible in `$S/mosaic2_auto_export.png` (6000×4000).
- I could not establish what real residual panel offsets look like, so I make no claim about how well the pass works on its intended case.

### 4. Depth-aware noise reduction on mosaics — M, low risk, NEW (not found in backlog)
- **What:** scale denoise strength by the coverage map (roughly 1/√frames), so thin panels get more and deep panels less.
- **Why:** Auto applies one strength to the whole canvas; a 40-sub panel next to 300-sub panels stays conspicuously gritty. Visible bottom-centre in `$S/mos_clean_leveling_top_vs_none_bottom.png`.

### 5. Single-field preview is quarter resolution — S, low risk, NEW
- **What:** raise `PROXY_MAX_PX` (1500, `seestack/edit/proxy.py:23`) to at least 1920, or area-average instead of striding.
- **Why:** an S30 frame is 1920 px on its long side, so every ordinary stack is strided by 2 and previewed at 960×540, point-sampled. Auto's sharpen radius of 1.0 px becomes 0.5 px, so the owner cannot see what it does. Confirmed: preview shape `(540, 960, 3)`.

### 6. Export speed at mosaic size — M, low risk, partly filed (preview responsiveness is; export time is not)
- **Evidence (`$S/mosaic2.log`, 6000×4000, Auto recipe):** 173 s, peak RSS 2.7 GB. `background.final_gradient` 37 s, `background.level_coverage` 34.5 s, `detail.chroma_denoise` 20.7 s, `detail.denoise` 20.5 s, sharpen 12.4 s, colour calibration 11.7 s. The two background ops fit smooth fields and could be fitted on the proxy and upsampled.
- Preview: 8.5 s cold, 1.5 s repeat, 2.6 s after a saturation tweak on a 1404×903 proxy; about 1.2 s on a single field.

## 3. Defects (ranked)

| # | Title | Severity | Confidence | Where | What the owner sees | Suggested fix | Status |
|---|---|---|---|---|---|---|---|
| 1 | Auto output is a screen stretch: grey, gritty sky | high | CONFIRMED (table above; 4 scenes, sky 39–55/255, grain 15–26 levels) | `presets.py:1279`, `thumbnail.py:1228-1229` | Noisy grey background on every Auto picture, regardless of stack depth | Improvement 1 | NEW specifics |
| 2 | Nebula-filled frame: teal sky, cyan stars, washed red | high | CONFIRMED (`decompose.py`) | `ops/tone.py` `_stretch` → `autostretch` per channel; `bg/final_gradient.py:322` | Hα nebulae look pink on a blue-green sky | Improvement 2 | NEW |
| 3 | Coverage leveling creates panel seams on a nebula-filled mosaic | high | CONFIRMED (seam step 0.3 → 2.5 e-4; visible) | `presets.py:1670`, `bg/coverage_leveling.py:1206` | Rectangular panel outlines on a clean mosaic | Improvement 3 | NEW |
| 4 | Bright cores blow to flat white; highlight protection off in Auto | high | CONFIRMED (blown area 0.120 % → 0 with `highlights` 0.6) | `presets.py:1271` | M31/M42-type cores are white blobs | Default it on | FILED, gated on owner data (IMPROVEMENTS.md ~L3085–3089) |
| 5 | Stars clip to colourless white | medium | CONFIRMED (72 % galaxy, 90 % cluster) | same as 1 | White dots instead of blue/orange stars | Follows from 1; colour-preserving stretch | NEW |
| 6 | "Hold back highlights" tints stars on a nebula frame | medium | CONFIRMED (mean star RGB 0.87/0.96/0.97 → 0.54/0.82/0.77 at 0.6) | `thumbnail.py` `_reanchor_highlights`, per channel | Turning the knob up makes stars green-cyan | Apply the shoulder on luminance / linked | NEW |
| 7 | Auto sharpens "clean" stacks whose stretched grain is as visible as a noisy one | medium | CONFIRMED (cluster: no denoise, sharpen 0.5, grain 18 levels) | `presets.py:1288`, `_NOISE_LO/_NOISE_HI` | Crisp grain | Judge noise after the stretch | NEW |
| 8 | Single-field preview is 960×540 | medium | CONFIRMED | `proxy.py:23`, `proxy_step` | Soft, aliased preview; pixel-scale ops invisible | Improvement 5 | NEW |
| 9 | Deconvolution defaults ring bright stars and mottle the sky | medium | CONFIRMED visually (`$S/galaxy_base_deconv_starreduce.png`, middle) | `ops/detail.py:612` | Dark ring around bright stars | Star-masked / damped RL, or lower default iterations | SHIPPED entries mention ringing; no open item |
| 10 | Uniform denoise leaves thin mosaic panels gritty | medium | CONFIRMED visually | `presets.py` auto denoise | One grainy rectangle in a smooth mosaic | Improvement 4 | NEW |
| 11 | Saturation boosts sky chroma noise | low–medium | CONFIRMED (per-channel grain 1.6× luminance grain) | `ops/tone.py:151` | Coloured speckle in the background | Weight saturation by luminance | NEW |
| 12 | SCNR leaves the sky slightly magenta | low | CONFIRMED (green 2–3 levels under R/B: 49/46/48) | `ops/tone.py:257` | Faint magenta tint | Smaller once sky is darker | FILED, gated |
| 13 | Preview is grainier than the exported file at screen size | low | CONFIRMED (7.0 vs 4.3 levels) | `proxy.py` `build_proxy` strides | Export looks smoother than the preview promised | Area-average the proxy | NEW |
| 14 | Mosaic export takes minutes; background ops dominate | low–medium | CONFIRMED (173 s at 24 MP, contended) | `webapp/pipeline.py` `_render_recipe_fullres` | Long wait per export | Improvement 6 | NEW |

Not a defect, but worth knowing: `level_by_coverage` smooths offsets across coverage levels (`coverage_leveling.py:1336`), so independent per-level offsets are not removed (per-level sky medians still spanned −9.9…+9.8 e-4 after the pass in `$S/mos_lv2.py`). Whether real offsets are smooth in frame count needs the owner's data.

## 4. Checked and found sound

- **NaN / coverage:** all 21 ops preserve the uncovered mask, create no new NaN and fill nothing (`$S/opsweep.py`).
- **Preview vs export at mosaic scale (6000×4000, step 4):** per-channel median difference +0.006 / −0.002 / −0.002, median |diff| 0.014; no op diverged grossly.
- **Pedestal invariance:** Auto gives identical results with sky at 0.03 and with sky zeroed (as the stacker delivers it).
- **Robustness:** no op raised on any scene, in preview or export.
- **Memory:** peak 2.7 GB for a 24 MP canvas (about nine float32 copies); it will scale linearly, so roughly 11 GB at 96 MP — not tested.
- **Star colour calibration** itself is right (star R/G 1.086, B/G 1.000 after the op); later steps spoil it.
- **Star reduction** at defaults is mild and artefact-free.
- **Mosaic trim:** Auto's crop removed about 15 % and left no uncovered pixels.

Not covered: `Editor.tsx` was only skimmed (one 3,100-line component, 43 queries/mutations, 21 ops, 49 parameters; Auto-process is one click from the header). I did not run the browser, the `_auto_edit_process_run` job path, or the taste-profile code.
