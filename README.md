# Seestack / AstroStack

A scalable, beginner-friendly astrophotography stacker for the ZWO Seestar smart
telescope — an alternative to DeepSkyStacker designed to handle 10,000+ raw subs
of a single target.

It ships in two forms that share the same processing engine:

- **Seestack** — the original Windows-first PySide6 desktop app.
- **AstroStack Web** — a headless, containerised web service built for
  **TrueNAS** (or any Docker host): point it at a dataset, drop your Seestar
  data in, and it automatically ingests, runs QC, and plate-solves new frames.
  You then preview raws and run stacking from a sleek web UI.
  **See [docs/webapp.md](docs/webapp.md).**

See [PLAN.md](PLAN.md) for the full design.

## Status

- **AstroStack Web** — complete and tested: auto-pipeline (ingest → QC →
  plate-solve), per-target organisation, web UI for preview/stacking, folder
  watcher, and a Docker image (with ASTAP bundled automatically) for TrueNAS.
- **Seestack** desktop — the original PySide6 app; mature processing engine.

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
  render/  headless debayer / autostretch / thumbnails (no Qt)
  core/    GPU/CPU shim, cache manager, job runner
webapp/    FastAPI web service: job manager, folder watcher, REST API, SPA
frontend/  React + Vite + TypeScript web UI (built into webapp/static)
docker/    Dockerfile + docker-compose.yml for TrueNAS / Docker
docs/
  glossary.md   beginner-friendly term glossary (linked from the GUI)
  webapp.md     AstroStack Web: deployment + usage
```
