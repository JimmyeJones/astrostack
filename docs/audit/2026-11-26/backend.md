# AstroStack audit — backend robustness, data safety, security, install/update

Scope: `main` at v0.511.5 (5263bb6). Read-only on the repo. Every experiment script is in
`/tmp/claude-0/-home-user-astrostack/898c11c2-2328-5559-a5d0-f0f505498eb1/scratchpad/audit/backend/` (`exp1`…`exp11`), run with the repo's `.venv`.

## 1. Verdict

1. **The incoming/ read-only guarantee holds in the owner's configuration.** I drove every destructive-looking endpoint over HTTP with `copy_to_cache` off and an ASTAP stub that litters beside its input; a files + directories + modes + mtime + sha256 snapshot of `incoming/` was identical after every step (exp2). No code path was found that deletes, renames or rewrites through a frame's `source_path`/`cached_path`.
2. **The guarantee is enforced by application code only.** The container runs as root with `incoming/` mounted read-write, and the app has an unauthenticated route to code execution as that root (finding 1, confirmed end to end). That is the real hole in the "raws can never be lost" promise.
3. **The update path can leave a non-technical owner with the app down and no page to fix it from**: the image is built *after* the app is stopped, a retry overwrites the rollback record, and a full disk stops the app from booting at all (findings 2, 6, 7).
4. **Turning the password on is punished**: every request pays ~190 ms of PBKDF2 on the event loop, serialised (finding 4). The safe configuration is the slow one, so the default-open install is likely to stay open.
5. Much is genuinely sound: upload and zip handling, the ASTAP scratch-copy design, the updater's request validation and `O_NOFOLLOW` handling, `restore-data.sh` (no `zfs rollback`), additive schema policy, frame paging. The risks are concentrated in trust boundaries and deploy operations, not in the per-file write paths the project has spent most effort on.

## 2. incoming/ write-path inventory

