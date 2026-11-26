# Current focus — AstroStack

> **Short on purpose (AGENTS.md: "short, dated, the Scout keeps it current").** One dated line per run goes at the
> top of *Run log*; keep about the last ten and move older lines, whole and in order, to `docs/archive/`. Detail
> belongs in `docs/PROCESS-NOTES.md`, never here. The 2,559-line page this replaced is kept verbatim in
> [`archive/FOCUS-to-2026-10-21.md`](archive/FOCUS-to-2026-10-21.md) — nothing was deleted.

## Front of the queue (2026-11-26)

**Open and ungated: the full audit's defects, filed as Bugs by the Scout on 2026-11-26, plus one new sweep-(1) bug.**
Take them top-down from "Bugs". The 🟠 entries come first: Auto's wavelet denoise leaves the export grainier than the
preview on stacker-correlated grain (editor, PRIORITY 1); `SettingsStore` boot (full disk, a damaged `config.json`,
rollback dropping keys); the nested-layout delete path; and the update that leaves the app stopped. The 🟡 entries
follow: the walk-away re-solve and restart re-import, PBKDF2 per request, the OOM guard on mosaics, the Moon & Sun
mesh and Seestar `{ip}` validation. The ⚪ batch holds the small items. **None of them changes a default.** The
audit's picture-quality ranking (Auto's target look, the sky flatten, nebula colour) waits on the owner and is filed
under Needs owner sign-off. Everything shipped before this lives in `SHIPPED.md` (latest v0.511.7). The owner's ⭐
colour-pattern entry is on HOLD for his per-temperature numbers. The dark ring waits on a diagnostic (below).

