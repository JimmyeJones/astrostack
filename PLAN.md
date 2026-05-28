# Seestack

A Windows-first, Python 3.12 astrophotography stacker built as a friendlier, scalable
alternative to DeepSkyStacker, focused on the ZWO Seestar smart telescope. Designed
to handle 10,000+ raw subs of a single target without falling over.

## Goals

- Process 10k+ Seestar `.fit` raw subs in a single project.
- Beat DSS on: scale, mosaic stitching, streak rejection, coverage-aware stacking
  (no bright overlap spots), per-frame quality metrics, and clarity for non-experts.
- Optional NVIDIA GPU acceleration via CuPy, with full CPU parity.
- Batch processing only (no live-stacking).
- Everything in-house: no DSS file import, no cloud services.

## Non-goals (for now)

- Live stacking during capture.
- Mono / LRGB / narrowband workflows (Seestar is OSC).
- Full ccdproc bias/dark/flat calibration (Seestar bakes darks in on-device; flats
  are not practical with its sealed optics).
- One-click installer (run from source via `pip install -e .`).

## Target user

Seestar owner with thousands of subs of a single target who has tried DSS, hit its
limits, and wants something that scales — but is **not** a PixInsight expert. Every
option in the UI needs a plain-language explanation, a sensible default, and a
"Why?" panel. Presets (Conservative / Balanced / Aggressive) cover 95% of cases.

## Tech stack

- **Language:** Python 3.12
- **GUI:** PySide6 (Qt 6)
- **Imaging core:** numpy, scipy, astropy, photutils, ccdproc (light use), astroalign,
  reproject, the STScI `drizzle` package, `astride` for streak detection
- **Plate solver:** ASTAP (external binary, bundled or path-configurable)
- **GPU:** CuPy (optional) via an `xp` shim — `xp = cupy if available else numpy`
- **Project file:** SQLite (one row per frame with all metrics + WCS)
- **Packaging:** `pyproject.toml`, run from source

## The 10k-frame architecture (the core idea)

DSS falls over past a few thousand frames because it tries to keep too much in RAM
and uses an in-memory median for rejection. Seestack is **streaming and out-of-core
from day one**:

- **Memory-mapped accumulators** sized to the output canvas: `sum`, `sum_of_squares`,
  `weight` (coverage map). Each aligned frame streams in, contributes, is freed.
  RAM usage is O(output canvas), not O(frames).
