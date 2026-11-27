# What's new

Plain-language notes for each released milestone on the way to AstroStack 1.0.
The plan is in [`docs/ROADMAP-1.0.md`](docs/ROADMAP-1.0.md).

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