"Sentinel test" = `tests/webapp/test_incoming_readonly_guard.py` (repo's own). "exp2" = my snapshot run (owner-shaped config, littering ASTAP stub, 10 steps, 0 lost / 0 changed / 0 unexpected-new at each).

| Operation | file:line | What keeps it out of incoming | Verdict | How verified |
|---|---|---|---|---|
| `shutil.copy2(src, cached)` ingest Stage-1 | `seestack/io/ingest.py:308` | destination is `targets/<safe>/cache/stage1/frame_NNNNNN`; source only read | SAFE | read; exp2 (cache off), sentinel test (cache on) |
| ASTAP run (`-f`, writes `.wcs`/`.ini` beside input) | `seestack/solve/astap.py:399-415, 442-463` | each solve copies the sub into a `TemporaryDirectory` and points ASTAP at the copy; sidecars read back then discarded | SAFE | exp2: stub wrote `.wcs`, `.ini` and a litter file beside its `-f` path and in cwd; none appeared in incoming (cwd litter landed in the app's cwd) |
| Stale solve-scratch sweep `rmtree` | `seestack/solve/astap.py:567` | only prefixed, non-symlink dirs directly under the system temp dir | SAFE | read |
| Bootstrap deep-stack `writeto` | `seestack/solve/bootstrap.py:565` | scratch dir | SAFE | read |
| ffmpeg / ffprobe | `seestack/video/ffmpeg.py:140, 444` | input only (`-i <path>`), output is a stdout pipe, no cwd | SAFE for writes (see finding 14 for reads) | read; sentinel video test |
| Delete target `rmtree` | `seestack/io/library.py:923` | path is `library/targets/<safe_name>`, `safe_name` looked up in the registry, never from the URL; `nested_incoming_conflict` refuses saving a layout that nests the trees | **CONDITIONAL** | exp2 safe in a normal layout; **exp3: with a config.json that already holds `incoming_dir` inside `library/targets`, boot only logs a warning and Delete removed 3 of 6 raw subs** (finding 9) |
| Merge targets copy / stray unlink | `seestack/io/merge.py:154, 435, 446` | both ends under `targets/` | SAFE | exp2 |
| Cache clear `rmtree` | `seestack/core/cache.py:87`, `webapp/routers/storage.py:451, 460` | `targets/<safe>/cache/*`, thumbs, proxies; `rmtree` refuses a symlinked root | SAFE | exp2 (all five stages) |
| Prune / delete stack run `unlink` | `webapp/routers/storage.py:129, 155` | paths are strings stored on `stack_runs` by the stacker (always `targets/<safe>/output/`); no client-supplied path; `output_basename` sanitised | SAFE | exp2; read |
| Stack outputs `writeto`/`rename`/`unlink` | `seestack/stack/output.py:326-478, 957, 1032, 1039` | `project_dir/output` | SAFE | exp2 |
| Editor exports, previews, reels, proxies | `webapp/routers/stack.py:2482-5181`, `webapp/pipeline.py:3141, 3504`, `seestack/edit/proxy.py:247-400`, `seestack/render/*` | `targets/<safe>/output` or cache | SAFE | exp2 |
| Calibration master build / delete | `seestack/calibrate/masters.py:652`, `webapp/calibration.py:89, 109, 2144` | writes `library/calibration/`; source folder confined to incoming by `routers/calibration.py:31-70` and only read | SAFE | read; repo test `test_calibration_incoming.py` |
| Upload (single file) | `webapp/routers/upload.py:335-358, 365-420` | the one sanctioned writer: unique `.part` temp, placed with `os.link` (fails if the name exists); names sanitised per segment and re-confined with `resolve()` | SAFE (create-new only) | exp2: same-name upload skipped, original bytes and mtime intact; `../` and backslash traversal rejected |
| Upload (zip) | `webapp/routers/upload.py:431-590` | never `extractall`; per-member `safe_relpath` + `confined_dest`; size cap = declared size; free-space check | SAFE (create-new only) | exp2: absolute and `../` members rejected, existing member skipped, nothing escaped |
| Upload fallback `os.replace` | `webapp/routers/upload.py:352-356` | only on filesystems without hard links; `lexists` check first | CONDITIONAL (race window; not ZFS) | read |
| Sample data load / remove | `webapp/sample_data.py`, `routers/sample.py:163` | temp dir then library; removal is a library target delete | SAFE | read; sentinel test |
| Video stills | `webapp/video.py:479-699, 1043-1183` | `<data_root>/video/<capture_id>`; guard refuses incoming under `video/` | SAFE | read; sentinel test |
| Pictures archive | `webapp/picturesarchive.py:319, 402`, `routers/gallery.py:1380` | `<data_root>/exports` | SAFE | exp2 |
| Sky map cache, diagnostics, thumbnails | `routers/sky.py:535-654`, `webapp/diagnostics.py:48`, `seestack/render/thumbnail.py:69-109` | library / state | SAFE | read |
| config.json, jobs DB, Seestar key, update request | `webapp/config.py:601`, `webapp/jobs.py`, `seestar/keyfile.py:224-247`, `routers/updates.py:119-123` | `<data_root>/state` | SAFE | read |
| `ensure_dirs` `mkdir(parents=True)` on incoming | `webapp/config.py:491-498` | creates the folder if missing; never touches contents | SAFE (but see note under "disclosure") | exp6 |
| `deploy.sh` backup / `restore-data.sh` | `scripts/deploy.sh:82-98`, `scripts/lib/restore-data.sh:62-75` | snapshot is read-only; restore copies only `*.sqlite*` and `config.json` under `library/` and `state/`, refuses symlinked folders, never `zfs rollback` | SAFE | read; repo tests `test_deploy_script.py`, `test_restore_data.py` |
| **Any file operation by code the web UI can make the container run** | `webapp/routers/settings.py:117`, `seestack/solve/astap.py:442` | nothing | **UNSAFE** | exp1b: unauthenticated HTTP only → shell command ran as uid 0 in the app's process context (finding 1) |

Not found anywhere in `seestack/` or `webapp/`: `shutil.move`, `fits.open(mode="update")`, write-mode `memmap` on a source frame, any unlink/rename keyed on `source_path` or `cached_path`.

## 3. Defects and risks (ranked)

### 1. ✅ FIXED in v0.511.6 (PR #1568) — Unauthenticated remote code execution as root in the container, via the `astap_path` setting
- **Severity: critical** (it voids the incoming guarantee). **Confidence: CONFIRMED** end to end.
- `webapp/routers/settings.py:117-135` (PUT accepts `astap_path`, `data_root`, `incoming_dir`, `library_root` — the same keys `_HOST_KEYS` at :146 deliberately keeps out of *import*), `seestack/solve/astap.py:121-142` (any existing path is accepted), `:442-463` (it is executed with `-f <copy of an uploaded file>`), `webapp/routers/system.py:111` (also executed with `-h`), `docker/Dockerfile` (no `USER`; root), `docker/docker-compose.yml` (`/data` incl. `incoming/` read-write).
- Evidence (exp1b, TestClient, password off as shipped): `PUT /api/settings` naming a shell as the ASTAP program → 200; `POST /api/upload` of a file that is a valid FITS and also valid input for that program → saved, pipeline queued; the auto-solve step ran it; a marker file was written containing `ran-as-0`.
- Scenario: any device on the LAN (a phone, a TV, a guest laptop) — or a web page the owner visits, through finding 3 — runs arbitrary commands as root inside a container that holds the only copy of every raw sub, read-write.
- Fix (S): drop `astap_path`, `data_root`, `incoming_dir`, `library_root` from what the settings PUT accepts unless a password is set, or better make them env/compose-only; validate that the ASTAP candidate is named `astap`/`astap_cli`. Then (M) run the container as a non-root user and document a ZFS periodic-snapshot task for the dataset as the real backstop.
- **NEW** (no entry in `docs/IMPROVEMENTS.md` / `SHIPPED.md`).

### 2. A failed image build leaves the app stopped, and a retry destroys the rollback record
- **Severity: high. Confidence: CONFIRMED** (exp4, real scripts over the repo's own stub fixture).
- `scripts/deploy.sh:74` (writes `last-good` from the *current checkout* before anything else), `:76` (stop), `:101-103` (checkout, then `up -d --build`).
- Evidence: with the build failing, deploy exits 1 after `compose stop`; no `start`/`up` is issued; the checkout is already on the new version. Running deploy again records `last-good = v0.2.0` (the version that never started); `rollback.sh --yes` then reports "now v0.2.0 → going to v0.2.0" and exits 0. The genuinely previous commit is recorded nowhere.
- Scenario: every update rebuilds `pip install .[web]` (and `npm ci`, and on a cache miss an unpinned, un-checksummed ASTAP download from SourceForge, `docker/install-astap.sh:17-31`). One network blip during a one-click update and the app is down; the page that would show the helper's message is the app that is down; the owner needs SSH. The obvious next move — press/run update again — erases the way back.
- Fix (S–M): `docker compose build` *before* `stop`; on any failure after stop, `docker start astrostack` automatically; write `last-good` only when `CUR_SHA` differs from the target and only after the build succeeds (or record the running container's image/commit instead of the checkout's).
- **NEW.** (The "says so and prints `docker start`" behaviour is tested and deliberate; the outage and the lost record are not filed.)

### 3. No Host-header check: a DNS-rebinding page gets the full API of a password-less install
- **Severity: high (as the remote leg of finding 1). Confidence: CONFIRMED** for the acceptance (exp5), READ for the browser attack.
- `webapp/main.py:304-349`: a state-changing request is allowed when `Sec-Fetch-Site: same-origin`, or when `Origin` matches whatever `Host` the request carried. A rebound hostname satisfies both. exp5: `PUT /api/settings` with `Host`/`Origin` naming another domain → 200; a plain cross-site PUT → 403 (that part works).
- Fix (S): accept only requests whose `Host` is an IP literal, `localhost`, or a name on a short allowlist setting (default: the container hostname plus `*.local`); refuse others with 421.
- **NEW.**

### 4. With a password set, every request spends ~190 ms of PBKDF2 on the event loop
- **Severity: medium–high. Confidence: CONFIRMED** (exp10).
- `webapp/main.py:355-376` (async middleware calls the KDF synchronously), `webapp/auth.py:33, 69-94` (200,000 rounds per check, no cache).
- Evidence: 30 concurrent `GET /api/settings`: 0.48 s with no password, 5.35 s with one. Requests are serialised behind the loop, so a gallery of ~100 thumbnails is ~20 s, and the Docker health probe queues behind the same loop.
- Fix (S): cache a successful `(header → ok)` verdict in memory keyed by an HMAC of the header, for the process lifetime or a few minutes; run the first check in a threadpool.
- **NEW.**

### 5. Subs that already failed to plate-solve are re-sent through the whole ASTAP ladder on every later import of that target
- **Severity: medium–high at the owner's scale. Confidence: CONFIRMED** (exp9).
- `seestack/io/scanner.py:1758` → `seestack/solve/runner.py:330-387` (offers every accepted-unsolved and every `solve_failed:` frame, no attempt counter, no back-off).
- Evidence: 8 unsolvable subs → 24 ASTAP invocations; each later scan that added **one** sub ran 27, 30, 33 — three per unsolved sub, every time.
- Scenario: a 35,894-sub target with a few hundred cloud-ruined subs pays hundreds of failing solves (each up to the timeout, times the ladder) on every batch that arrives during a night. That holds the single worker, so stacks and other imports wait. `docs/SHIPPED.md:18148` mentions it in passing ("hours per scan on a walk-away box") as a reason not to build something else; it was never filed as a bug.
- Fix (S–M): remember per frame which (ASTAP version, star-DB, hint) combination already failed and skip until one changes or the user asks ("Rescue unsolved" already exists for that).
- **KNOWN IN PASSING, NOT FILED.**

### 6. The app cannot boot when the data disk is full or read-only
- **Severity: medium. Confidence: CONFIRMED** with a simulated ENOSPC (exp11).
- `webapp/config.py:561`: `SettingsStore.__init__` re-saves `config.json` unconditionally on every boot; the `OSError` propagates out of the lifespan.
- Scenario: pool or dataset quota fills during a big stack; the container restarts; with `restart: unless-stopped` it loops. The Storage page — the only friendly way to free space — is unreachable.
- Fix (S): make the boot-time save best-effort (log and continue; skip it when the serialised text equals what is on disk).
- **NEW.**

### 7. Deploy snapshots are never pruned, so "free up space" stops freeing space
- **Severity: medium. Confidence: READ** (+ exp4 shows one snapshot per deploy, no destroy anywhere in `scripts/`).
- `scripts/deploy.sh:84`. Each update snapshots the whole dataset. Raws are never deleted so they cost nothing, but every pruned stack run, cleared cache and replaced master stays pinned by every older snapshot. Feeds finding 6.
- Fix (S): keep the newest N (3?) `astrostack-pre-*` snapshots, destroy older ones after a healthy deploy; show snapshot usage on the Storage page.
- **NEW.**

### 8. Root on the NAS is delegated to whatever reaches GitHub `main`, and the 3-day soak is measured on a forgeable date
- **Severity: medium–high (design). Confidence: READ.**
- `scripts/update_agent.py:355` (root runs the clone's `deploy.sh`), `:399-408` (`refresh_self` copies the new `update_agent.py` into root's cron path), `.github/workflows/stable.yml:45` (`git log -1 --format=%ct` — committer date, set by whoever makes the commit; AGENTS.md §8 allows a direct fast-forward push).
- The helper's own hardening is good (see section 4) but it protects against the *container*, not against the repository. Code is written and merged by unattended agents with no human review, on a public repo whose issue tracker those agents read. Nothing is signed; `stable` has no "known-bad" list, so it can also advance to a commit whose fix landed two days later.
- Fix (M): compute the soak from the CI run's `created_at` (server time), not the commit; protect `main`/`stable` so only PR merges and the workflow can write them; add a `do-not-ship` marker file the workflow honours; consider requiring an owner-held signed tag for anything that changes `scripts/`, `docker/` or `update_agent.py`.
- **NEW** as a filed risk.

### 9. An install that is already in the unsafe folder layout boots, warns once in a log, and still deletes
- **Severity: medium (low likelihood, total loss if hit). Confidence: CONFIRMED** (exp3).
- `webapp/config.py:553-560`. With `incoming_dir` already inside `library/targets` in `config.json`: boot succeeded, a scan adopted each raw folder as a target folder, `DELETE /api/targets/M_42?remove_files=true` → 200 and 3 of 6 raw subs gone. Saving any setting in that state returns 422, so the owner also cannot change other settings, yet nothing on screen says why.
- Fix (S): while `nested_incoming_conflict(...)` is non-None, refuse every destructive endpoint (delete target, merge, cache clear, prune) and the scan, and surface the sentence on the Dashboard. Booting is fine; deleting is not.
- **FILED AS DELIBERATE** ("still boots and warns", `docs/SHIPPED.md:5463`); the destructive-path gap is not filed.

### 10. A damaged config.json silently turns the password off, resets folders, and flips auto-stack on — and the damaged file is overwritten at once
- **Severity: medium. Confidence: CONFIRMED** (exp6).
- `webapp/config.py:501-533, 545-561`. Truncated JSON → defaults → immediate re-save. Result in exp6: `auth enabled: False`, `incoming_dir: ''`, `auto_stack: True`, no copy of the bad file kept. A top-level non-object does the same. (One bad field is handled well: only that field resets.)
- Writes are atomic and fsynced, so this needs a hand edit or a restore gone wrong — but the outcome is an open app that starts auto-stacking ~100 targets.
- Fix (S): on a parse failure keep `config.json.unreadable-<stamp>`, do not re-save, and start with the watcher and auto-stack off until the owner confirms.
- **NEW.**

### 11. Rolling back to an older build drops settings the newer build wrote
- **Severity: low–medium. Confidence: CONFIRMED** (exp6c).
- Unknown keys are ignored on load and the boot re-save writes the file without them. Roll back one version and forward again and any setting introduced in between (including a read-only token if the rollback crosses its introduction) is gone.
- Fix (S): `model_config = ConfigDict(extra="allow")` on `Settings`, or carry unknown top-level keys through `save()`.
- **NEW.**

### 12. The one-click update does not look at the job queue
- **Severity: low–medium. Confidence: READ.**
- `webapp/routers/updates.py:144-154`, `frontend/src/components/UpdatesCard.tsx`, `scripts/deploy.sh:76` (`compose stop`, default 10 s grace then SIGKILL). A stack that has been running for 19 hours is killed and marked interrupted; nothing resumes it.
- Fix (S): `apply`/`rollback` return 409 with the running job's name unless `force` is sent; the card says what will be interrupted.
- **NEW.**

### 13. No watchdog on the single worker
- **Severity: low–medium. Confidence: CONFIRMED** for the mechanics (exp7), SUSPECTED for likelihood.
- `webapp/jobs.py:515-563`. A job body that never returns (a pool child blocked on I/O; `fut.result()` has no timeout at `seestack/stack/stacker.py:4868, 5003`) holds the queue for ever; cancel is honoured only by cancel-aware bodies (exp7b: `cancel()` returned True, state stayed `running`). A `BaseException` in a body ends the worker thread with the job left `running` and every later job `queued` (exp7a) while `/api/health` stays green. I found no `sys.exit` in the engine, so the second case is theoretical today.
- Fix (S): catch `BaseException` in `_run` (re-raise only on stop), and expose "worker alive / current job running for N h with no progress for M min" on `/api/system` and the Dashboard.
- **NEW** (queue starvation by `reprocess_all` itself was fixed in v0.444.0; a single long stack still blocks imports by design and says so since v0.441.1).

### 14. ffmpeg is given uploaded/dropped video files with no protocol restrictions
- **Severity: low. Confidence: READ.** `seestack/video/ffmpeg.py:140-147, 444`. A crafted playlist-style file in a `*_video/` folder can make ffmpeg open other local files or URLs (contradicting "no outbound network"). Fix (S): add `-protocol_whitelist file,pipe` and `-f`-free probing limits.
- **NEW.**

### 15. Seestar "connect" accepts any host string
- **Severity: low. Confidence: READ.** `webapp/routers/seestar.py:101-107`, `webapp/seestar/manager.py:321-340, 118-121`. With the integration enabled (a setting anyone can flip on an open install), `POST /api/seestar/<host>/connect` opens a TCP connection to an arbitrary host on the scope's fixed port and later fetches a path that host names from its HTTP port; only JPEG/PNG bodies are returned and the port is not caller-chosen. Each distinct string also adds a client object that is never evicted. Fix (S): require an IP literal in a private range, or one that discovery already listed.
- **NEW.**

### 16. No memory limit on the container
- **Severity: low. Confidence: READ.** `docker/docker-compose.yml` sets `shm_size` but no `mem_limit`; an over-budget stack is then the *host's* OOM problem and the kernel chooses the victim. The stacker has its own memory-budget guard, which is the main defence. Fix (S): document/set `mem_limit` to a fraction of RAM.
- **NEW.**

### 17. `restore-data.sh` restores databases but not the files they describe
- **Severity: low. Confidence: READ.** `scripts/lib/restore-data.sh:44-75`, `scripts/deploy.sh:92` (tar holds `*.sqlite*` and `config.json` only). After a restore, older `stack_runs` rows point at `output/master.*` names that a later re-stack has since archived and replaced, and `library/calibration/masters.json` is not in the tar backup at all. Nothing is lost from disk; history rows can show the wrong picture and orphan files accumulate. Also, with `rollback.sh <older tag> --restore-data` the backup restored is always the *last* deploy's, whose schema may still be newer than the tag.
- Fix (S): include `masters.json` and state `*.json`; print "re-scan and check History" after a restore; compare the backup's `user_version` to the target's schema.
- **NEW.**

## 4. Checked and found sound

- **ASTAP sidecars**: never pointed at the raw; scratch copy per invocation, stale scratch swept at boot. Verified with a littering stub.
- **Upload and zip**: traversal, absolute names, backslashes, overwrite of an existing raw, zip bombs (declared-size cap + free-space reserve), macOS sidecars, concurrent same-name posts. All behaved in exp2.
- **Path parameters**: `{safe}` is resolved through the registry, never joined to a path; video `capture_id` is re-discovered server-side; calibration `source_dir` is confined to incoming with symlinks resolved; the SPA fallback is confined to the static root; calibration master paths are stripped from client input.
- **Updater helper** (`scripts/update_agent.py`): the request is validated field by field and never reaches a command line; the page cannot name a commit; every file under the container-writable folder is opened through a directory fd with `O_NOFOLLOW`/`O_EXCL`; the helper refuses to install inside the data folder; a lock prevents overlapping runs.
- **Rollback data handling**: no `zfs rollback`; stale WAL files cleared before older databases are copied back; symlinked folders refused; schema comparison forces `--restore-data` when the older build cannot open the newer format. Older builds refuse a newer schema with a clear message rather than corrupting it, and most new columns are added without a version bump precisely to stay rollable.
- **Cross-site POST check**: plain cross-origin state-changing requests are refused (403 in exp5); the gap is only the rebinding case in finding 3.
- **Auth storage**: PBKDF2 with per-install salt, constant-time compare, credentials excluded from settings GET/PUT/export; read-only token limited to an exact GET allowlist.
- **Job persistence**: DB errors and unserialisable results cannot kill the worker; cancel/claim race closed; restart marks running and queued jobs distinctly (exp7c).
- **Scale**: frames endpoint is paged in SQL. On one synthetic 35,894-sub target (small files, this machine's disk, not ZFS): first import 241 s; a re-scan with nothing new 10.4 s at 156 MB peak RSS; one watcher poll 2.0 s (exp8, exp8b). No quadratic behaviour seen. Note the watcher re-walks the whole tree on every inotify wake-up, so during a long copy it polls back to back; at 2 s a poll that is tolerable.
- **Config loader**: one out-of-range field resets only that field (exp6b); the layout guard resolves symlinks before comparing.

## Disclosure

exp6 briefly created two empty directories outside the scratch area (`/mnt/raws`, `/mnt/lib`): the config loader's `ensure_dirs` created the folders named in my test config. I removed both with `rmdir` immediately; nothing else was touched, and `git status` on the repo is clean.
