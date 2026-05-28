# Seestack

A Windows-first astrophotography stacker for the ZWO Seestar smart telescope.
Built as a scalable, beginner-friendly alternative to DeepSkyStacker — designed
to handle 10,000+ raw subs of a single target.

See [PLAN.md](PLAN.md) for the full design.

## Status

Early scaffold (milestone M1). Not yet usable.

## Requirements

- Windows 10/11
- Python 3.12
- [ASTAP](https://www.hnsky.org/astap.htm) installed locally (for plate solving)
- Optional: NVIDIA GPU + CUDA 12 for acceleration

## Install (development)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[dev]
# Optional GPU support:
pip install -e .[gpu]
```

## Run

```powershell
seestack
```

## Layout

```
seestack/
  io/      FITS loading, debayer, project SQLite
  qc/      Per-frame quality metrics
  solve/   ASTAP plate-solving wrapper
  align/   Frame alignment / reproject
  bg/      Background flattening
  stack/   Streaming, memory-mapped accumulators
  post/    Stretch, color cal, export
  gui/     PySide6 application
  core/    GPU/CPU shim, cache manager, job runner
docs/
  glossary.md   beginner-friendly term glossary (linked from the GUI)
```
