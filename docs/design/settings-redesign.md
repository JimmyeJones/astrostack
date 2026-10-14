# Settings page redesign — owner-approved spec (2026-10-14)

**Owner's words** (2026-10-12): *"a major overhaul of the settings page may be nice — with visuals… most of
those terms are very confusing and can seem scary to mess with to the average person."* On the first mockup
(2026-10-13): *"I want the expert settings to be dumbed down so that an average user can adjust all settings as
needed. They should be warned of any unexpected consequences of editing things."* Approved with **"Yes go"**
on 2026-10-14.

The approved mockup's full source — every heading, label, help sentence, warning and default — is
[`settings-redesign.mockup.dc.html`](settings-redesign.mockup.dc.html) beside this file (its markup is a design
format, not app code: read it for the **copy and the layout**; build in the app's own React + Mantine). Where
this document and the mockup differ, this document wins.

## Rules (non-negotiable)

- **Nothing is removed** (AGENTS.md §1 UI rule). Every control on today's `frontend/src/routes/Settings.tsx`
  — all 39 labelled settings, the stacking defaults (`default_stack_options` via `StackOptionControl`), and
  every Maintenance card — stays reachable, at most one click away.
- **UI only.** No `Settings` field is renamed, removed or re-typed; no default changes (§9). A control that
  offers fewer choices than its field allows (e.g. cores "All / Half / One") must still *display* any other
  stored value faithfully and keep it until the owner changes it.
- **Old names stay findable.** Each control shows `Was: <old label>` in small text, and the search box matches
  old labels, new titles and help text.
- **Plain words only** on the page: no "QC", "ASTAP", "FOV", "CIDR", "pixfrac", "poll interval" outside the
  `Was:` line.
- Accessible: real `<button>`/`<input>`, `aria-pressed` on switches, ≥ 44 px targets, warnings with
  `role="note"`, colours that differ in lightness as well as hue.

## Page structure (top to bottom)

0. **Header** — "Settings", one reassuring sentence, and **Find a setting** (live filter; matches old names).
1. **How hands-off should AstroStack be?** — three cards that set the steps in (2):
   *Do it all for me* → `watcher_enabled`, `auto_ingest`, `auto_qc`, `auto_solve`, `auto_stack`,
   `auto_edit_on_autostack` all on · *Get them ready — I'll stack* → first four on, last two off · *Hands on* →
   all off. Picking a card is a preview until **Save**, like every other control here. A hand-edited mix shows
   as no card selected ("Custom").
2. **When new photos land in your drop folder** — the six steps as a numbered row (Notice → Sort → Check →
   Place → Stack → Finish), one switch each, mapped in that order to the six fields above. A step after a
   switched-off one is drawn as "Waiting for an earlier step". Under it: the stack-trigger card
   (`auto_stack_min_frames`, `auto_stack_settle_min`) and the two-targets guard (`mixed_pointing_guard`). A
   green line: *"Your raw subs are only ever read — never moved or deleted."*
3. **Leaving out bad frames** — "How picky?" segmented control: *Keep all* (`auto_grade_frames` off) /
   *Gentle* / *Balanced* / *Strict* (`auto_grade_sensitivity` = conservative / balanced / aggressive). An
   illustration of ~12 frame tiles (sharp, cloud, shaken, slightly soft, satellite trail) marks which would be
   **Kept** / **Left out** for the current choice, labelled *Illustration*. Trails switch =
   `keep_streaked_frames`.
4. **Where you observe from** — "Read it from my photos" (the location the app already derives from the
   Seestar's FITS headers — `_resolve_observer`; reuse it, don't add another reader), "Type it in" (`site_lat`,
   `site_lon`, `site_elevation_m`), privacy line, and `min_target_altitude_deg` as a slider driving a small
   horizon drawing whose lit band redraws as it moves.
5. **How pictures are made** — four cards with their current value: outlier removal, drizzle
   (`auto_drizzle` + the stacking default), `auto_crop_border`, `auto_bind_calibration`; then **Show all
   stacking options**, which opens today's full `StackOptionControl` list unchanged.
6. **How hard your NAS works** — memory as a bar (other apps / room AstroStack may use / kept free) over
   `max_stack_memory_gb` (blank = Automatic), and processor cores.
7. **Updates & upkeep** — today's Maintenance cards (App updates, the #903 repair, reprocess, job history),
   unchanged, in one place.
8. **More settings** (open by default; *not* "expert") — every remaining setting as a plain control with a
   consequence warning; see below.

Badges on each card: **Safe to change** (teal), **Changes future pictures** (amber), **Has side effects — read
the note** (lilac). Shape + text, never colour alone.

## "More settings" — every control, its field, and its warning

Each one: a title, one sentence on what it does, the control, and — **the moment its value differs from the
default** — an amber *Heads up* note with the sentence below plus **Back to default (<default>)**. Where the
sentence depends on direction, both are given.

| Title | Control → field | Heads-up when changed |
|---|---|---|
| Where your photos and library live | Standard / Choose other folders → `data_root`, `incoming_dir`, `library_root` | Nothing is moved for you. AstroStack will look in the new folders, so your library will look empty until you move the files there yourself. Your raw subs are never touched. *(Keep the existing `nested_incoming_conflict` refusal.)* |
| Make a working copy of each photo first | switch → `copy_to_cache` | Every sub is copied, so you need about as much free space again as your drop folder holds, and importing a big night takes longer. Only worth it if your drop folder is on a slow or unreliable network share. |
| How much job history to remember | slider 50–2,000 → `job_history_limit` | Up: uses a little more disk; the Jobs page can take a moment longer to open. Down: older job records are forgotten sooner. Pictures aren't affected either way. |
| Wait after copying stops | slider 10 s–5 min → `watch_quiet_period_s` | Down: a photo still being copied over Wi-Fi might be read half-finished and marked bad (re-checkable from the Frames tab). Up: new subs show up a little later. |
| Back-up check for new files | slider 1–30 min → `watch_poll_interval_s` | Down: a little more disk activity, especially with a big drop folder. Up: on a share that doesn't report new files, they can take up to N minutes to appear. |
| Telescope field of view | Read from my photos / Seestar S30 / Seestar S50 → `astap_fov_deg` | If this doesn't match the telescope that took the photos, most frames won't be placed — and unplaced frames aren't stacked. *(Builder: confirm how the solver uses `astap_fov_deg` vs the frame's own `FOCALLEN`/`XPIXSZ` before wiring "Read from my photos"; if the field is already only a fallback, say so in the help line.)* |
| Time allowed per photo | slider 20 s–5 min → `astap_timeout_s` | Up: more faint frames get placed, but a cloudy night can take much longer. Down: quicker, but more faint frames are left out of stacks. |
| Use the telescope's own target as a starting point | switch → `astap_use_solve_hints` | Off: each photo is searched across the whole sky, so placing takes a lot longer. |
| Rescue faint fields | switch → `astap_bootstrap_solve` | On: more of a faint target's photos get used, but importing it takes noticeably longer. |
| Processor cores to use | All / Half / One → `cpu_workers` | Imports and stacks take longer; the NAS stays more responsive for other apps. |
| Memory limit for stacking | Automatic / slider → `max_stack_memory_gb` | Too low: big mosaics may be refused or drizzled smaller. Higher than the NAS really has free: it can run out of memory and other apps (or AstroStack) may be stopped mid-job. |
| Let AstroStack choose satellite-trail removal on hands-off stacks | switch → `auto_reject_on_unattended` | Hands-off stacks may take longer (an extra pass), but trails and hot pixels are cleaned without asking. |
| Show my Seestar's live status | switch → `seestar_enabled` (+ `seestar_poll_interval_s`) | AstroStack looks for the telescope on the home network every few minutes and checks it every few seconds while on. |
| Let AstroStack control the Seestar | switch → `seestar_control_enabled` | It can then start, stop and move the telescope. Leave off unless you use the Live page's buttons — the Seestar app keeps working either way. |
| How to find the Seestar | Search my network / I'll type its address → `seestar_scan_subnet`, `seestar_known_ips`, `seestar_scan_interval_s` | If the telescope's address changes (e.g. after a router restart), AstroStack won't find it until you update it here. *(The address box appears only for the second choice.)* |

Every warning must be **true of the code** — re-read the field's use before shipping its sentence, and change
the sentence (not the behaviour) if it isn't.

## Build order — one slice per Builder run (AGENTS.md §1: one layout slice per run)

1. **More settings** (above) + badges + `Was:` lines + search matching old names. Biggest value: it is what the
   owner asked for in his second message.
2. Sections 1–2: the hands-off cards and the six-step row.
3. Section 3's picky control and frame illustration.
4. Sections 4, 6 and 7 (location + horizon, NAS bar, upkeep grouping).
5. Section 5 (the four picture cards over the existing stacking list).

Each slice: vitest for every warning's show/hide and **Back to default**, a test that every pre-redesign
setting key is still rendered and saved somewhere on the page (guards "nothing removed"), an upgrade test that
an old `config.json` loads and round-trips unchanged, and a `scripts/agent-dogfood.sh` pass with before/after
page heights at 420 px and 1440 px in the commit message.
