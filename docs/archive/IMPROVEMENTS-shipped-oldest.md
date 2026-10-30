# Backlog Shipped list — archive of the oldest one-liners

Moved verbatim and in order from the foot of the `## Shipped` list in [`../IMPROVEMENTS.md`](../IMPROVEMENTS.md),
oldest last, so the working list stays no longer than a run found it (AGENTS.md §2). Newer moves are appended
above older ones.

## Moved 2026-10-30 (Scout, branch `claude/exciting-wozniak-1xi45k`)

- **Integration time inline on History cards + Reuse settings from Gallery** —

## Moved 2026-10-23 (Scout, branch `claude/beautiful-newton-v9b2h7`)

- **Fix red CI (pytest-qt import crash)** — CI had been failing on every merge:

- **Integration time on Gallery cards** — stack runs now record their effective

## Moved 2026-10-21 (Scout, branch `claude/zen-curie-t3nyff`)

- **Reuse stack settings from a previous run** — new

- **Warn on a mismatched calibration master pick** — the Stack form now shows an

## Moved 2026-10-20 (Scout, branch `claude/zen-curie-ur5fu9`)

- **Auto-suggest a matching flat-dark** — `recommend_masters` now also returns

- **Drizzle flux-scale fix** — `DrizzleStacker.result()` no longer divides the

- **Auto-suggest calibration masters** — new `recommend_masters` ranks the

- **Stack info panel** — new `GET /stack-runs/{id}/info` reads the provenance

- `run_stack` edge-case tests — single accepted frame (degenerate stack, coverage

- Editor-export provenance — the derived `master.fits` from an editor recipe now

- Channel-combine provenance — the LRGB/RGB combined FITS now carries
- Accessibility sweep — added `aria-label` to the remaining icon-only
- Channel-combine NaN fix — LRGB pixels covered in G/B/L but uncovered in a
- **Flat-dark support** — a master flat can now be dark-subtracted before
- **Dashboard stats caching** — `GET /api/stats` no longer re-opens every target's
- **Settings backup & restore** — `GET /api/settings/export` downloads a portable
- **FITS output provenance headers** — `master.fits` now records OBJECT (target),
- CI safety net (`.github/workflows/ci.yml`) — full Python + frontend suites run

- **Autonomous run (agent, this session):** security fixes — Seestar `goto`
- **Autonomous run #1 (agent):** security + reliability/operability hardening +
- Autonomous dev playbook (`AGENTS.md`) + this backlog.
- Mono stacking + LRGB/RGB channel combine — `StackOptions.mono`, `channel_combine`,
- Star-mask-aware local edits — `edit/starmask.py`, mask-gated `stars.reduce`,
- Optional HTTP Basic access control (opt-in, PBKDF2, middleware). (v0.10.0, `7a995fc`)
- Dark/flat calibration — engine, master store, build job, API, UI. (v0.9.0)
- Keyboard shortcuts for frame grading on the Target page. (`2de2099`)
- Sigma-clip fix: no longer over-clips single-coverage (mosaic-edge) pixels. (`ab3883d`)
