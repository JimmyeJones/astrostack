# Seestack / AstroStack

A beginner-friendly astrophotography stacker for the **ZWO Seestar** smart
telescope — an alternative to DeepSkyStacker built to handle 10,000+ raw subs of
a single target without falling over.

Point it at a folder, drop your Seestar data in, and it sorts the frames by
target, throws out the bad ones, works out where each one points, stacks them,
and hands you a finished picture. You don't have to know what any of that means
to use it — the app explains the jargon as you go, and there's a
[glossary page](#a-quick-tour) built in.

---

## Which version do I want?

| | **AstroStack Web** | **Seestack desktop** |
|---|---|---|
| Runs on | TrueNAS, or any machine with Docker | Windows |
| You use it from | Any browser on your network — phone, laptop, tablet | The machine it's installed on |
| Good for | Leaving it running so it processes new subs on its own | Sitting down at one PC to process by hand |
| Setup | One-time, below | `pip install`, further down |

**If you have a NAS, or you want the hands-free version, use AstroStack Web.**
That's the one this guide walks through, and it's what most people want.

Both share exactly the same processing engine, so the pictures come out the
same either way.

---

# Getting started (AstroStack Web)

This walks through the whole thing from nothing. It takes about 20 minutes, most
of which is the computer doing the work while you wait.

## What you need

- **A machine that stays on** — a TrueNAS box, a mini PC, a Raspberry Pi 5, an
  old laptop. It needs Docker.
- **Somewhere to put the data.** Astrophotography subs are big; a night can be
  5–20 GB. Point this at a real disk with room to grow, not a USB stick.
- **A few GB of RAM.** 8 GB is comfortable. Big mosaics like more.
- **Your Seestar's files**, which you'll copy over in step 6.

You do **not** need to install Python, a plate solver, a star catalogue, or any
astronomy software. The build downloads all of that for you.

## 1. Make a folder for your data

On TrueNAS, create a dataset — for example `tank/astro`. Anywhere else, just
make a directory, e.g. `/srv/astro`.

Everything the app owns lives inside that one folder, so it's also the only
thing you need to back up.

## 2. Get the code

```bash
git clone https://github.com/JimmyeJones/astrostack.git
cd astrostack
```

## 3. Tell it where your data lives

From inside the `astrostack` folder you just cloned, create a file called `.env`
containing your path from step 1:

```bash
echo 'ASTRO_DATA=/mnt/tank/astro' > .env
```

Change `/mnt/tank/astro` to your actual path. This lives outside the code on
purpose, so updating the app later can never overwrite it.

**Check it before you continue** — a typo here is the single most common way to
get confused later:

```bash
docker compose --env-file .env -f docker/docker-compose.yml config | grep /data
```

That should print your path. If it doesn't, fix `.env` before going on.

## 4. Build and start it

From the same folder:

```bash
docker compose --env-file .env -f docker/docker-compose.yml up -d --build
```

**The first build takes a while** — usually 10–20 minutes. It's downloading
ASTAP (the plate solver, which works out where each photo points) and its star
catalogue, a few hundred megabytes in total. Later rebuilds reuse that and take
about a minute.

Grab a coffee. When it finishes you'll get your prompt back.

## 5. Open it

In a browser on the same network:

```
http://<your-machine's-ip>:8000
```

You should see the Dashboard. If you do, the hard part is over.

## 6. Try it before you trust it

On the Dashboard there's a card offering to **load a sample image**. Take it.

It builds a small fake target out of thin air and runs it through the whole
chain — ingest, quality check, plate solve, stack — in under a minute. It's the
fastest way to confirm everything works and to see what the app actually does,
without waiting on a night of real data. You can delete it afterwards with one
click.

## 7. Add your own subs

Copy your Seestar's target folders into the `incoming/` folder inside your
dataset. Copy the **whole folder**, don't rearrange the contents.

The Seestar names them in a particular way and the app relies on it:

| Folder the Seestar makes | What's in it |
|---|---|
| `NGC 7000_sub/` | **The raw subs.** This is the one that matters — it's what gets stacked. |
| `NGC 7000_mosaic_sub/` | Raw subs for a mosaic. Also stacked. |
| `NGC 7000/` | The Seestar's own on-device stack. Kept, but not re-stacked. |
| `*_video/`, `*_photo/` | Video and single shots. Not deep-sky subs. |

Within about 30 seconds of the copy finishing, the app notices the new files and
starts working. It deliberately waits until a file has stopped changing before
reading it, so copying over Wi-Fi or SMB can't give it a half-written frame.

Watch it happen on the **Jobs** page.

## 8. Turn on hands-free mode

Go to **Settings**. The steps that run automatically are:

| Setting | What it does |
|---|---|
| `watcher_enabled` | Notices new files arriving |
| `auto_ingest` | Files them under the right target |
| `auto_qc` | Measures each frame's quality |
| `auto_solve` | Works out where each frame points |
| `auto_stack` | **Stacks the target once there's enough** |

The first four are on out of the box. **Check `auto_stack` yourself** — new
installs get it on, but if your settings file was created by an older version it
keeps whatever it had, and the app won't flip a switch you might have turned off
deliberately.

With all five on, the whole thing is genuinely hands-off: shoot, copy the
folder over, come back to a finished picture.

---

## A quick tour

Once you have something stacked:

- **Library** — your targets, with how much total exposure each has
- **Gallery** — every picture you've made, with the settings that made it
- **Editor** — stretch, colour, noise, sharpening, all non-destructive
- **Tonight** — what's worth shooting this evening from where you are
- **Sky Map** — your own images placed on the real sky, where they actually are
- **Glossary** — plain-language explanations of every term the app uses

If a word on any page doesn't mean anything to you, the Glossary almost
certainly covers it.

## Where your files go

```
<your dataset>/
  incoming/   ← you drop Seestar folders here
  library/    ← organised targets and finished stacks
  state/      ← settings and the job database
```

Your original subs in `incoming/` are **never modified, moved or deleted** by
the app. It reads them and writes everything it makes into `library/`.

## Updating later

```bash
cd astrostack
git pull
docker compose --env-file .env -f docker/docker-compose.yml up -d --build
```

Your data and settings are untouched — they live in your dataset, not in the
code. Don't add `--no-cache`: it forces the whole ASTAP download to happen
again for no benefit.

## If something goes wrong

**The page won't load.** Check the container is up with `docker ps` — you want
`astrostack` listed as `healthy`. If it isn't, `docker logs astrostack` will say
why.

**It started, but the library is empty and my targets are gone.** Almost always
a wrong path in `.env`. The app is set up to *refuse* to start rather than
quietly create an empty folder somewhere, so check the startup logs — they name
the path it was given.

**Nothing happens when I copy files in.** Give it 30 seconds — it waits for
files to stop changing. After that, check the Jobs page. Note that only one job
runs at a time, so if a long job is already going, yours is queued behind it.

**Frames are being rejected.** That's usually correct — clouds, satellite
trails, bad tracking. The Target page shows the reason for each one.

**Stacking runs out of memory.** Lower `ASTROSTACK_CPU_WORKERS` in
`docker/docker-compose.yml` and restart. Large mosaics are the usual culprit.

## Keeping it private

The app has no password by default, which is fine on a home network. If you want
one, set it on the **Settings** page — after that every page and the API ask for
it. Don't put this on the open internet either way.

---

# Seestack desktop (Windows)

The original PySide6 desktop app. Same engine, no Docker, no NAS.

**Requirements:** Windows 10/11, Python 3.12,
[ASTAP](https://www.hnsky.org/astap.htm) installed locally, and optionally an
NVIDIA GPU with CUDA 12.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .[gui]
seestack
```

Add `pip install -e .[gpu]` for GPU acceleration.

---

# For developers

```bash
# backend (engine + web API; no Qt needed)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,web]"
uvicorn webapp.main:app --reload --port 8000

# frontend, in a second terminal — proxies /api to :8000
cd frontend && npm install && npm run dev
```

Running the tests, the dogfood pass, and the conventions this repo is built on
are documented in [AGENTS.md](AGENTS.md). Deployment detail, the REST API and
every configuration key are in [docs/webapp.md](docs/webapp.md). The design
history is in [PLAN.md](PLAN.md).

## Layout

```
seestack/
  io/      FITS loading, debayer, project SQLite
  qc/      Per-frame quality metrics
  solve/   ASTAP plate-solving wrapper
  align/   Frame alignment / reproject
  bg/      Background flattening
  stack/   Streaming, memory-mapped accumulators
  edit/    Non-destructive editor ops (stretch, colour, detail, noise)
  post/    Stretch, color cal, export
  gui/     PySide6 application
  render/  headless debayer / autostretch / thumbnails (no Qt)
  core/    GPU/CPU shim, cache manager, job runner
  data/    bundled offline data: sky catalogs + the beginner glossary
webapp/    FastAPI web service: job manager, folder watcher, REST API, SPA
frontend/  React + Vite + TypeScript web UI (built into webapp/static)
docker/    Dockerfile + docker-compose.yml for TrueNAS / Docker
docs/      webapp.md (deployment + API), IMPROVEMENTS.md (backlog)
```
