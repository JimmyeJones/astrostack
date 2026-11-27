# AstroStack — working rules (1.0 era)

**Autonomous development ended on 2026-11-26.** The Builder/Scout playbook that
used to live here is archived in [`docs/archive/agent-era/`](docs/archive/agent-era/AGENTS.md),
together with its prompts and focus file. Work now happens in deliberate sessions
with the owner, milestone by milestone, following
**[`docs/ROADMAP-1.0.md`](docs/ROADMAP-1.0.md)** — read it first. The evidence behind
every roadmap item is the full audit in [`docs/audit/2026-11-26/`](docs/audit/2026-11-26/README.md).

`docs/IMPROVEMENTS.md`, `docs/SHIPPED.md` and `docs/PROCESS-NOTES.md` are frozen
history from the agent era: read them for context, add to them only what the docs
budget test needs, and do not treat them as a work queue.

The section numbers below are kept from the old playbook because code comments
cite them.

## §1 The owner

One non-technical owner. **His telescope is a ZWO Seestar S30** (150 mm, 2.1°,
one-shot-colour, alt-az). Where the model matters, derive it from the frame's own
`FOCALLEN`/`XPIXSZ` rather than assuming.

**His library:** ~105 targets and ~110k subs, some targets with tens of thousands.
He shoots many mosaics, so test mosaic-shaped and large-canvas cases, not only a
single field.

**His install:** TrueNAS/Docker, updated in place with the Settings → Update button
(which installs the `stable` branch). He has no darks or flats.

**The app stays local: no outbound network, ever.** A new offline Python
dependency needs his OK.

**The UI rule.** Nothing may be removed; reorganise instead. A page shows at most
five top-level things, and new features go inside an existing group.
`tests/test_ui_clutter_budget.py` enforces a per-route ceiling until M5 replaces
it with a rendered-page measure. Never game it: don't rename a component or move
it into a child file just to drop the count.

## §5 Definition of done

- The Python suite and (if you touched `frontend/`) `npx tsc --noEmit`,
  `npx vitest run` and `npx vite build`, run from `frontend/`, all pass. Never weaken,
  skip or delete a test to get green.
- **A bug fix gets a regression test that fails without the fix.**
- `__version__` in `webapp/__init__.py` is bumped from latest `main` (CI checks it).
- **Picture-changing work** ships with an old-vs-new comparison on the owner's own
  targets (roadmap R8), and becomes the default only after he picks it.

## §7 Environment

`source scripts/agent-setup.sh`, then follow
[`docs/AGENT-ENVIRONMENT.md`](docs/AGENT-ENVIRONMENT.md):
- redirect test output to a file;
- cap the BLAS threads and use xdist;
- never run `scripts/agent-dogfood.sh` at the same time as pytest.

## §8 Shipping

- Work on a branch, open a PR, and merge it when CI is green. **Never force-push `main`**,
  and never create or move tags (`release-tags.yml` does that).
- **`stable` moves only by running the "Release to stable" workflow**
  (`.github/workflows/stable.yml`) when a roadmap milestone is declared ready.

## §9 Backward compatibility — this is a live install

Every merge must be a safe in-place upgrade:
- the old `config.json` loads;
- database migrations are additive only;
- the on-disk layout is unchanged;
- no existing default flips silently.

Pattern: `tests/webapp/test_config_upgrade.py`.

## §10 Hard guardrails

- **🔒 `incoming/` is strictly read-only.** The owner's raw subs exist there and
  nowhere else, with no backup. The only permitted operations under it are read and
  create-new (uploads). No move, rename, delete, truncate, overwrite or cleanup,
  ever, by default or behind a setting. Ingest copies; it never moves.
- **The repository is public; his data is not.** Never reproduce:
  - his location (`SITELAT`/`SITELONG`, `site_lat`/`site_lon`);
  - other people's names;
  - host paths, LAN addresses, serials or Wi-Fi names;
  - his email address.

  Refer to paths as `$ASTRO/...` or `/data/...`.
- **Never set `git config user.name`/`user.email`.** `scripts/agent-setup.sh` pins the
  no-reply identity, and the pre-push hook and CI check it.
- **Never break the stack hot path's memory bounds** or NaN = "no coverage"
  semantics.
- **Never add a networked dependency** or make an irreversible change on your own.
