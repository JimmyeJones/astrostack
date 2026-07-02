# AstroStack improvement backlog

Living backlog for the autonomous dev loop (see `AGENTS.md`). Each entry is
tagged with the pillar it serves (Reliability / Scale / Usability /
Operability / Security / Quality) and a size estimate (S = &lt;1hr, M = a few
hours, L = half day+). Newest shipped entries go at the top of "Shipped".
Items under "Needs owner sign-off" must not be started autonomously — see
`AGENTS.md` §9 for why.

## Shipped

- **[Security] Patch `react-router` open-redirect and `form-data`
  CRLF-injection CVEs** — S — `npm audit` in `frontend/` flagged
  `react-router`/`react-router-dom` (moderate: same-origin redirect with a
  `//`-prefixed path is reinterpreted as protocol-relative, enabling open
  redirect) and `form-data` (high: CRLF injection via unescaped multipart
  field names/filenames). Both fixed via a non-breaking `npm audit fix`
  (regenerated `package-lock.json`). Remaining `esbuild`/`vite`/`vitest`
  findings only affect the dev server, not the production build, and need
  a deliberate major-version bump — logged as a new backlog item below
  rather than force-fixed blindly. *(2026-07-02)*

- **[Security] Close the quick-look-preview gap in the `output_name`
  sanitizer** — S — the `output_name` sanitizer below (`_sanitize_basename`
  in `seestack/stack/output.py`) is only called inside
  `write_stack_outputs()`. `run_stack()`'s quick-look preview path
  (`_save_quick_look` in `seestack/stack/stacker.py`, periodic PNG saves
  during pass 1) builds its own filename from `options.output_name`
  independently and was still unsanitized. `run_stack()` now sanitizes
  `options.output_name` once, up front, before either path can use it.
  Covered by
  `tests/test_stack_pipeline.py::test_stack_sanitizes_path_traversal_output_name`
  (also updated `tests/webapp/test_editor.py`'s equivalent test — the editor
  export job now succeeds with a sanitized name rather than erroring, to
  match `_sanitize_basename`'s fix-it-not-fail-it approach). *(2026-07-02)*

- **[Reliability] `lucky_fraction` had no bounds validation** — S —
  `run_stack()` (`seestack/stack/stacker.py`) now raises `ValueError` up
  front if `StackOptions.lucky_fraction` isn't in `(0, 1]`. Previously 0
  silently fell back to keeping exactly one frame via `max(1, ...)`, and
  negative/`>1` values weren't rejected at all. Covered by
  `tests/test_stack_pipeline.py::test_stack_rejects_out_of_range_lucky_fraction`.
  *(2026-07-02)*

- **[Security] Validate Seestar `goto` RA/Dec coordinates** — S —
  `GotoRequest` (`webapp/routers/seestar.py`) forwarded `ra_hours`/
  `dec_deg` straight to the telescope's RPC with no bounds check. A
  malformed request now fails fast with a 422 (`Field(ge=0, lt=24)` /
  `Field(ge=-90, le=90)`) instead of being sent to hardware. (The
  overlapping `bayer` frame-preview finding from the same pass was
  already fixed upstream — see the entry below.) Covered by
  `tests/webapp/test_seestar.py::test_goto_rejects_out_of_range_coordinates`
  (+ a boundary-acceptance test). *(2026-07-02)*

- **[Usability] Silent job-cancel failures; Logs download ignored the
  active filter** — S — `Jobs.tsx`'s cancel mutation had no `onError`, so
  cancelling a job that had already finished (or any other failure) gave
  no feedback; added a notification and an `aria-label` on the icon-only
  cancel button. `Logs.tsx`'s download button built its file from the
  unfiltered `entries` while the UI badge showed the `filtered` count —
  a user who searched for something specific and hit Download got the
  whole log instead of what they were looking at; fixed to export
  `filtered`. Covered by `frontend/src/routes/Jobs.test.tsx` and
  `frontend/src/routes/Logs.test.tsx`. *(2026-07-02)*

- **[Usability] Confirm + surface errors on stack-run deletion** — S —
  `History.tsx`'s delete (trash icon) fired the mutation the instant it was
  clicked — no confirmation, and no `onError`, even though it permanently
  removes the run's FITS/TIFF/preview files. Added a `window.confirm`
  prompt and an `onError` notification, matching the pattern already used
  for destructive actions in `Storage.tsx`; also added the missing
  `aria-label` on the icon-only delete button. Covered by
  `frontend/src/routes/History.test.tsx`. *(2026-07-02)*

- **[Security] Validate the `bayer` query param on frame previews** — S —
  Found while replenishing the backlog. `GET .../frames/{id}/preview?bayer=`
  was free text that got embedded straight into the thumbnail cache filename
  (`cache_dir / f"web_..._{pattern}_v{THUMB_VERSION}.png"`). Because
  `Path.__truediv__` treats any `/` in that string as real path separators,
  a value like `bayer=../../../../x` builds a path outside the target's
  `cache/thumbs/`. The write side happens to be guarded today (an invalid
  pattern raises inside `bilinear_debayer` before anything is written), but
  the existence check (`if not out.exists(): ... else serve it`) runs
  *before* that guard, so a traversal value pointing at an existing file
  would be served back as-is — a latent read primitive that would also
  become a write primitive the moment that incidental downstream validation
  ever changes. Bayer patterns are inherently a 4-value enum
  (`RGGB`/`BGGR`/`GRBG`/`GBRG`), so `webapp/routers/frames.py` now validates
  at the router boundary and 400s on anything else, same fix shape as the
  `output_name` sanitizer. Covered by a new test in
  `tests/webapp/test_api.py`. *(2026-07-02)*

- **[Quality] Direct pixel-transform tests for editor ops** — M —
  `seestack/edit/ops/stars.py` (`stars.reduce`) had no test anywhere — its
  erosion-based star-shrink algorithm is implemented entirely in the editor
  op, not backed by a tested `seestack.bg`/`seestack.stars` module. The
  `background.*` ops do wrap already-tested `seestack.bg.*` functions, but
  the *wrapper* (recipe-params-dict → `Options` dataclass, the
  `ctx.coverage is None` early return in `level_coverage`) had no coverage of
  its own — a param-name typo or dropped field would pass every existing
  test. Added `tests/test_edit_ops_pixel_transform.py`: real pixel-behavior
  assertions for `stars.reduce` (shrinks a star core, leaves flat sky alone,
  `amount=0` is an exact no-op, NaN gaps survive), and wiring tests for the
  three `background.*` ops (params actually reach the underlying function,
  `level_coverage` is a no-op with no `ctx.coverage`). *(2026-07-02)*

- **[Usability] Surface fetch errors instead of spinning forever** — M —
  `Dashboard.tsx`, `Gallery.tsx`, `Library.tsx`, `Storage.tsx`, `Jobs.tsx`,
  `Sky.tsx`, `Logs.tsx` all gated rendering on `isLoading || !data` with no
  `isError` check, so a 500/network failure just spun the loader forever.
  Added a shared `QueryError` component (`frontend/src/components/`) and wired
  it into all seven routes; polling routes (Dashboard/Jobs/Logs) only swap to
  the error view when there's no cached data to keep showing, to avoid
  flicker on a single failed background poll. Sky Map keeps its own inline
  overlay alert (replacing the whole 3D canvas on a transient error would be
  worse than the loader gap it fixes). Covered by
  `frontend/src/components/QueryError.test.tsx`. *(2026-07-02)*

- **[Operability] Bound settings that could silently misconfigure the
  service, clamp `/api/jobs` `limit`** — S — `watch_quiet_period_s`,
  `watch_poll_interval_s`, `astap_timeout_s`, `cpu_workers`,
  `seestar_scan_interval_s`, `seestar_poll_interval_s` in `webapp/config.py`
  had no bounds, so `PUT /api/settings` could accept e.g. `astap_timeout_s: 0`
  (every plate-solve fails instantly) or `cpu_workers: 0` (crashes the
  pool). Added `Field(ge=..., le=...)` constraints, plus a `ValidationError`
  → `422` handler in `webapp/routers/settings.py` (previously an
  out-of-bounds/invalid patch would 500). Also clamped `GET /api/jobs`
  `limit` to match the existing `/api/logs` pattern. Covered by new tests in
  `tests/webapp/test_api.py`. *(2026-07-02)*

- **[Reliability] Consistent 404s for unknown targets on merge/delete** — S —
  `POST /api/targets/merge` raised an uncaught `FileNotFoundError` (500) when
  `into` didn't resolve; `DELETE /api/targets/{safe}` silently returned
  `200` for a target that never existed (`Library.delete_target` was a
  no-op on a miss). `merge_targets` now catches and maps to 404;
  `delete_target` now returns whether it found something, and the router
  404s when it didn't. Covered by three new tests in `tests/webapp/test_api.py`.
  *(2026-07-02)*

- **[Security] Sanitize `output_name` before it reaches the filesystem** — M —
  `output_name` (stack options + editor export/batch requests) flowed
  unvalidated into `out_dir / f"{out_basename}.fits"` in
  `seestack/stack/output.py`. A value like `"../../../etc/x"` or `"/etc/x"`
  could write stack outputs outside the target's `output/` directory. Added
  `_sanitize_basename()` — a single choke point used by both the stack
  pipeline and the editor export/batch paths (and the desktop GUI) — that
  strips anything but `[A-Za-z0-9._-]`, collapses leading/trailing separators,
  and falls back to `"master"` if the result is empty. Covered by
  `tests/test_output_sanitize.py` (unit tests on the sanitizer + an
  integration test proving `write_stack_outputs` can't escape
  `<project>/output/`). *(2026-07-02)*

## Backlog

- **[Operability] `GET /api/stats` re-opens every target's SQLite project on
  every 10s Dashboard poll** — M — `webapp/routers/stats.py` (`get_stats`)
  opens a `Project` for *every* target and iterates *all* of its stack runs
  just to compute `n_stack_runs` and pick the newest `recent_limit` (default
  8) — then `Dashboard.tsx` polls this endpoint every 10 seconds
  (`refetchInterval: 10_000`) for as long as the dashboard tab is open. At a
  handful of targets this is unnoticeable; at dozens of targets with years of
  re-stacks (this app makes re-stacking cheap, so run counts grow) it's
  continuous, compounding I/O for a number that barely changes between polls.
  Fix shape: track `n_stack_runs` and the N most-recent runs incrementally
  (e.g. a small "recent stacks" table/index in the registry DB, updated when
  a stack run is written) instead of a full re-scan every poll — or at minimum
  cache the aggregate for a few seconds server-side. `GET /api/gallery`
  (`webapp/routers/gallery.py`) has the identical open-every-project pattern
  but is only fetched on-demand (page visit), so it's lower urgency — worth
  fixing in the same pass since the query pattern would be shared.

- **[Scale] Frame listing loads + sorts the whole table in Python** — M —
  `GET /api/targets/{safe}/frames` (`webapp/routers/frames.py`) materializes
  every frame via `proj.iter_frames(...)` (unbounded `SELECT * ... ORDER BY
  id`, `seestack/io/project.py`), then sorts the full list in Python and
  slices for pagination. Fine at hundreds of frames, wasteful at the 10k-frame
  scale this project is built for. Push `ORDER BY <col> LIMIT/OFFSET` into
  SQL with an index on the sortable columns (`fwhm_px`, `star_count`,
  `sky_adu_median`, `eccentricity_median`, `timestamp_utc`).

- **[Operability] `jobs.sqlite` has no retention/pruning policy** — S —
  `webapp/jobs.py` writes every completed job (ingest/QC/solve/stack/editor
  batches — anything the watcher or a user triggers) to `state/jobs.sqlite`
  forever; there's no delete/prune path anywhere in the module. This app is
  built to run unattended and always-on against a NAS dataset (see
  `docs/webapp.md`), so over months of watcher-driven auto-processing the
  table only grows. Not urgent (SQLite handles this size fine and `list()`
  is already `LIMIT`-bound), but worth adding a simple age- or count-based
  prune (e.g. keep the last N terminal jobs, or terminal jobs older than N
  days) run opportunistically on startup or after each job completes.

- **[Quality] Thin API test coverage on target CRUD + stack history** — M —
  `tests/webapp/test_api.py` is ~115 lines / 10 tests covering
  `targets.py` + `frames.py` + `stack.py` + `settings.py` + `system.py`
  combined; it never exercises `create_target`, `merge_targets`,
  `delete_target`, `patch_target`, the target thumbnail endpoint, or stack
  history/download/render/delete. Add targeted tests per endpoint (basic
  `delete_target`/`merge` coverage landed with the 404 fix above; still
  missing: `create_target`, `patch_target`, thumbnail, stack history/download/
  render/delete).

- **[Usability] Frontend bundle has no code-splitting on Sky/Aladin** — M —
  `npm run build` warns that `assets/aladin-CKJvJOV6.js` (2.4 MB) and
  `assets/Sky-*.js` (850 KB) are both eagerly bundled into the main chunk
  graph. The Sky Map is one route among many; dynamic `import()` for the
  Aladin Lite dependency (only needed when a user opens Sky Map in "real sky"
  mode) would cut initial load weight for everyone who never opens that page.

- **[Quality] ~127 pre-existing `ruff check .` findings** — L — Mostly
  mechanical (`UP035`/`UP017` typing-import modernization, missing
  `zip(..., strict=)`, etc.) but spread across many files; not currently
  blocking anything. Worth a dedicated cleanup pass with `ruff check --fix`
  plus manual review of the unsafe-fix set, run as its own isolated PR so a
  bad auto-fix is easy to bisect.

- **[Operability] `vite`/`vitest`/`esbuild` dev-toolchain has known CVEs**
  — M — `npm audit` (after the `react-router`/`form-data` fix shipped this
  run) still reports esbuild ≤0.24.2 (moderate: the dev server accepts
  requests from any website) via `vite` ≤6.4.2 → `vitest` ≤3.2.5. Only
  exploitable while running `npm run dev`, not in the production build
  served by `webapp/`, so it's not urgent — but `npm audit fix --force`
  wants to jump to `vite@8`, a real major-version bump across the vite/
  vitest toolchain (config changes, full test-suite re-verification), so
  per `AGENTS.md` §9 ("major version bumps of core deps") this needs a
  deliberate dedicated pass, not a blind `--force` in an automated run.

- **[Operability] No CI workflow** — M — there is no `.github/workflows/`
  (or equivalent) in this repo; the Python `pytest` and frontend
  `vitest`/`build` gates only run when a human or the autonomous loop
  happens to run them locally. Adding a workflow that runs the same
  commands as `AGENTS.md` §7 on every push/PR would catch regressions
  immediately instead of at the next hourly run. Purely additive (a new
  workflow file), no risk to existing behavior.

- **[Usability] Icon-only buttons missing `aria-label`** — M — repo-wide
  sweep of `frontend/src/routes/*.tsx` and `components/*.tsx`; only a
  handful of `aria-label`/`role`/`alt` attributes exist across all routes
  (a few landed incidentally with the `History.tsx`/`Jobs.tsx` fixes
  above), so most icon-only actions (delete, cancel, download, edit) are
  unlabeled for screen-reader users. Do as one focused sweep with a small
  test asserting known icon buttons have accessible names.

- **[Reliability] Seestar client has no reconnect/retry on dropped TCP**
  — M — `webapp/seestar/client.py` has no backoff/retry on socket drop;
  a flaky Wi-Fi link to the scope currently requires the user to manually
  reconnect via the UI. This is the core hardware-integration path for
  live monitoring/control, so it's worth a dedicated pass — needs care
  around not spamming reconnect attempts, and the retry/backoff logic
  should be testable in isolation from real hardware.

## Needs owner sign-off

(Nothing queued right now — see `AGENTS.md` §9 for the standing list of
categories that always require a human decision before starting: on-disk
schema changes, auth additions, new outbound network deps, destructive-default
changes, major dependency bumps, Seestar protocol changes without a
verification harness, and deployment topology changes.)
