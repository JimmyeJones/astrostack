# AstroStack Web

A headless web version of the Seestack engine, built to run on **TrueNAS SCALE**
(or any Docker host). Point it at a dataset, drop your Seestar data in, and it
handles the rest.

## What it does

- **Watches** a folder in your dataset. When new Seestar `.fit` files finish
  arriving, it automatically **ingests** them, runs **QC** metrics, and
  **plate-solves** them — then saves everything for later. Every auto-step is
  toggleable in Settings (and you can enable auto-stacking too).
- **Organises by target.** Each Seestar target sub-folder becomes its own
  project/stack automatically (the existing Library/scanner). Re-scans are
  idempotent.
- **Web UI** to browse targets, preview raw frames (debayered + autostretched),
  sort/accept/reject by quality, configure & run stacking with the full set of
  engine options (advanced ones tucked behind a disclosure), watch live job
  progress, and download results (FITS / TIFF / PNG).
- **Sky Map** — an interactive 3D viewer of the night sky (a built-in
  bright-star backdrop, no external survey needed) with every stacked image
  dropped onto the celestial sphere at its plate-solved position and angular
  size. Where fields overlap, the most recent image is drawn on top. Drag to
  look around, scroll to zoom, click an image to jump to that target.

## How it's built

```
Browser ── React SPA (frontend/, built into webapp/static)
   │  REST + SSE
FastAPI (webapp/) ── single job worker thread ──► seestack engine
   │                     (scan → QC → solve → stack)            │
   └── folder watcher (watchdog + polling + debounce) ──────────┘
        all state lives in the mounted dataset
```

- One **job worker** runs heavy work one job at a time (QC/solve already use all
  cores internally; stacking is memory-heavy). Progress streams to the browser
  over **SSE**; jobs persist to `state/jobs.sqlite` and survive restarts.
- The **watcher** only ingests files that have been size/mtime-stable for a
  quiet period, so half-copied frames arriving over SMB/NFS are never read
  mid-write.

## Dataset layout

Point the container's `/data` volume at a TrueNAS dataset. The app creates:

```
<dataset>/
  incoming/   ← drop your Seestar target folders here
  library/    ← organised per-target projects + stack outputs
  state/      ← config.json + jobs.sqlite
```

## Deploy on TrueNAS SCALE (Custom App)

1. Create a dataset, e.g. `tank/astro`.
2. Build/push the image, or build locally from the repo root:
   ```bash
   docker compose -f docker/docker-compose.yml up -d --build
   ```
3. In `docker/docker-compose.yml`, set the volume to your dataset
   (`/mnt/tank/astro:/data`) and adjust `ASTROSTACK_CPU_WORKERS`.
4. Add it as a TrueNAS SCALE **Custom App** (paste the compose, or use the
   image + the same volume/env/port settings). Expose port **8000**.
5. Browse to `http://<truenas-ip>:8000` and drop a Seestar folder into
   `incoming/`.

### ASTAP (plate solving)

The Docker image **automatically downloads** the ASTAP headless CLI and the
**d05** star database at build time — no manual steps needed. Plate solving
works out of the box for the Seestar's ~1.3° field of view.

If you need a larger star database or want to pin a specific ASTAP version,
mount your own install over `/opt/astap` at runtime (see
[docker/astap/README.md](../docker/astap/README.md)).

## Local development

```bash
# backend (engine + web deps; no PySide6 needed)
pip install -e .[web]
ASTROSTACK_DATA=/tmp/astro astrostack-web      # serves on :8000

# frontend (separate terminal) — proxies /api to :8000
cd frontend && npm install && npm run dev      # serves on :5173
```

Run `cd frontend && npm run build` to bundle the SPA into `webapp/static/`,
after which the backend serves the whole app on a single origin at `:8000`.

## Configuration (`state/config.json`)

Editable from the **Settings** page or directly on disk. Key options:

| Setting | Default | Meaning |
|---|---|---|
| `watcher_enabled` | `true` | Auto-process new files |
| `watch_quiet_period_s` | `30` | Stability window before a file is read |
| `auto_ingest` / `auto_qc` / `auto_solve` | `true` | Auto pipeline steps |
| `auto_stack` | `false` | Also auto-stack each target |
| `copy_to_cache` | `false` | Copy frames locally (use for slow/NAS sources) |
| `astap_path` | `null` | Override ASTAP location (else `$SEESTACK_ASTAP_PATH` → PATH) |
| `cpu_workers` | all cores | Parallelism for QC/solve/stack |

## REST API

Interactive docs at `/docs`. Highlights: `GET /api/targets`,
`GET /api/targets/{safe}/frames`, `GET /api/targets/{safe}/frames/{id}/preview`,
`GET /api/stack/options/schema`, `POST /api/targets/{safe}/stack`,
`GET /api/jobs/{id}/events` (SSE), `POST /api/scan`, `GET/PUT /api/settings`,
`GET /api/health`.
