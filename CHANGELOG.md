# What's new

Plain-language notes for each released milestone on the way to AstroStack 1.0.
The plan is in [`docs/ROADMAP-1.0.md`](docs/ROADMAP-1.0.md).

## 0.512.4 — Tidier updates

**Updates keep only the newest 3 backups.** Each update still backs up your data
before it starts the new version. Once the new version is running, older update
backups beyond the newest 3 are removed. Only the update's own backups are
touched, never your pictures or subs.

## 0.512.3 — Shorter notes

**Notes** on the Target page and the Dashboard now sit under the target's name and
show as one-line headlines. Press **Show more** to read one. Problems and
warnings still show in full.

## 0.512.2 — Simpler pages, faster drizzle

- **Editor:** your picture comes first and stays on screen while you scroll the
  controls. The explanation cards (what the object is, framing, "How's my stack?",
  the progress reel) are folded into one **About this picture** section under the
  editor.
- **Stack page:** **Start stacking**, the time and memory estimate, and the progress
  bar are at the top. When a stack finishes, **Open in editor** takes you straight to
  it.
- **Target page:** **Edit** is the one main button once a target has a picture.
  *Re-run QC + Solve* and *History* are under **More**.
- **Drizzle** does about a third less work per sub on its single thread, for exactly
  the same picture. Big drizzled targets finish sooner.
- **Full-size downloads** you have already made stay ready after an update that
  doesn't change how pictures are drawn. Before, every update threw them away and the
  next download of a big mosaic took minutes again.

## 0.512.1 — Moon & Sun, and faster pages

- **Moon & Sun:**
  - a Moon that isn't full (gibbous, with dark maria) now lines up properly; it used to
    come out soft or doubled;
  - drizzled pictures no longer pick up a faint coloured mesh when the brightness
    flickers between frames (thin cloud, auto-exposure);
  - stacks that aren't drizzled are a touch sharper.
- **Faster pages:**
  - the app now compresses what it sends your browser, so a big target's page loads
    about ten times less data;
  - a target's Planning tab only loads when you open it, which took most of the
    8–18 seconds the Target page needed to open.

## 0.512.0 — Milestone 1 (in progress): foundations

- **"Create a report for Claude".** Settings → Updates & upkeep → *App updates* now
  has a button that runs a set of read-only checks on your library and your NAS and
  gives you one file to send to Claude. The file holds numbers only: no location,
  file names or addresses. These checks decide how the picture-quality work in the
  next milestones gets built.
- **Seestar.**
  - AstroStack can now find your scope from inside Docker: it checks the home network
    your browser reached it on.
  - Scope addresses must be on your home network.
  - The connection survives the scope going offline (0.511.7).
- **Safer.**
  - The ASTAP setting can only run ASTAP (0.511.6).
  - The app answers only on home-network names, so a web page can't drive it through
    your browser.
  - A failed update leaves the old version running (0.511.13).
  - The app boots even on a full disk (0.511.9).
  - A damaged settings file is kept rather than silently reset (0.511.12).
- **Updates arrive by milestone.** The Update button now installs finished, released
  milestones only, instead of whatever passed its tests three days earlier.
