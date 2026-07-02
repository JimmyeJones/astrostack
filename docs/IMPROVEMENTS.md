# AstroStack improvement backlog

Living backlog for the autonomous dev loop (see `AGENTS.md`). Each entry is
tagged with the pillar it serves (Reliability / Scale / Usability /
Operability / Security / Quality) and a size estimate (S = &lt;1hr, M = a few
hours, L = half day+). Newest shipped entries go at the top of "Shipped".
Items under "Needs owner sign-off" must not be started autonomously — see
`AGENTS.md` §9 for why.

## Shipped

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

- **[Reliability] `POST /api/targets/merge` 500s instead of 404 on unknown
  `into`** — S — `Library.merge_targets` raises a bare `FileNotFoundError`
  when the `into` target doesn't resolve; `webapp/routers/targets.py` doesn't
  catch it, so the client sees an unhandled 500 with a stack trace instead of
  a clean 404. `create_target` already has the right pattern to copy.

- **[Reliability] `DELETE /api/targets/{safe}` returns 200 for an unknown
  target** — S — `Library.delete_target` is a silent no-op when the entry
  isn't found (`seestack/io/library.py`), so the router still returns
  `200 {"deleted": ...}` for a target that never existed. Misleading for
  scripted cleanup; should 404 like the sibling endpoints. (Pairs naturally
  with the merge-target 404 fix above — same PR, same pattern.)

- **[Usability] List/dashboard routes don't surface fetch errors** — M —
  `Dashboard.tsx`, `Gallery.tsx`, `Library.tsx`, `Storage.tsx`, `Jobs.tsx`,
  `Sky.tsx`, `Logs.tsx` all gate rendering on `isLoading || !data` and never
  check `query.isError`, so a 500/network failure just spins the loader
  forever instead of showing an error state. `Editor.tsx` and `AladinSky.tsx`
  already handle this correctly — extract their pattern into a shared
  component/hook and apply it to the rest.

- **[Operability] Settings numeric fields have no bounds** — S —
  `watch_quiet_period_s`, `watch_poll_interval_s`, `astap_timeout_s`,
  `seestar_poll_interval_s`, `seestar_scan_interval_s`, `cpu_workers` in
  `webapp/config.py` are plain `int`/`float` with no `ge=`/`le=` constraints.
  `PUT /api/settings` currently accepts e.g. `astap_timeout_s: 0` (every solve
  instantly times out) or a negative `cpu_workers`. Add `Field(ge=..., le=...)`
  constraints matching sane operational ranges.

- **[Operability] `GET /api/jobs` has no upper clamp on `limit`** — S —
  Unlike `/api/logs` (clamped to 5000 in `webapp/routers/logs.py`),
  `list_jobs` in `webapp/routers/jobs.py` passes a caller-supplied `limit`
  straight into the SQL `LIMIT ?` with no ceiling. Add the same clamp pattern
  used in `logs.py`.

- **[Scale] Frame listing loads + sorts the whole table in Python** — M —
  `GET /api/targets/{safe}/frames` (`webapp/routers/frames.py`) materializes
  every frame via `proj.iter_frames(...)` (unbounded `SELECT * ... ORDER BY
  id`, `seestack/io/project.py`), then sorts the full list in Python and
  slices for pagination. Fine at hundreds of frames, wasteful at the 10k-frame
  scale this project is built for. Push `ORDER BY <col> LIMIT/OFFSET` into
  SQL with an index on the sortable columns (`fwhm_px`, `star_count`,
  `sky_adu_median`, `eccentricity_median`, `timestamp_utc`).

- **[Quality] Editor pixel ops have no direct unit tests** — M —
  `seestack/edit/ops/stars.py` (`stars.reduce`) and
  `seestack/edit/ops/background.py` (`subtract`, `final_gradient`,
  `level_coverage`) are only exercised indirectly through generic
  recipe-pipeline tests in `tests/test_edit_engine.py`; nothing asserts their
  actual pixel transform on a synthetic input (e.g. that `background.subtract`
  measurably flattens a synthetic gradient). A regression in the transform
  math itself could pass CI silently.

- **[Quality] Thin API test coverage on target CRUD + stack history** — M —
  `tests/webapp/test_api.py` is ~115 lines / 10 tests covering
  `targets.py` + `frames.py` + `stack.py` + `settings.py` + `system.py`
  combined; it never exercises `create_target`, `merge_targets`,
  `delete_target`, `patch_target`, the target thumbnail endpoint, or stack
  history/download/render/delete. Add targeted tests per endpoint (natural
  follow-on once the 404-handling fixes above land, so the new tests assert
  the corrected behavior).

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

## Needs owner sign-off

(Nothing queued right now — see `AGENTS.md` §9 for the standing list of
categories that always require a human decision before starting: on-disk
schema changes, auth additions, new outbound network deps, destructive-default
changes, major dependency bumps, Seestar protocol changes without a
verification harness, and deployment topology changes.)