- **Two-pass sigma-clipping:** pass 1 builds running mean/std into the accumulator
  (Welford's algorithm). Pass 2 re-streams frames and only contributes pixels within
  k·σ of the pass-1 mean. Constant RAM, two full reads.
- **Coverage / weight map** divides the final sum: each output pixel = sum / weight,
  not sum / N. This is the fix for "brighter where more frames overlap" — including
  in mosaics. Always on, not a user choice.
- **Drizzle integrates cleanly** — each input contributes to the output independently,
  so it's already a streaming algorithm.

## NAS-aware caching

NAS random reads are 10–100× slower than local SSD and the stacker reads everything
twice. So caching is part of the design:

- **Stage 1 cache (local SSD):** on first ingest, copy raws to a local working folder
  as they're read. Everything downstream reads from local. ~150 GB for 10k Seestar
  subs.
- **Stage 2 cache (aligned float16):** after solve+align, write each warped frame as
  a float16 mmap. Pass-2 sigma-clipping reads these instead of re-warping. ~2× disk,
  big time saving.
- **Cache management panel** in the GUI: show what's cached, size, clear stages
  independently. User-toggleable with a "Disk used / time saved" estimate.

## Pipeline

```
ingest → calibrate (light) → quality-score → plate-solve →
  align/reproject → background-flatten → reject (streaks/clouds) →
  stack (drizzle or weighted mean) → post (final flatten, color cal, stretch)
```

Each frame's per-stage outputs are recorded in the project SQLite so re-stacking
with different rejection thresholds takes seconds, not hours.

## Module layout

```
seestack/
  io/          fits loading, RGGB debayer, project file (SQLite)
  qc/          per-frame metrics: FWHM, star count, sky ADU, eccentricity,
               transparency, streak detection (astride + Hough)
  solve/       ASTAP wrapper, WCS caching
  align/       astroalign fallback, reproject for WCS-based, mosaic grouping
  bg/          per-frame Background2D flatten, final post-stack flatten
  stack/       memory-mapped accumulators, two-pass sigma-clip, drizzle path,
               weighted-mean path, coverage map
  post/        stretch (asinh / STF), photometric color calibration, save
               32-bit FITS + 16-bit TIFF
  gui/         PySide6 — project view, frame table with metrics + thumbnails,
               reject curves, stack progress, before/after preview
  core/        xp shim (numpy / cupy), job runner, progress bus, cache manager
docs/
  glossary.md  every term used in the UI, explained for beginners
PLAN.md        this file
pyproject.toml
README.md
```

## Project SQLite schema (sketch)

One row per frame:

- `id`, `path`, `cached_path`, `aligned_cache_path`
- `timestamp`, `exposure_s`, `gain`, `temperature`
- `wcs_json` (serialized astropy WCS)
- `fwhm_px`, `star_count`, `sky_adu_median`, `eccentricity_median`,
  `transparency_score`
- `streak_detected` (bool), `streak_count`
- `mosaic_panel_id` (nullable)
- `accept` (bool, user-overridable), `reject_reason` (text)

This is what DSS doesn't have, and it's huge: re-stack with different filters
without redoing solve / align.

## UX rules (for the non-expert)

Every option must have:

- A plain-language label ("Reject frames with star trails", not "Enable astride
  streak detection").
- A one-line subtitle.
- An expandable "Why?" panel: what it does, when to enable it, what it costs,
  the default. No jargon without a definition.
- Presets: **Conservative / Balanced / Aggressive / Custom** at the top of every
  panel. Default is Balanced.
- "Explain this number" tooltip on every threshold field.
- Live before/after preview where possible (background flatten, stretch).
- A "Tips" sidebar with context-aware advice driven by the project metrics
  ("47 frames have FWHM > 4px — typical Seestar threshold for rejection is 3.5px").

`docs/glossary.md` is linked from the GUI and covers every term: FWHM, sigma-clipping,
drizzle, WCS, plate-solve, debayer, background gradient, transparency, coverage map.

## Default settings (the "Balanced" preset)

| Stage | Default | Why |
|---|---|---|
| Frame rejection: FWHM | reject worst 20% | adapts to seeing, no fixed pixel threshold |
| Frame rejection: star count | reject if <50% of median | catches clouds simply |
| Frame rejection: streaks | on, medium sensitivity | satellites common, FPs rare |
| Background flatten (per-frame) | on, polynomial degree 2 | removes sky-glow gradient without eating nebulosity |
| Alignment | WCS-based via ASTAP | most robust across targets |
| Stacking | weighted mean + 2-pass sigma-clip (κ=3.0) | scales to 10k frames; median is too slow |
| Drizzle | off by default | only helps with lots of dithered frames |
| Coverage normalization | always on | the "no bright overlap" fix; not a user choice |
| Photometric color calibration | on | sets white balance from real star colors |

## Milestones

### M1 — Scaffold
- Repo layout, `pyproject.toml`, dependencies pinned.
- `xp` numpy/cupy shim with feature detection.
- Project SQLite schema + open/create.
- ASTAP wrapper stub (locate binary, run on a single frame, parse WCS).

### M2 — Ingest + QC + Frame Table GUI
- Load Seestar `.fit` raws (RGGB debayer, header parse).
- Compute per-frame metrics: FWHM, star count, sky ADU, eccentricity, streaks.
- Local SSD cache (Stage 1).
- PySide6 main window with sortable frame table, thumbnails, metric histograms,
  manual accept/reject toggle.
- **Already useful standalone** — browse and triage 10k Seestar frames in a way
  DSS can't.

### M3 — Solve + Align
- ASTAP integration over the full project (parallel, with progress).
- Cache WCS in SQLite.
- WCS-based alignment via `reproject`.
- Sky footprint visualization on a canvas (mosaic grouping falls out for free).
- Aligned float16 cache (Stage 2).

### M4 — Streaming Stacker v1
- Memory-mapped accumulators.
- Weighted-mean stack with coverage map.
- Two-pass sigma-clipping.
- Validate output against DSS on a small set.

### M5 — Background flatten + Streak rejection
- Per-frame `photutils.Background2D` flatten before stacking.
- `astride` streak detector wired into auto-reject.
- "Tips" sidebar surfacing recommendations from the metrics.

### M6 — Drizzle path
- STScI `drizzle` integrated into the streaming accumulator.
- UI option with clear "when to enable this" guidance.

### M7 — GPU shim
- CuPy backend for warp + accumulator hot loops.
- Auto-detect CUDA, fall back to CPU silently.
- "GPU detected: yes/no" indicator in the UI.

### M8 — Mosaic mode
- Group frames by WCS center.
- Output canvas = union of footprints.
- Coverage normalization handles seams automatically (it's already on).

### M9 — Post-processing
- Asinh / STF stretch with live preview.
- Photometric color calibration (Gaia catalog via plate-solve).
- Export 32-bit FITS and 16-bit TIFF.

### M10 — Polish
- Glossary, "Why?" panels everywhere.
- Presets reviewed and tuned.
- Cache management panel.
- README with screenshots.

## Open questions / decisions parked

- Whether to support DSLR / other-camera FITS later (probably yes, after M9).
- Whether to add a true median-style rejection (slow but sometimes wanted) — defer
  unless users ask.
- Whether to bundle ASTAP or require user install — decide at M1.