**Gated, do not start:** the un-located-panel entry (Scout 2026-10-19 in Bugs) waits on diagnostic `mosaic_panel_hints` v2
(v0.506.10), the dark ring on `sky_falloff` v3 (v0.506.16) and the #878 headline LEAD on `twin_target_overcount` v1 (v0.506.8); the
other LEADs and ⚪ notes in Bugs wait on owner/observer measurements — read each one's gate first, and do not
re-litigate a stand-down that carries numbers. **Issue inbox:** #878, #880, #903, #1015 — all previously acted-on
and owner-gated, none updated since 2026-10-12 (re-checked 2026-11-11, Scout `optimistic-cannon-usq0cn`, again by `mh7yxx`, `jy9aay`, `dsfjim`, `x5qu3g`, `hv4l4e`, `vrbblx`, `i0xwhr`, `geies9`, `vlbnkm`, `kab7ux`, `facsy5`, `4ynjos`, `5y9dxt`, `crb7x5`, `50wcqa` and `g4pc96`, 2026-11-12; `c961hx`, 2026-11-13; `r0r7nj`, 2026-11-14; `n2dcsi`, 2026-11-15; `rxvumk`, 2026-11-16; `0rt6q3`, 2026-11-17; `oq82pp`, 2026-11-18; `iqbzjc`, 2026-11-19; `ibvjue`, 2026-11-20; `ddog9y`, 2026-11-21; `2lvfdt`, 2026-11-22; `rk51kw`, 2026-11-23; `8tbxaq`, 2026-11-24; `wi0jah`, 2026-11-25; `m4byti`, 2026-11-26). No `Diagnostic result:` issue has landed yet
(the diagnostics shipped in v0.506.0 / v0.506.1 run after the owner's next update).

## QA rotation (Scout)

Order (AGENTS.md roles): (1) preview↔export parity at mosaic scale → (2) mosaic/walk-away per-panel divergence →
(3) ASTAP/ffmpeg filesystem side effects with a stub binary → (4) the webapp routers. **Last swept: (1), 2026-11-26
→ next sweep is (2).** Each sweep must find a *new* angle — the angles already run are in the `Sweep (N)` entries
of `docs/PROCESS-NOTES.md` (grep `sweep (1)`).

## Run log (newest first)

*2026-11-26 (Scout, branch `claude/sweet-euler-m4byti`) — **the full audit's unfiled defects filed as Bugs (nine entries plus one ⚪ batch, each re-checked in code or re-run), and sweep (1), new angle: Auto's wavelet denoise on stacker-correlated grain, one 🟠 bug filed reproduced** (the export keeps 92–98 % of the grain where the step-5 preview keeps 44 %). The audit's picture-quality ranking was filed under Needs owner sign-off. Inbox unchanged; no `Diagnostic result:`; no open PRs. Suite 9018 passed / 7 skipped. Dogfood `--build --mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: the 🟠 entries at the top of Bugs, denoise first; Scout: sweep (2), and file `Diagnostic result:` issues when they land.*
*2026-11-26 (Builder, branch `agent/seestar-poll-oserror`) — **v0.511.7: the full audit's Seestar defect 1 fixed — the telemetry thread no longer dies the first time the scope goes offline** (`SeestarClient.connect` raises `SeestarError` on a socket failure; `SeestarManager._poll_one` guarded per scope). +3 tests, red before. The audit (`docs/audit/2026-11-26/`) holds more verified, unfiled defects (Seestar discovery and `{ip}` validation, PBKDF2 on the event loop, ASTAP re-running on known-unsolvable subs, no gzip on frame JSON, boot on a full disk). **START HERE NEXT RUN:** Builder: the audit README's "broken or unsafe" list is real work — take the next S item there that does not change a default; Scout: file the audit's remaining defects as Bugs, sweep (1).*
*2026-11-26 (Builder, branch `claude/fervent-gauss-7d6n9z`) — **adopted stranded PR #1568 (v0.511.6, `find_astap` only runs a file named like ASTAP)**: idle 3 h, based on current `main`, all six CI checks green; ASTAP-touching tests 1346 passed locally, fail-before shown (7 guard tests red with the old `p.exists()`). Merged. Its three unfiled audit follow-ups (host-path settings writes need a credential, Host-header allow-list, non-root container) filed under Needs owner sign-off. **START HERE NEXT RUN:** Builder: nothing ungated — stop early unless an owner gate, a `Diagnostic result:` issue or a Scout-filed bug has landed, and check `main`'s CI first; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-26 (Builder, branch `claude/fervent-gauss-r9bzuq`) — **no app change: nothing ungated; big-picture dogfood `--build --mosaic --editor --big` CLEAN** — `main`'s CI green (#1566); inbox unchanged (#878, #880, #903, #1015, owner-gated; no `Diagnostic result:`), no open PRs, no Scout-filed bug open since v0.511.5. Dogfood: no console errors or overflow on any page, Auto's mosaic trim 7.9 %, full-size editor navigator/split checks passed; the `--big` Add-menu drive was cut off after Stretch by this run's own 25-min wall-clock cap (`waitForTimeout` on a closed page), not by the app. **START HERE NEXT RUN:** Builder: nothing ungated — stop early unless an owner gate, a `Diagnostic result:` issue or a Scout-filed bug has landed, and check `main`'s CI first; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-26 (Builder, branch `claude/fervent-gauss-a4n22x`) — **no app change: nothing ungated** — `main`'s CI green (#1565); inbox unchanged (#878, #880, #903, #1015, owner-gated; no `Diagnostic result:`), no open PRs, no Scout-filed bug open since v0.511.5. Stopped early. **START HERE NEXT RUN:** Builder: nothing ungated — stop early unless an owner gate, a `Diagnostic result:` issue or a Scout-filed bug has landed, and check `main`'s CI first; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-26 (Builder, branch `claude/fervent-gauss-qtnj15`) — **no app change: nothing ungated** — `main`'s CI green (#1564); inbox unchanged (#878, #880, #903, #1015, owner-gated; no `Diagnostic result:`), no open PRs, no Scout-filed bug open since v0.511.5. Stopped early. **START HERE NEXT RUN:** Builder: nothing ungated — stop early unless an owner gate, a `Diagnostic result:` issue or a Scout-filed bug has landed, and check `main`'s CI first; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-25 (Builder, branch `claude/fervent-gauss-8v1nox`) — **no app change: nothing ungated** — `main`'s CI green (#1563); inbox unchanged (#878, #880, #903, #1015, owner-gated; no `Diagnostic result:`), no open PRs, no Scout-filed bug open since v0.511.5. Stopped early. **START HERE NEXT RUN:** Builder: nothing ungated — stop early unless an owner gate, a `Diagnostic result:` issue or a Scout-filed bug has landed, and check `main`'s CI first; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-25 (Builder, branch `claude/fervent-gauss-8kr3mc`) — **no app change: nothing ungated** — `main`'s CI green (#1562, v0.511.5); inbox unchanged (#878, #880, #903, #1015, owner-gated; no `Diagnostic result:`), no open PRs, no Scout-filed bug open since v0.511.5. Stopped early. **START HERE NEXT RUN:** Builder: nothing ungated — stop early unless an owner gate, a `Diagnostic result:` issue or a Scout-filed bug has landed, and check `main`'s CI first; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-25 (Builder, branch `claude/fervent-gauss-4vxton`) — **v0.511.5: the Scout's 2026-11-25 🟡 `find_target` shadowing fixed** — `Library.find_target` prefers the `safe_name` match; display-name callers (scanner hold-back, skipped-folders card, sample demo) use the new `find_target_by_name`. +7 tests (both spellings, both orders: page, DELETE, re-scan), red before. Suite 9003 passed / 7 skipped. **START HERE NEXT RUN:** Builder: nothing ungated — stop early unless an owner gate, a `Diagnostic result:` issue or a Scout-filed bug has landed, and check `main`'s CI first; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*
*2026-11-25 (Scout, branch `claude/sweet-euler-wi0jah`) — **QA rotation sweep (4), new angle: the `{safe}` target path parameter when one target's display name is another's folder name — one bug, filed reproduced (🟡 S)**: `Library.find_target`'s `name OR safe_name` hands target "M_31" the URL of "M 31" (folder `M_31`); its card opens the other page and DELETE removes the other target. Inbox: the same four, owner-gated; no `Diagnostic result:`; no open PRs. Suite 8996 passed / 7 skipped. Dogfood `--build --mosaic` CLEAN (trim 7.9 %). **START HERE NEXT RUN:** Builder: the 2026-11-25 🟡 `find_target` Bug; Scout: sweep (1), and file `Diagnostic result:` issues when they land.*

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
