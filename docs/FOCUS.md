# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-03)

**One ungated bug is open:** the Scout 2026-11-03 entry in Bugs — a macOS `._*.fit` sidecar in `incoming/` is
reported as an unreadable sub that is "still waiting", and a `.recycle/` / `.Trash-*/` folder becomes a target.
Part (a), the `._` skip in all three walkers, is buildable now (S–M); part (b), the hidden-folder skip, waits on
one-sitting item 19. Otherwise a Builder should dogfood (`--mosaic --editor`) and file what it finds. The owner's ⭐
colour-pattern entry is on HOLD for his per-temperature numbers; the dark ring waits on the S30's measured vignette.
Recently closed: a one-target stack after a Combine shows its deeper picture (v0.505.9); "It's back" names the deepest
returning target per part (v0.505.8); Compare's same-object pair (v0.505.7). Older closures are in the archived run
log and `SHIPPED.md`.

**Gated, do not start:** the un-located-panel entry (second in Bugs) waits on the owner's hint-shape answer; the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-02).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (3), 2026-11-03
→ next sweep is (4).** Each (3) sweep must find a *new* angle — the list of angles already run is in the
`Sweep (3)` entries of `docs/PROCESS-NOTES.md` (grep `sweep (3)`).

## Run log (newest first)

*2026-11-03 (Scout, branch `claude/exciting-wozniak-bnak6b`) — **QA rotation sweep (3), new angle: junk a NAS share or desktop leaves in `incoming/` (`._*.fit`, `.recycle/`, `.Trash-*/`) — side effects CLEAN, one bug filed reproduced** (no walker skips a dot-name). Inbox: the same four, owner-gated. Dogfood `--mosaic` CLEAN. **START HERE NEXT RUN:** Builder: part (a) of that entry (ungated); Scout: sweep (4) with a new angle.*
*2026-11-03 (Builder, branch `claude/fervent-allen-9aep51`) — **no app change: nothing ungated; two new-angle probes CLEAN** — a sub deleted from disk before its stack is skipped with a plain log line (7 of 8 stacked), and all 21 editor ops keep mosaic holes as holes at every parameter extreme. Suite 8557 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (3) with a new angle; Builder: nothing ungated until the sensor-temperature or vignette gate is answered.*
*2026-11-03 (Builder, branch `claude/fervent-allen-d02o0b`) — **no app change: nothing ungated; first-ever dogfood `--mosaic --big --deep --closing --incoming-lag --editor` CLEAN** (`[scale]` 0/16 moved, trim 7.9 % / 6.7 % full-size, the three Tonight cards agree, deep frames table windowed at 301 rows, three editor drives clean). Suite 8557 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (3) with a new angle; Builder: nothing ungated until the sensor-temperature or vignette gate is answered.*
*2026-11-03 (Builder, branch `claude/fervent-allen-dq0u87`) — **no app change: nothing ungated; first-ever dogfood `--mosaic --dithered --deep --combine --calibration --editor` CLEAN** — the first `--deep`/`--dithered`/`--calibration` pass since the `--combine` stack-step fix, so its mosaic checks really ran (trim 7.9 %, dithered 30.7 % against its 30.3 % apron, calibration note withdrew with both masters applied, §10 `incoming/` unchanged, 1,200-sub frames table windowed at 301 rows). **START HERE NEXT RUN:** Scout: sweep (3) with a new angle; Builder: nothing ungated until the sensor-temperature or vignette gate is answered.*
*2026-11-03 (Builder, branch `claude/fervent-allen-6uov9m`) — **no app change: nothing ungated; first-ever dogfood `--mosaic --combine --restack --incoming-lag --big --editor`** found `--combine` leaving every loaded sample unstacked, so its mosaic-trim, scale-pair and full-size checks never ran and said nothing (earlier `--combine --mosaic` "CLEAN" records cover the combine journey only); `agent-dogfood.sh` fixed, re-run CLEAN (scale 0/16 moved, trim 7.9 %). **START HERE NEXT RUN:** Scout: sweep (3) with a new angle; Builder: nothing ungated until the sensor-temperature or vignette gate is answered.*
*2026-11-02 (Builder, branch `claude/fervent-allen-s1pgbe`) — **v0.505.9: a one-target stack after a Combine shows its deeper picture** (`pipeline._settle_app_pin_after_stack`; only the batch ever lifted the merge's pin, so Stack/Process left the shallower picture on the wall and "+3 subs waiting" on the board). Found by a first-ever dogfood `--mosaic --deep --combine --calibration --editor`, otherwise CLEAN; `--calibration` under `--combine` now re-processes (dev script). **START HERE NEXT RUN:** Scout: sweep (3) with a new angle; Builder: nothing ungated until the sensor-temperature or vignette gate is answered.*
*2026-11-02 (Builder, branch `claude/fervent-allen-mt7l7g`) — **no app change: nothing ungated; first-ever dogfood `--mosaic --dithered --incoming-lag --calibration --editor` CLEAN** (mosaic trim 7.9 %, dithered 30.7 % against its recorded 30.3 % apron; the calibrated branch withdrew its note with both masters applied; incoming-lag note moved from "8 subs" to the one unreadable sub once the scan imported the 7; three editor drives clean, nothing overflowing, no console errors). Suite 8549 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (3) with a new angle; Builder: nothing ungated until the sensor-temperature or vignette gate is answered.*
*2026-11-02 (Builder, branch `claude/fervent-allen-u2gvb2`) — **no app change: nothing ungated; first-ever dogfood `--mosaic --dithered --closing --no-site --combine --editor` CLEAN** (§10: `incoming/` unchanged through merge; `--closing` skips itself under `--no-site`). Its one `!` line was the editor drive's stale-toast wait, fixed in `scripts/dogfood_editor.mjs` (cursor parked off the toast stack, 20 s wait); the re-run read the marked chip's own sentence. Suite 8549 passed / 7 skipped. **START HERE NEXT RUN:** Scout: sweep (3) with a new angle; Builder: nothing ungated until the sensor-temperature or vignette gate is answered.*
*2026-11-02 (Scout, branch `claude/exciting-wozniak-8uy5tg`) — **QA rotation sweep (2), new angle: which returning target "It's back" names in full — one bug, Scout-fixed as v0.505.8** (`nightplan._returning_targets` ranked same-night returns by target total; a 4-field 6 h mosaic, 1.5 h per part, was named ahead of a 3 h single field). Inbox: the same four, owner-gated; #1344's hold unanswered. Dogfood `--mosaic --editor` CLEAN. **START HERE NEXT RUN:** Scout: sweep (3) with a new angle; Builder: nothing ungated until the sensor-temperature or vignette gate is answered.*
*2026-11-02 (Builder, branch `claude/fervent-allen-ker4l7`) — **no app change: nothing ungated; first-ever dogfood `--mosaic --no-site --editor --big` CLEAN** (Auto trim 7.9 % small / 6.7 % full-size, editor drive clean on all three runs, nothing overflowing, no console errors; tallest page the documented `[phone] /life-list [Still to shoot]` 14,513 px). **START HERE NEXT RUN:** Scout: sweep (2) and triage #1344's hold; Builder: nothing ungated until the sensor-temperature or vignette gate is answered.*

## Standing frontier

- **Mosaic-scale and walk-away behaviour is the open frontier**, not the single-field engine core. Do NOT re-sweep
  `seestack/stack` or `seestack/calibrate` until a new bug is found there (AGENTS.md).
- **Grown-canvas rule:** anything that puts one run's look, crop or picture onto another run's canvas places it by
  both masters' WCS and falls back (or hides itself) without one — v0.502.23 (reel) and v0.502.24 (previous-edit
  crop) are the pattern; the noise-delta picture (v0.502.32) was the last known surface.

## How the owner gets builds now

He deploys with `sudo bash scripts/deploy.sh` from the **`stable`** branch (advanced by `.github/workflows/stable.yml`
to the newest `main` commit ≥ 3 days old with green CI) or from a release tag. So a fix reaches him days after it
merges — ship the follow-up to your own change *before* that soak ends.
