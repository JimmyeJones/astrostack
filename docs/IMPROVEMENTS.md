# AstroStack improvement backlog

The shared blackboard for autonomous development. Read
[`../AGENTS.md`](../AGENTS.md) first — it defines the loop, the decision
framework, and the guardrails. This file is *what* to build; AGENTS.md is *how*.

> **Current focus (re-cut 2026-09-07 to match AGENTS.md §1; the 2026-07 text below it was
> stale twice over).** The single-field stacking-engine core (`seestack/stack/*`,
> `seestack/calibrate/*`) has passed **twenty clean sweeps** and is **closed until a new bug is
> found there — do not re-sweep it**. The open frontier is **mosaic-scale and walk-away behaviour
> of the Auto/editor path**: every Auto/editor claim is judged on a tiled mosaic canvas at the
> owner's scale, never on the 6-frame sample (D1 hid there through three audits). After that:
> autonomy, friendliness and image quality (priorities 2–4). Fix any real editor regression first;
> favour these areas when picking *new* work. **Ready-to-build entries are marked `READY` — grep for it.
> Both `⭐ READY — GATE OPEN` items have now shipped (the editor auto-seed v0.390.0, the `auto_stack` default
> flip v0.391.0), so there is no starred queue left — pick from `READY` and from the priority sections.
> Every gate that needs the owner is in one list at the top of "Needs owner sign-off".**

**Conventions**
- **This file is the WORKING LIST. A run must leave it no longer than it found it,**
  unless it is filing a verified bug (AGENTS.md §2, "the three-file rule"). When an
  item ships or is closed, **cut the entry** and append it to
  [`SHIPPED.md`](SHIPPED.md), leaving a one-line `✅ v0.xxx.y <what>` under
  "Shipped" here. Process notes, collision diaries and QA sweep records —
  **including clean ones** — go to [`PROCESS-NOTES.md`](PROCESS-NOTES.md), never
  into a priority section. Delete an "In progress" claim when you release it.
  *(Added 2026-09-04. The file grows ~100 lines per merged PR — 18,757 on 08-01,
  34,934 on 09-02, 41,038 on 09-04 — so no agent can read it in a run, and every
  agent is necessarily skimming. That is the common cause behind stale entries
  surviving, ideas being re-derived, and items being built twice.)*
- Sections: **Bugs (fix these first)** → **In progress** → **Ideas** (roughly
  prioritised) → **Shipped** → **Needs owner sign-off**.
- Two kinds of agent share this list (see AGENTS.md "Agent roles"): the **Builder**
  *drains* it (implements + ships the top items), and the **Scout** *fills* it
  (files verified bugs, curates priorities, adds ideas). Claim any item you start by
  moving it to **In progress** with your branch name, in the same commit that starts
  it. Move it to **Shipped** (with the commit/PR) when done, or back to **Ideas** if
  you abandon it.
- **Scout — replenish and curate.** Each Scout run: file the bugs you verified into
  "Bugs (fix these first)" (symptom + location + repro + severity + confidence),
  reprioritise, prune done/stale/duplicate items, and add a few well-reasoned ideas
  (AGENTS.md §4) — but only ones that serve the **§1 priorities** (1 editor,
  2 autonomy, 3 friendliness, 4 image quality), each tagged with a size (S/M/L) and
  its priority. Do **not** log niche mono/LRGB/channel-combine/narrowband ideas.
- **Builder — bugs and leads only.** A Builder files a bug it verified itself and a
  lead it could not finish; it does not invent features to stay busy (AGENTS.md §4).
  If ready work is genuinely thin, dogfood the app (§2) and file what you find — an
  idle run that leaves `main` green is a success.
- **Priority order (from AGENTS.md §1) governs this list.** Work the top sections
  first. The editor is priority 1.
- **A shipped item's spec belongs in `SHIPPED.md`; until it is moved, keep it
  *indented*.** The cut above is the rule; this is the fallback for the inline
  "✅ SHIPPED" entries still sitting under "Ideas", and for the moment between
  shipping and moving. *(The "Bugs" half of that backlog is done — 227 resolved
  entries and 24 sweep records were cut on 2026-09-05; "Ideas" is what is left.)*
  Strike the headline,
  write the SHIPPED paragraph, and keep the original spec **as an indented
  continuation** (two spaces), never as a fresh top-level `- **…**` bullet. A
  top-level copy is indistinguishable from open work: every
  way an agent triages this file — reading a section, or grepping `^- \*\*` for
  unclaimed items — surfaces it as a live idea, and runs have been spent
  re-picking features that shipped months earlier. Indented, the "is this open?"
  question is answerable by shape alone.

---

## In progress

> **This section holds *live* claims only — nothing else.** Claim an item by adding
> one line here with your branch name, in the same commit that starts the work;
> **delete that line** when you release the claim (§11). Everything a finished run
> wants to say goes in `docs/PROCESS-NOTES.md`, not here.
>
> *(Emptied 2026-09-04. It had grown to 420 lines in which **every** header said "claim
> released" or "run finished" — a diary, not a claim board, and the one section
> whose whole value is being short. The diary moved verbatim to
> [`PROCESS-NOTES.md`](PROCESS-NOTES.md); nothing was deleted.)*

*No live claims.*

---

## Bugs (fix these first)

- **LEAD, MEASURED (Builder 2026-09-25, filed while shipping v0.475.0 — the one thing that fix measured and
  deliberately did not change) — the reveal's two sides are not identically sampled when the master is
  drizzled, so part of the "stacking cut your noise ~N×" number is the drizzle kernel rather than the
  stacking.** *(Pillar: trust — PRIORITY 1-adjacent; size **S to decide, M to be sure of**; severity low —
  the number is now physically honest about the pixels it measures, and the question is whether those are the
  pixels the sentence is about. Confidence: **measured this run** against ground truth on a real
  debayer+warp+drizzle fixture; how often the owner's runs drizzle is **not** measured.)*
  `_measure_noise_ratio` reads the sub at native resolution and the master at **its own**, and the module
  docstring's "Identical sampling" rule is exactly about not doing that. On a 2× drizzle the master's pixels
  cover a quarter of the area, and the warp + kernel smooth them, so its per-pixel σ falls **further** than
  averaging alone can explain: ground truth on the v0.475.0 fixtures is a ratio of **7.88** on a 2×-drizzled
  master against **6.98** native, for the identical 36 frames and a √N of 6.00. No information is gained —
  the pixels are smaller and correlated — but ~13 % of the drizzled badge is resampling.
  **Do not "fix" this by re-inflating the estimator**: v0.475.0's numbers are correct *for the pixels the
  master has*, and `tests/test_noise_ratio_correlated.py` pins them against ground truth. The question is a
  design one — should the comparison be pixel-**area**-matched (bin the master down by the drizzle scale
  before measuring, so both sides describe one patch of sky), and if so what does the √N yardstick then mean?
  **Check first, cheaply:** what share of the owner's runs actually drizzle, and at what scale. If most are
  1×, this is a footnote and should be **closed with the number** rather than built.

- **LEAD (Builder 2026-09-25, filed while shipping v0.473.0 — the observer's second point in issue
  [#966](https://github.com/JimmyeJones/astrostack/issues/966), which that fix deliberately did not touch) —
  a reprocess batch prices every target against a budget that is 70 % of *whatever RAM is free at the minute
  that target comes up*, so which mosaics survive a five-day batch is a property of the host, not of the
  picture.** *(Pillar: trust + autonomy — PRIORITY 2; size **S to write, M to be sure of**; severity low now
  that v0.473.0 makes the batch degrade rather than refuse. Confidence: **mechanism traced**; the owner-side
  observation is the observer's.)*
  `webapp.pipeline`/`stacker._stack_memory_budget_bytes` falls through to a live free-memory read when
  `max_stack_memory_gb` is unset in the config and `ASTROSTACK_MAX_STACK_GB` is not exported — which is the
  owner's state. The observer saw the *same target* priced against a **~4.1 GB** budget in one batch and a
  **~3.2 GB** budget in the next, so the same subs and the same options produced a different answer a week
  apart with nothing about the data changed.
  **Why it is smaller than it was.** Before v0.473.0 that decided *picture or no picture*. It now decides how
  far the drizzle scale steps down, so the failure mode is a mosaic that is quietly less zoomed-in on one batch
  than on another — real, but not a hole in the library.
  **The shape worth costing:** capture the budget **once** at the start of a batch and price every target in it
  against that one number, so a refusal (or a step-down) is a property of the canvas rather than of the minute.
  **Check first, because it cuts both ways:** a budget captured when the box happened to be busy would then hold
  down *every* target in a five-day batch, including the ones that would have fit comfortably an hour later.
  A floor (never price below what the run would have got at, say, the median of a few samples) is probably part
  of any workable answer. **Do not blind-flip the guard's source** — it is the on-by-default hot path and this
  box has an OOM history (§10).

- **LEAD (Builder 2026-09-25, filed while shipping v0.473.1 — the two halves of observer issue
  [#965](https://github.com/JimmyeJones/astrostack/issues/965) that fix deliberately left) — refuse an
  implausible solve at *solve* time, and heal the rows already carrying one.** *(Pillar: image quality —
  PRIORITY 4; (a) **M**, (b) **S to write, M to be sure of**; severity low now that the stack drops them.
  Confidence: both mechanisms traced in the code; the re-solve cost is **not** measured, which is why (a) is a
  lead.)*
  **(a) The solve-time refusal, which is what the issue itself suggests.** Every sub carries `FOCALLEN` and
  `XPIXSZ`, and `fits_loader.fov_deg_from_header` already derives the expected scale from them to give ASTAP its
  own FOV hint — so `solve.runner.apply_solve_result_to_db` could refuse to store a solve whose scale is more
  than ~1 % from the frame's own optics, the way it already refuses an unreadable sidecar. That is prevention at
  the point the bad row is created, and it is *header*-derived rather than population-derived, so it works on a
  target with only a handful of subs where v0.473.1's consensus bar is silent by design.
  **What has to be settled first, and it is not the threshold.** A frame stored with a `solve_failed:` reason
  and no `wcs_json` is **re-offered on every scan** (`build_solve_arglist` deliberately keeps offering them,
  because most solve failures are transient). The observer's own control says the flake is not deterministic —
  the same bytes solved correctly on the other attempt — so a retry is genuinely likely to succeed, which is the
  argument *for*. The argument against is the bill on a walk-away box: 178 frames × a ladder that can burn up to
  3× `astap_timeout_s` (see the `astap_timeout_s` entry below) is hours per scan, on exactly the nights the
  owner walked away. **Measure the retry-success rate before building it**, or give the refusal its own
  non-retrying mark and accept that a genuinely transient flake then needs a manual re-solve.
  **(b) Healing the rows that already carry a bad WCS.** v0.473.1 catches them the next time the target is
  stacked — which is how they will in fact be caught, since the owner reprocesses — but nothing surfaces the
  178 until then. A read-only pass that counts them per target (the same median-and-consensus rule, no writes)
  would at least let the Target page say so. Keep it read-only: clearing a stored `wcs_json` outside the solve
  path is the thing that turns (b) into (a)'s re-solve bill without (a)'s decision.
  **(c) ~~`n_roughly_aligned` is NULL on all 690 of the owner's stack runs~~ — ⚪ CLOSED WITH THE GREP, and
  it was never going to show any of this** *(Builder 2026-09-26, while shipping v0.475.3 — the grep this
  point asked for, done)*. The column **is** written: `stacker` stamps `NROUGHAL` and persists
  `n_roughly_aligned` under `eff.subpixel_refine and not eff.drizzle and refine_active`, deliberately
  omitting it otherwise so that "absent" reads as *"refine didn't run"* rather than a reassuring zero. It is
  NULL on all 690 because **`StackOptions.subpixel_refine` defaults `False`** and nothing turns it on — it is
  a hand-set **advanced** field on the Stack form (`schemas.py`), so every one of those runs had refine off,
  and NULL is the correct record. **And the premise under it is wrong too:** "roughly aligned" is the
  *refine* step's own cap being exceeded (`align.align_one`'s `roughly_aligned_ids`), not a wrong-scale plate
  solve — a frame with an implausible WCS reprojects at the wrong scale, which is what v0.473.1 now catches;
  it does not read as "rough". So this column would have been silent on the 178 frames even with refine on.
  Nothing to build here. *(The one thing that did come out of the grep is a separate, shipped bug: the
  `soft_stars` health note was prescribing those non-existent subs to the reader — v0.475.3.)*

- ~~**🟠 BUG (autonomy / library hygiene, Builder 2026-09-17, reproduced before it was fixed) — a folder of
  darks under `incoming/` becomes a light target, in the one place the app itself told the owner to put
  them.**~~ — **✅ SHIPPED v0.455.0.** Entry cut to [`SHIPPED.md`](SHIPPED.md), one-liner under "Shipped".
  The short version, kept here only because the *class* is worth remembering: the Calibration page's build
  form is placeheld `/data/incoming/darks` and asks for "a Seestar `Dark` folder on your NAS", and
  `GET /api/calibration/incoming` is a whole feature premised on calibration folders living under
  `incoming/` — while `seestack/io/scanner.py` had no notion of a calibration frame at all, so exactly those
  folders were ingested as targets ("Darks 10s", 6 lights, on the Library wall, in the campaign stats, in the
  planner, chipped "Not stretched yet", stackable). Two halves of one app disagreeing about what the same
  files are. Fixed by giving the scan `discover.classify_frames` — literally the rule the build offer is
  decided by — so the set the offer lists and the set the scan passes over are one set by construction.

- ~~**🟠 BUG (image quality + trust, Builder 2026-09-18, reproduced before it was fixed) — a target is not
  necessarily one exposure, and the master-dark advisory assumed it was: the same subs, the same dark, and
  the app either warned or said nothing depending on which frame was picked as the reference.**~~ —
  **✅ SHIPPED v0.456.0.** Entry cut to [`SHIPPED.md`](SHIPPED.md), one-liner under "Shipped". The short
  version, kept here only because the *class* is worth remembering: `stacker.run_stack` asked
  `CalibrationMasters.calibration_warnings` about `ref.exposure_s` — the **reference frame's** exposure —
  with a comment saying it "stands in for the (uniform) session". Nothing makes a session uniform: shoot a
  target at 10 s one night and 30 s the next and it is one target with two exposures in it. Then
  `pick_reference_frame`, which chooses on quality and pointing and has never heard of exposure, silently
  decided whether the advisory fired at all — and when it did fire it said the pedestal was wrong "on every
  frame", which was false for the subs the dark actually matched. Reproduced on a real `run_stack`:
  `calibration_warnings == []` on a 6-sub target (four at 10 s, two at 30 s) with a 10 s dark, while the
  30 s subs got that dark subtracted **unscaled**. The class: *a representative value is a claim that the
  set is uniform, and nothing in the data enforces it.* Sibling surfaces that take the same shortcut, in
  case a future run is in them: `pipeline._auto_bind_for_target` and `routers/calibration.py`'s
  `calibration-suggestions` both take the **median** exposure.

- **LEAD (Builder 2026-09-19, filed while shipping v0.468.0 — the half of that fix that reaches the
  *unattended* path, and the one an agent should not blind-build) — the auto-binder judges a master dark by
  its stamped (median) temperature and its own median gain, so exactly the master v0.468.0 exists to warn
  about auto-binds as a perfect match, with nobody there to read the warning.** *(Pillar: autonomy —
  PRIORITY 2; size **M to write, L to be sure of**; severity low-to-medium; confidence: **mechanism traced
  and arithmetic-checked in the code**, the tradeoff **not** measured — which is why this is a lead.)*
  **What is traced.** `webapp/calibration._match_distance` scores a master on `master["sensor_temp_c"]`
  alone — the median v0.468.0 has just shown can be a temperature no frame in the master was shot at — and
  `_dark_match_confident` / `_flat_match_confident` / `_bias_match_confident` gate on that same distance. So
  a dark built across 25 °C whose median happens to land on the target reads as distance 0.0, is bound by
  `auto_bind_master_ids`, and the run's advisory (which now does say so, v0.468.0) is the only trace — on a
  walk-away night nobody reads it. Separately, `pipeline._confident_master_binding` passes
  `gain=_med(...)` and `sensor_temp_c=_med(...)`: the **exposure** half was fixed in v0.457.0 by handing the
  binder the whole set (`light_exposures_s` + `distinct_exposures`), and gain and temperature were not. On an
  evenly-split two-gain target the median is a gain *neither* population was shot at (80 and 200 → 140), and
  both failure directions follow from it — a gain-80 dark matching most of the subs is judged against 140 and
  **refused**, or a gain-140 dark matching none of them is judged against 140 and **bound**.
  **Why it was NOT built this run, and what has to be settled first.** The obvious fix — charge a blended
  master its own half-range as extra distance, which is literally true ("this master's temperature is only
  known to ±half its range") — is *not* additive, because `_match_distance` feeds the **confidence gate** and
  `master_coverage`'s "which targets does this cover" page as well as the ranking. Raising a distance can
  therefore flip a bind into a refusal, i.e. strip calibration from a target that has it today. And that is
  the tradeoff this repo cannot settle: `auto_bind_master_ids`' own contract says "leave it uncalibrated
  rather than risk anything", while v0.457.0's reasoning says the opposite for the mixed case ("stripping
  calibration from a target that is mostly one length is worse than the mismatch on the minority"). **A
  blended dark still removes most of the pedestal and most of the hot pixels**, so refusing it may well be
  the worse answer, and which it is depends on how wide the blend is — a number nobody has from the owner's
  library. **Do not blind-flip it.** The shapes worth costing, cheapest first: **(a)** leave binding alone
  and make the *choice* prefer an unblended master only as a **tie-break** (equal distance → narrower range
  wins), which can never strip anything; **(b)** hand the binder `light_gains` / `light_temps_c` the way
  v0.457.0 handed it `light_exposures_s`, so it judges against the **dominant** value rather than a phantom
  median — that one is a strict improvement in both directions and is probably the right first slice;
  **(c)** the half-range charge, only with a before/after on real masters. (a) and (b) are independent of
  each other and of (c).
  **✅ (a) SHIPPED v0.469.1, built exactly as the shape describes.** New `calibration._temp_range_span` +
  `_match_rank`: the order masters are tried in is now `(match distance, temperature span)`, so among masters
  the acquisition numbers cannot separate, the one that was actually shot at the temperature it is stamped
  with beats one that merely averages to it. **Not** a distance term, deliberately — `_match_distance` also
  feeds the confidence gates and `master_coverage`, so charging a blended master extra distance is the thing
  the lead says could strip calibration off a target that has it today. A tie-break can only reorder two
  masters that are already level. Applied at all four places that rank (`recommend_masters`,
  `auto_bind_master_ids`' dark/flat/bias candidate sorts, `_recommend_flat_dark`, `existing_master_like`) and
  at none of the three that gate. One-sided like everything else here: a master built before v0.468.0 recorded
  no range, scores 0 and keeps its place. **What is still open is (c)**, unchanged and still gated on a
  before/after against real masters.
  **✅ (b) SHIPPED v0.469.0 — the gain half only; read what was deliberately left out.** New pure
  `apply.dominant_gain` (sharing `distinct_gains`' own grouping via `_gain_groups`, so "is this a second
  setting?" still has one answer) now supplies the representative gain to all three places that took a median
  of it — `pipeline._confident_master_binding`, the Stack form's `calibration-suggestions`, and the coverage
  roll-up's target signature — so the page, the form and the walk-away run cannot describe one target three
  ways. The lead's arithmetic was reproduced as the regression test: two darks at gain 80 and gain 140, subs
  split 3/3 between 80 and 200, and the gain-140 dark that matches **none** of them wins on the old median.
  **The temperature half (`light_temps_c`) was considered and deliberately not built**, and that is a
  judgement rather than an omission: a gain is a discrete *setting*, so a midpoint between two of them is a
  value the camera was never at — a temperature is continuous and a Seestar's sensor is uncooled, so a value
  between two nights' readings is one the sensor really passed through. There is no "dominant" temperature to
  reach for, and `apply.py`'s own constant comment already argues the same way (*"a temperature… earns a
  tolerance wide enough to cover a night"*). Re-open it only with a shape that is not "the mode of a
  continuous quantity".

- **LEAD (Builder 2026-09-19, filed while shipping v0.470.0 — the one thing in that fix that is a *proxy*
  rather than a measurement, and I knew it when I shipped it) — the app decides "ragged rim or under-shot
  panel?" from a share it did not measure for that question, and on a mosaic that is both, the rim wins.**
  *(Pillar: friendliness / trust — PRIORITY 3; size **S to write, M to be sure of**; severity low;
  confidence: **the proxy and its failure direction are traced in code**, how often the ambiguous shape
  occurs on the owner's library is **not** measured — which is why this is a lead.)*
  **What shipped and why.** v0.470.0's grain note has to choose between two opposite prescriptions about one
  thin region: *"another night on that panel"* and *"Trim border crops the worst of it away"*. It chooses
  with `stackhealth.has_ragged_border`, i.e. `coverage_thin_frac >= _COVERAGE_THIN_SHARE` — deliberately the
  ragged-border note's **own** condition, so the two notes on one card cannot disagree, which was the whole
  point. That was the right call for the fix: it needed no new column, no migration and no new threshold.
  **What it is not.** `coverage_thin_frac` answers *"how much of this canvas is under a quarter of one
  panel's depth?"* — a question about **amount**, not about **place**. The thing being inferred is
  geometric: is the thin region the canvas's perimeter, or an interior panel nobody has finished? The
  observer's own discriminator for that is a **distance transform of the covered footprint normalised by its
  maximum inscribed radius** (0 % of thin pixels beyond half that radius on all 22 of the owner's mosaics,
  the same as on the single-field controls), which is cheap (`scipy.ndimage.distance_transform_edt`, already
  a dependency) and definitive where the share is circumstantial.
  **The failure direction, stated so nobody has to re-derive it:** a mosaic that has *both* a ragged union
  rim **and** a genuinely under-shot interior panel takes the rim branch, so the owner is told to trim when
  the more useful answer was to go and shoot that panel — and the grain note is the one surface that would
  have said so (the panel map says *where*, but it is a different card). The reverse cannot happen: without
  a rim the note keeps the sentence it has always had.
  **Why it was not built.** It needs the interior fraction carried onto the run to be read at note time, and
  `stack_runs` has no column for it — so it is an additive migration plus a `coverage_backfill` pass, which
  is the right shape for a *measured* answer and far too much for an inference the card already makes
  coherently. **Check first, before building any of it:** how often does the owner's library actually hold a
  mosaic that is both? If the answer is "rarely", the proxy is good enough and this should be **closed with
  the number** rather than built. If it is built, put the fraction behind the same lazy backfill the grain
  columns already use, default it to "unknown" (never to 0.0, which would read as "all rim"), and keep
  `has_ragged_border` as the fallback for every run recorded before it existed.

- **LEAD, MEASURED (Builder 2026-09-19, filed with v0.471.2/v0.471.3 — the readers of the same class those two
  fixes deliberately did NOT take, because each needs an *engine* signature decision rather than a router-local
  edit) — three more of the Target page's own fetches build a `FrameRow` for every sub of the target, and two of
  them `list()` it, so on the owner's deepest target one visit costs ~280 MB and ~3.8 s in endpoints nobody has
  changed.** *(Pillar: performance + memory safety — AGENTS.md §10, this box has an OOM history; size **M to
  write, M to be sure of**; severity low-to-medium. Confidence: **measured this run** on a synthetic project of
  35,894 subs carrying ~2 kB of `wcs_json` each, best of 3 on this box.)*
  **The class.** A `FrameRow` is `SELECT *`, and the biggest column on a solved sub is its plate solution —
  `wcs_json` is a FITS header *text* of ~25 eighty-character cards. Every endpoint that wants a handful of small
  fields off a deep target pays for that column. v0.471.1 fixed `/frames` (it was read eighteen times per visit),
  v0.471.2 the Stack form's `calibration-suggestions` and the Calibration page's coverage roll-up, v0.471.3
  `/sky-brightness` and `/restack-gain`. `Project.iter_frame_columns` is the primitive the rest would use.
  **What is left, measured:**

  | endpoint | time | peak allocation | what it actually needs |
  |---|---|---|---|
  | `…/best-frame` | 1,057 ms | **132.4 MB** | `best_frame(frames)` → `id`, `fwhm_px`, `star_count`, `timestamp_utc` |
  | `…/stack-health` | 1,153 ms | **145.6 MB** | `stack_health(run, frames)` + `recommended_dark_spec(frames)` + `stamped_noise_measurement(proj, run, frames)` |
  | `…/reject-summary` | 1,594 ms | ~0 (streams) | `count_unreadable_frames(frames)` → `cached_path`, `source_path` |

  **Why it is a lead and not a drive-by.** The two fixed in v0.471.3 were purely router-local: the router built
  its own small objects out of the fields, so the change stopped at the router. These three hand the frames to
  **engine** functions, so each is a question about that function's input type, not about the read — and
  `stack_health` is three functions over one list, on the priority-1 card. Changing an engine signature that other
  callers share is exactly the speculative refactor AGENTS.md §10 says not to do on its own.
  **Shapes worth costing, cheapest first.** **(a)** `count_unreadable_frames` is the easy one and the only one
  that is *not* about memory: it reads two path fields, its caller is the only caller, and it could take
  `(cached_path, source_path)` tuples. **Check first** that it is worth it — the 1,594 ms above is against a
  fixture where **no file exists**, which costs two `stat()`s per frame, and the endpoint's own comment records
  44 ms per 5,000 frames when they are all present; so on a healthy install the stat half is ~320 ms and the row
  building is the rest. **(b)** `best_frame` returns *the frame*, and its caller reads four fields off the
  returned one — so a narrow projection means either returning a tuple (and changing every caller) or keeping the
  id and re-reading that one row, which is one extra query against 132 MB. **(c)** `stack_health` is the big one
  and should not be attempted without deciding what a "frame" means to it first; it is also the one whose 145.6 MB
  is worth the most.
  **✅ (b) SHIPPED v0.471.5, and it needed no projection at all — read why before picking (a).** The dilemma the
  shape describes is a false one, because it assumes the lever is *what is read*. It is not: (c) measured the same
  run that these reads **stream**, so the cost is what the caller **keeps** — and `best_frame` is a `min()`, i.e.
  it keeps exactly one frame. The whole 132 MB was the endpoint's own `list(...)` plus the function's internal
  `eligible` filter list. Both are gone: `best_frame` takes an `Iterable` and streams a strict-`<` running minimum
  (identical tie-break — `min()` keeps the first frame at a winning key, and so does `<`), the endpoint hands over
  `iter_frames(accepted_only=True)` itself, and `n_accepted` is `Project.count(accepted_only=True)` rather than a
  `len()` of rows built to be discarded. **1,181 ms / 135.3 MB → 858 ms / ~0 MB**, same pick, same count. It still
  returns a `FrameRow`, so no caller changed and no record type was needed.
  **↳ Which downgrades (a).** It already streams (peak ~0, as the table says), the endpoint's own comment records
  44 ms per 5,000 frames when the files are present, and the 1,594 ms measured above is a fixture where **none**
  exists — so a projection there buys the row building only, on the one entry with nothing to retain. Probably
  not worth a slot; check the stat half against a healthy install before spending one.
  **Do not turn this into a sweep.** Each entry above is its own measurement and its own decision, and the two
  already fixed were worth fixing because the change stopped at the router. A blanket "make everything take
  tuples" would trade a readable engine API for a number nobody has asked about on a healthy-sized library.
  **✅ (c) SHIPPED v0.471.4 — the biggest one, and the decision the lead asked for was made rather than dodged.**
  What a "frame" means to `stack_health` turns out to be **seven small fields and one bit**, enumerated by
  reading every attribute the three functions touch: `accept`, `reject_reason`, `fwhm_px`,
  `eccentricity_median`, `exposure_s`, `gain`, `id` — and `wcs_json`, which is only ever asked *is it there?*.
  So the answer is a record, not a tuple and not a changed signature: new `project.FrameHealth` +
  `Project.iter_health_frames`, with `FrameRow.solved` added as a property so the one derived bit has a single
  definition and the engine functions can be handed either kind and cannot tell the difference (their
  annotations take a `stackhealth.GradedFrame` union). Every existing caller passes whole rows exactly as
  before. Measured on the same 35,894-sub fixture: **1,180 ms / 144.0 MB → 541 ms / 9.8 MB**, field-for-field
  identical, notes and darks-guide identical. Tests +16; the endpoint guard and the no-row-objects guard both
  **fail before** (scratch reverts, run).
  **One thing the lead assumed and the build measured — worth knowing before picking (a) or (b).** I first
  answered the bit in SQL (`wcs_json IS NOT NULL AND wcs_json <> ''`) on the theory that reading the header to
  test it "defeats the purpose". **It does not, and that machinery was removed before it shipped:** the read
  *streams*, so at most one header is alive at a time — measured **269 ms against 256 ms**, with the **same
  peak**. The whole 144 MB was never the reading, it was the **retaining**: 35,894 `FrameRow`s each holding
  their own header, all at once. So the lever on these endpoints is *what the caller keeps*, not what the SELECT
  names, and a narrow projection buys nothing where the caller already streams — which is exactly what the lead
  records about `reject-summary` (a), whose `count_unreadable_frames` streams and costs ~0.

- **🟠 OPEN REMAINDER of observer issue [#903](https://github.com/JimmyeJones/astrostack/issues/903) — a restack
  still *changes* each target's displayed picture; v0.447.2 only stopped it being silent.** *(Pillar: trust —
  PRIORITY 1-adjacent; size **L**, and not a drive-by. Filed by the Scout 2026-09-16 with three fix options;
  option (1) shipped as **v0.447.2**, option (2) declined, option (3) re-sized — reasons below. Full mechanism,
  the traced code paths and the owner's 44-of-77 pixel measurements are in [`SHIPPED.md`](SHIPPED.md) under
  v0.447.2.)*
  **↳ SEVERITY BOUND, observer re-measure 2026-09-21 (Scout logged 2026-09-25) — the open remainder is confined
  to *machine* auto-edits; hand edits are protected.** With a `reprocess_all` at target 45/95, the observer
  found 21 targets newly displaced from an edited run to a recipe-less newest run — and **all 21 are
  machine-made** (9 carry an `editor_auto_baked_look` stamp, 12 an `editor_auto_note` without one); **none is a
  hand-made recipe**, which `pipeline._picture_is_auto_finished` stands down on. So the guard (v0.448.1) is doing
  what it was built to do: it preserves the *current* displayed state and does not *restore* a pre-flattening
  finished run, which is precisely what option (3) below is for. The displaced renders are all re-derivable Auto
  output, so the harm ceiling here is "the wall shows a linear stack instead of an Auto render until re-run",
  not "the owner's own editing is lost". Do not re-prioritise this up on the strength of the 21-target count.
  **The mechanism in one line:** `current_picture_path` resolves cover → newest-with-a-preview, and
  `cover_stack_run_id` is NULL on all 89 of the owner's targets — so a restack, being newest, becomes the
  picture, and with the batch's auto-edit switch off that picture is a flat linear stack. v0.447.2 made the
  dialog say so, with the count (`reprocess_status.finished_pictures`), and v0.448.0 made the Library wall say
  which targets are in that state. Neither *prevents* it.
  **(2) — default the reprocess auto-edit from `settings.auto_edit_on_autostack` — DECLINED, don't re-file.**
  The owner's `auto_edit_on_autostack` is **off** (Owner Facts), so seeding the switch from it would leave his
  dialog byte-identical and change nothing about this bug; on an install where it *is* on it flips a visible
  switch's default, which is a behaviour change bought for no measured benefit. (1) already gives every install
  the choice explicitly, which is what (2) was reaching for.
  **(3) — pin the cover on supersede — still open, and NOT the small structural fix it looks like.** A cover
  pinned when a restack supersedes an edited run is *permanent*: `current_picture_path` prefers it over every
  later run, so the target that stops regressing today stops updating tomorrow, and the owner's next night's
  stack silently never becomes the picture. That is the same class of surprise pointing the other way. Any
  workable shape therefore needs an **unpin rule** (clear the auto-pin as soon as the target has a newer run
  that is itself finished), which is state the cover column does not carry — a manual pin and an auto-pin are
  the same NULL-or-int today, and §9 forbids repurposing the existing column's meaning. So (3) is really "an
  auto-cover with provenance" and wants its own design pass.
  **Cheaper alternative — ✅ ITS LARGER HALF SHIPPED AS v0.448.1; read this before re-picking it.** The idea
  was: carry the superseded run's finish onto the fresh run when the batch restacks a target whose displayed
  picture was finished, leaving cover semantics alone entirely. v0.448.1 ships that for the subset where it is
  unambiguously right — a picture the **app itself** baked (`editor_auto_baked_look` stamped on the run
  `finishedpicture.displayed_picture_run` picks, no cover pinned) gets a fresh Auto edit, via
  `pipeline._picture_is_auto_finished` → the existing `_auto_edit_process_run`, reported as `kept_finished`.
  Re-deriving Auto rather than copying the old recipe verbatim is deliberate there: the whole point of a
  reprocess is the *new* engine's pixels, and Auto fitted to them is what the app would have produced anyway.
  **What is still open is the hand-edited subset** — a recipe somebody saved themselves, which has no baked
  stamp. Copying it verbatim is the only way to preserve *their* look, and that is not a drive-by: a saved
  `geometry.crop` is expressed against the old canvas, and the over-trim machinery
  (`webapp/stale_crop.py`, `mosaicTrim.ts`) exists because a crop that no longer fits its coverage bound is a
  real failure mode. So this slice needs the crop re-derived or re-validated against the fresh run's coverage
  map, plus a test per direction. The wall chip (v0.448.0) is what makes the remaining cases visible meanwhile.
  **(3) is unchanged by v0.448.1** — nothing was pinned and the cover column's meaning is untouched.
  **⚠ BUILDER FINDING 2026-09-17, while shipping v0.448.1 — the hand-edited slice has a SECOND gate this entry
  does not name, and it is the harder one.** The crop is the gate everyone sees: a saved `geometry.crop` is
  expressed against the canvas it was cropped on, and `webapp/stale_crop.py` exists because a crop that no longer
  fits its coverage bound is a real failure mode. That one is *solvable* — the border rule can re-derive the rect
  against the fresh run's own coverage map, which is exactly what the editor's "re-trim this" offer already does.
  The gate nobody has named is the **tone chain**: a hand-tuned stretch, black point or curve is fitted to *one
  master's* noise floor and histogram, and the whole point of a reprocess is that the new master's are different
  (deeper, cleaner, possibly a different canvas and a different `photometric_normalize` outcome). Replaying that
  curve verbatim can clip a core it used to hold, or leave a sky it used to lift — and unlike the crop there is no
  existing measurement that says whether it did. So "copy the recipe forward" is **not** the safe half of this
  entry; it is the half that needs a way to *check* the replayed look before it becomes the target's picture.
  Sketch worth costing: replay it, then compare the result against the same two measurements the unattended
  auto-edit already records for its own output (`AUTO_EDIT_SKYCAST_PREFIX` sky cast, `AUTO_EDIT_HIGHLIGHT_PREFIX`
  blown-core fraction) and stand down to "leave it linear, the wall chip will say so" when either is worse than
  the run being superseded. That keeps the promise the entry is about without guessing. Do NOT ship a verbatim
  copy without it.
  **✅ CLOSED 2026-09-17 by the Builder who built the carry and then measured its premise — the hand-edited
  slice has nothing to carry, and both gates above are moot. Do not re-open it; the finding it produced
  shipped as v0.449.0.** I implemented the verbatim copy with the crop gate the entry asks for (canvas-shape
  check + `stale_crop` re-validation against the fresh run's own coverage, 21 tests, both gates fail-before),
  then probed the premise on the running app and **abandoned it unmerged**. The premise is that a restack
  flattens the picture a hand editor was looking at. It does not, because **there was never a stretched
  picture to flatten**: `routers.editor.put_recipe` writes the recipe row to the project DB and *nothing
  else* — **no path re-renders a preview on Save** — so a run carrying a hand-saved recipe is still showing
  `_write_preview_png`'s plain autostretch of the linear master. Measured, not reasoned: saving a recipe
  through the real endpoint leaves the preview PNG's sha1 **unchanged**, and the same run's listing reports
  `unexported_edit: true`, which is the app's own words for the same fact. It also matches the observer's
  measurement on the owner's library — his 42 saved recipes carry 3–70 % crops and **0 of 77 live previews are
  cropped**, i.e. none of those recipes is in the bytes. So a carry would not have preserved a picture; it
  would have put a look on the wall that had never been there, unprompted, in a batch operation.
  **The tone-chain gate above is closed by the same measurement** — there is no displayed hand-tuned look
  whose fidelity is at stake — and it was good judgement on a premise nobody had checked, which is why the
  measurement is recorded here rather than the disagreement.
  **What the probe *did* find is a real bug on three shipped surfaces, and it is fixed:** the same
  false premise lived in `finishedpicture.run_is_a_finished_picture`, which counted a saved recipe as a
  finished picture — so **saving an edit made the "Not stretched yet" chip vanish** from the Library wall and
  the Gallery, and shrank the reprocess warning's count, on a card whose bytes had not changed. Shipped as
  **v0.449.0**: a preview is finished when something *baked* it (an export's own pixels, or
  `preview_display_space`), which is the mark `_unexported_edit` already reads, so the two stop contradicting
  each other about one run. Entry in [`SHIPPED.md`](SHIPPED.md).
  **One genuinely open leftover, filed small and honestly optional (S, autonomy — PRIORITY 2):** after a
  reprocess, the user's saved recipe stays on the superseded run, so getting their look onto the new pixels
  means re-doing it in the editor. Copying the recipe onto the fresh run **without re-rendering its preview**
  would save that — the wall is unchanged either way (still the autostretch, still correctly chipped), so it
  changes no displayed pixel and the tone-chain judgement happens where it belongs, in front of the user in
  the editor. It would, correctly, make the fresh run report `unexported_edit`. Worth doing only if the owner
  asks; it is a convenience, not a regression fix, and this entry has already cost two runs.

- **🟠 BUG (autonomy / data-integrity, Scout 2026-09-14 — mechanism traced end-to-end from observer issue
  [#878](https://github.com/JimmyeJones/astrostack/issues/878)) — a mosaic's raw-subs folder is minted as a
  SECOND, hash-suffixed target because `make_safe_name("<T> (mosaic)")` collides with the on-device-output
  target's `<T>_mosaic`, so the same subs are QC'd, solved and stacked twice.** *(Pillar: autonomy —
  PRIORITY 2; size L; **architectural + touches on-disk layout — do not blind-take it**. Severity: medium
  — no image is wrong, but 76 % of the owner's frames (41,732 of 54,681) are double-registered, doubling
  CPU/disk on a box with a recorded OOM history, and the Library shows two entries per mosaic. Confidence:
  **mechanism TRACED and arithmetic-verified**; owner-side counts **measured** by the observer.)*
  **Root cause, confirmed by computing the hashes:** `mosaic_target_name` names a mosaic subs folder
  `<T>_mosaic_sub/` → display `"<T> (mosaic)"`, and `make_safe_name("<T> (mosaic)")` collapses the spaces
  and parens to `_` and strips them, yielding safe stem `<T>_mosaic` — *identical* to the safe stem of the
  Seestar's on-device output folder `<T>_mosaic/` (display `"<T>_mosaic"`, safe `<T>_mosaic`). Since the
  output folder is ingested as its own target (see #880), `<T>_mosaic` is already owned by a *different*
  display name, so `Library._allocate_safe_name` (`seestack/io/library.py:427`) disambiguates with
  `sha1("<T> (mosaic)")[:8]` → `<T>_mosaic-<hex>`. Verified: `sha1("73 Leonis (mosaic)")[:8] == "328c48ae"`
  and `sha1("Alphecca (mosaic)")[:8] == "c7bed385"`, both exactly matching the observer's minted targets.
  The 11 targets all being created in one 2026-07-25 3-minute window is the convention-upgrade re-scan that
  first applied `"<T> (mosaic)"` naming to folders an older scan had ingested under their raw folder name
  (`<T>_mosaic_sub` → display `"<T> mosaic_sub"` → safe `<T>_mosaic_sub`) — which is the OTHER member of each
  pair the observer lists. **Second, correctness-adjacent consequence Scout adds:** the *old* duplicate
  (`<T>_mosaic_sub`, named `"<T> mosaic_sub"`) does **not** end in `" (mosaic)"`, so
  `is_mosaic_target_name` (`seestack/io/scanner.py:87`) classifies it as a **single field** and stacks the
  mosaic subs in single-field mode — a genuinely wrong stack sitting in the library, not just clutter.
  **Code location:** `seestack/io/library.py:446` (`_allocate_safe_name` collision → hash suffix),
  `library.py:195` (`make_safe_name` lossy collapse of `" (mosaic)"`≡`"_mosaic"`), `scanner.py:82`
  (`mosaic_target_name`), `scanner.py:113` (`_seestar_target_name`). **Repro:** `sha1("<T> (mosaic)")[:8]`
  reproduces every `-<hex>` suffix; and `make_safe_name("X (mosaic)") == make_safe_name("X_mosaic")` for any
  X. **Why NOT a drive-by:** the obvious fix — give a mosaic target a distinct safe stem — changes on-disk
  paths for existing installs (§9 forbids), and de-duplicating the 11 existing pairs is a merge migration
  that must never touch `incoming/` (§10) and must keep the more-complete target. **Note the strong link to
  #880:** if the bare `<T>_mosaic/` on-device output were skipped at ingest (as single-field `<T>/` output
  already is), the stem `<T>_mosaic` would be free and the subs target would claim it cleanly with no hash
  suffix — so fixing #880's classification gap *prevents this collision going forward* (it does not un-mint
  the existing 11). Sensible first slice for the Builder: (1) make `_seestar_output_bases` recognise the
  mosaic output naming so `<T>_mosaic/` is skipped, closing recurrence; then (2) a separate, owner-sign-off
  merge pass for the existing duplicates. Do NOT ship a `make_safe_name` change that moves live folders.
  **⚠ BUILDER VERIFICATION 2026-09-14 (branch `claude/sweet-babbage-f0hdap`) — THE NAMED FIRST SLICE IS
  ALREADY IN THE CODE; do not build it.** Run against `_apply_seestar_convention` directly, with
  `["<T>_mosaic_sub", "<T>_mosaic", "M 42_sub", "M 42"]` as the drop: units `['<T> (mosaic)', 'M 42']`,
  skipped `[('<T>_mosaic', 'device_output'), ('M 42', 'device_output')]`. The bare-folder sibling test is
  `(parent, low + _SUB_SUFFIX) in sibling_names` (`scanner.py`), and `"<T>_mosaic" + "_sub"` *is*
  `"<T>_mosaic_sub"` — so a mosaic's device output sitting beside its subs folder has been skipped all
  along, by the single-field rule, without anyone noticing it covered both. **Recurrence is therefore
  already closed**, and the 11 minted duplicates are pre-convention leftovers rather than a live leak.
  `classify_seestar_junk_target` already offers one-click removal for exactly that shape too — it carries
  an explicit `is_mosaic = low.endswith(_MOSAIC_SUFFIX)` branch with its own wording ("its own stacked
  image of each mosaic panel") and checks the `<T>_mosaic_sub` sibling on disk. **What is genuinely still
  open here is (2)** — de-duplicating the 11 existing pairs, which this entry already routes to owner
  sign-off — **— and that is all.** *(Corrected later the same run, by the Builder who wrote the paragraph
  above: I had carried the Scout's "stacked in single-field mode" half forward as the one piece worth a
  slot, and it does not hold either.* **The stack does not consult the target's name.** `is_mosaic_target_name`
  has exactly two consumers — `objectinfo.py:352`'s `allow_extent_match` and the merge suggester's
  mosaic/single split at `routers/targets.py:193` — and neither is the stacker. Mosaic mode is decided
  **geometrically, from the frames' own plate-solved footprints**: `mosaic.py:330`,
  `is_mosaic = union_area > AUTO_UNION_AREA_RATIO * ref_area` (1.3x, i.e. footprint centres spanning more
  than ~15 % of the FOV), and that is what `run_stack` persists as the run's `is_mosaic`. So a legacy
  `<T>_mosaic_sub`-named target holding real mosaic subs **stacks as a mosaic anyway**; what its name
  actually costs is a merge suggestion that may offer to combine it with its single field, and a weaker
  object-extent match — both display-level, neither a wrong picture. There is **no wrong stack in this
  entry**.)* The one place
  `_seestar_output_bases` really does skip mosaics is the **healing** companion, for output frames an old
  scan merged *into* a `_sub` target — a different population from these, which sit in their own bare
  targets.
  **↳ OBSERVER CONFIRMS RECURRENCE IS DORMANT ON LIVE DATA, Scout 2026-09-19** (from issue #878's
  2026-09-17 follow-up; the observer re-measured the whole library after ingestion resumed). The duplicated
  set is **41,732 frames, byte-identical across four readings**, while the denominator grew by 5,885 newly
  ingested frames — so the falling rate (76.3 % → 68.9 %) is pure dilution, not new duplication. Grouped by
  capture night, the mechanism **last fired 2026-07-03**; the 18 nights and 18,681 distinct frames since
  (including all 5,885 post-stall ones) carry **zero** double-registration. A control rules out "the shape is
  gone": `IC_360` and `IC_360_sub` still both exist and still share 583 `source_path`s, yet `IC_360` has since
  taken 3,299 new frames from the very `_sub` folder its twin is named for and **none** landed in the twin. So
  the duplicating *shape* is present and the duplicating *behaviour* is not — which corroborates the Builder's
  in-code verification above that the sibling-skip rule already closes recurrence. **The only work left is the
  one-off reconciliation of the 11 historical hash-suffixed pairs, and it is owner-sign-off** (it merges
  targets / rewrites on-disk layout, §9, and must never touch `incoming/`, §10) — now filed as **gate 16** in
  "Needs owner sign-off" so the owner can see where the decision lives. No urgency from accumulation.

- **🟡 BUG (friendliness + autonomy, Scout 2026-09-14 — verified from observer issue
  [#880](https://github.com/JimmyeJones/astrostack/issues/880)) — a raw Python exception repr is stored as a
  user-facing `reject_reason`, and QC-error frames stay `accept=1`, so 11 mosaic-output-only targets sit in
  the library as accepted-but-unstackable.** *(Pillar: friendliness — PRIORITY 3; size S–M. Severity: low —
  no image damaged, no stack polluted (observer ruled out pollution: the 54 frames are in bare `<T>_mosaic`
  targets with zero stack_runs, disjoint from the real `<T>_mosaic_sub` targets). Confidence: **traced** to
  the exact lines.)* Three distinct, separable defects: **(a)** `qc/runner.py:113` stores
  `reject_reason = f"{reason}:{result.error or 'unknown'}"`, and `result.error` is the raw exception string
  from `fits_loader.py:219` (`ValueError: expected 2D Bayer array, got shape (3, 3840, 2160)`) — a Python
  repr shown wherever a reject reason surfaces, against a namespaced vocabulary everywhere else
  (`auto:grade:fwhm_px`, `auto:seestar_output`). The cheap, independently-correct fix: store a namespaced
  code (`qc_error:unsupported_layout`) and keep the exception text in a detail column, so no surface ever
  shows a repr. **Care:** `reject_reason.startswith("qc_error")` is matched in `rejection_summary.py:82`,
  `session_recap.py:91`, `stackhealth.py:520`, `solve/runner.py`, `project.py:1319` — the prefix must be
  preserved, and the 135 existing rows carrying the old format must still bucket correctly (add a migration
  or a read-time normaliser; do not rewrite rows in place without a test). **(b)** QC error leaves `accept`
  untouched (`apply_qc_result_to_db` sets only `reject_reason` when `metrics is None`) — combined with the
  mosaic-output classification gap (`scanner.py:377` skips mosaics in `_seestar_output_bases`), the 54
  device-output frames stay `accept=1` and count as accepted for 11 targets no stack can ever use. **(c)**
  the classification gap itself is the same one #878 turns on — fixing it (recognise `<T>_mosaic/` device
  output and reject/skip it like single-field output) closes both the accepted-clutter here and #878's hash
  collision. (a) is the safe small win; (b)/(c) are the shared mosaic-output work.
  **⚠ BUILDER VERIFICATION 2026-09-14 (branch `claude/sweet-babbage-f0hdap`) — (a) is NOT user-facing and
  (b) is deliberate; read this before spending a slot here.**
  **(a):** the exception repr is *stored*, never *shown*. Every surface that renders a reject reason maps
  it first — `frontend/src/routes/Target.tsx::rejectReasonLabel` answers `"QC error"` for anything
  `startsWith("qc_error")` (pinned by `Target.test.tsx:1990`), `webapp/rejection_summary._bucket_for`
  buckets it as `"error"`, and `seestack/session_recap.py:91` says `"unreadable"`. The observer sees the
  repr because it reads `project.sqlite` directly, which is not a UI. So this is **storage hygiene, not a
  friendliness bug**: real, and worth doing if the file is touched, but it costs a migration or a read-time
  normaliser for the 135 existing rows plus five `startswith("qc_error")` consumers and buys the owner
  nothing visible. Do not carry it as PRIORITY 3.
  **(b):** `accept` staying True on a QC error is **documented, deliberate design**, not an oversight —
  `seestack/solve/runner.py:336-342` spells out the carve-out and why it exists. Flipping it is not a
  one-liner: the recovery branch (`qc/runner.py:135-140`) clears only `reject_reason` when a later QC
  succeeds, so setting `accept=False` on the *retryable* first failure would let one transient NAS blip
  permanently un-accept a good frame. Any change here must restore `accept` in that branch too, and needs a
  test for the blip-then-recover path. **(c)** is answered by the #878 note above.

- **📋 OWNER ANSWERS TO THE FOURTH AUDIT'S OPEN QUESTIONS (2026-09-11) — two findings get *smaller*, one
  question is closed unanswerable. Read before prioritising the audit's items.**
  - **The pre-D1 saved-recipe crop (⭐ item below — ✅ IT HAS SINCE SHIPPED, don't go looking for it; all three
    surfaces closed in v0.416.0 + v0.417.0, entries in [`SHIPPED.md`](SHIPPED.md), and the order dependency
    below is therefore already satisfied): he sees no blurry mosaic cards.** Asked to open his Library
    and look, his answer was *"don't see anything immediately"*. **The likely reason is in Owner Facts:
    `auto_edit_on_autostack` has been OFF on his install**, so the walk-away chain never auto-edited anything —
    a stored recipe only exists where he used the editor or "Process target" **by hand**. So the bug is **real
    and still worth fixing** (the audit reproduced it in the shipped image over a real v0.277 volume), but its
    blast radius *on this owner* is small, and it is **not** the emergency the audit's placement implies.
    **Re-prioritise accordingly — and note the order dependency:** it becomes materially *more* important the
    moment `auto_edit_on_autostack` is turned on, which is an approved-and-pending change. **Fix it before that
    flips**, not after. Absence of a visible symptom is not proof of absence — he looked quickly, at cards, not
    at every target.
  - **Root-owned files under `library/targets/` — low impact, confirmed.** The container runs as root, so
    everything it writes is root-owned. Asked whether he browses that share from Windows, he said he browses
    **only to upload new subs** — i.e. he writes into `incoming/` over SMB (TrueNAS-owned) and has no need to
    read or write the app's own `library/targets/` tree from a client. **Keep the finding open as hygiene, drop
    its priority**; it is not blocking him and a UID/GID change to a live install is exactly the kind of
    migration §9 says to be careful with.
  - **Which version he upgraded from: unanswerable, stop asking.** *"don't remember"*, and the upgrade has
    already happened, so the pre-upgrade schema and config are gone. **Do not spend a run reconstructing it.**
    Anything that genuinely needs it should be re-derived from what is on disk now (run records, schema
    version, `config.json` keys) rather than from his memory.

> **Open bugs and nothing else** (the three-file rule, AGENTS.md §2). The 227 resolved
> entries and 24 QA sweep records this section used to carry were cut to
> [`SHIPPED.md`](SHIPPED.md) and [`PROCESS-NOTES.md`](PROCESS-NOTES.md) on 2026-09-05,
> verbatim and in order — 12,375 lines down to under 1,000, so this section can be *read*
> rather than skimmed. **Grep those two files for anything older than v0.352.3**, including
> the target of any "see above" / "see below" in the entries below that no longer resolves
> here.

- **🟠 FIXTURES THAT CANNOT EXHIBIT THEIR BUG (fourth external audit, 2026-09-10 — both reproduced by reverting
  the fix in a scratch script; see PROCESS-NOTES).**
  ~~(1) `test_the_sky_stays_put_at_every_stack_depth[very-deep]`~~ and
  ~~(2) `test_a_ragged_mosaic_still_gets_its_fringe_trimmed`~~ — **BOTH FIXED v0.417.1** (Builder 2026-09-10),
  each verified by reverting the production fix in a scratch script and watching the test go red, which it now
  does and did not before. (1) `displayspace.assert_shadow_clip` now replays the **pre-fix** `_sky_mode`
  histogram — all finite values over `[p0.5, median]`, 128 bins — and requires bin 0 to *win* it, so the guard
  checks the clip **dominates** rather than merely exists; and the depth ladder gained an explicit
  `exhibits_a1` flag, because the measured boundary is between 0.001 (pre-fix rel. error 0.996) and 0.0008
  (0.114): the three rungs at and above 0.001 now assert the strong guard, and `very-deep` is kept but labelled
  as coverage of the *fix*, never of the bug. The test had also been leading with a hand-rolled
  `clipped_fraction(st) > 0.005` instead of the shared guard, which is how it drifted. (2) now asserts the rect
  **equals** `(5/400, 5/400, 395/400, 395/400)` — the border rule's own answer, measured — with the ~95 % kept
  fraction a consequence rather than the check; on the reverted rule it was 0.902, inside the old
  `0.90 < kept < 0.99` window.
  ~~**(3, note only)** the v20/v21 fixtures in
  `tests/test_project_schema_drift.py` are today's `SCHEMA_SQL` minus one or two columns, which
  `_reconcile_table_columns` restores even with the migration steps deleted~~ — **FIXED v0.418.2**
  (Builder 2026-09-11), and the entry is now CLOSED. Reproduced first: both tests passed with their
  `if from_version < 21` / `< 22` blocks **deleted outright**. Two things were wrong, and only one of
  them was the fixture. The *observation* was that a purely additive nullable-column migration and
  the runtime backfill produce the same schema, so `_disable_the_runtime_backfill` now switches the
  net off and makes the migration the only thing that can satisfy the assertions. The *fixture* is now
  a frozen DDL literal instead of `SCHEMA_SQL` minus the new columns — which is the half that buys
  something durable: a derived fixture grows every column the schema grows, so it can never be missing
  one, whereas a frozen one goes red the moment a column reaches `SCHEMA_SQL` with no `ALTER` step.
  Verified against all three cases, including a synthetic new column with no migration — the v0.119.8
  live-install brick, red in this suite for the first time. Full entry in [`SHIPPED.md`](SHIPPED.md).

- **⚪ A-MINOR — verified smaller items from the same audit, batch these into cleanup passes.** ~~No validator
  stops `library_root` being set **inside** `incoming_dir` (after which every correctly-scoped `rmtree`
  resolves inside the raw tree — *not* the owner's current state, but one settings edit away)~~ *(shipped
  v0.327.8, see above)*; ~~the scanner's
  bare-`<T>/` skip is **silent** even when the folder holds thousands of FITS (the owner's `NGC 6888` 4,815 vs
  `NGC 6888_SUB` 3,110 is exactly that shape)~~ *(shipped v0.329.2, see below)*; ~~the plate-solve-failed screen shows a
  blocking banner and, in the same row, a "?" popover calling unsolved subs "usually harmless"~~ *(shipped
  v0.328.1, see below)*; ~~the Stack
  page prints the **raw engine error** where every other page uses `friendlyJobError`~~ *(shipped v0.328.0,
  see below)*; ~~the frames table prints raw
  UTC under a hero that says "Shot &lt;local night&gt;"~~ *(shipped v0.328.5, see below)*;
  ~~"nights" means **6-hour sessions** on the Nights card
  but **calendar nights** in captions~~ *(shipped v0.329.1, see below)*;
  ~~three hand-mirrored "is this a genuine run" predicates~~ *(shipped v0.338.1 — and they **did** disagree;
  see the note directly below)*;
  `POST /api/targets` has **no frontend caller**; ~~share and print JPEGs use 4:2:0 chroma subsampling~~
  *(shipped v0.328.0, see below)*; the "full
  data" TIFF anchors its white point on the single brightest surviving pixel *(traced 2026-09-03 — the
  mechanism is confirmed, but read the note below before "fixing" it)*.

- **⚪ MEASURED RESIDUAL OF D1's FOURTH INSTALMENT (Builder 2026-09-09, filed with the v0.399.3/v0.399.4 fix
  that closed the rest) — the border rule still over-crops a **weighted** coverage map on a minority of fully
  tiled rasters, which only a **legacy** run can now hand it.** *(Severity: low — every run that writes
  `{stem}_framecov.fits` is measured on the frame count instead, where the same 147 rasters are 0/0/0 in all
  three outline shapes. Confidence: HIGH, same harness. Size: unknown.)*
  Over 147 rasters × 3 outline shapes (exactly tiled; four uncovered corners; a ragged perimeter), as how many
  keep under 95 % of what their own coverage allows: **frame counts 0 / 0 / 0** (worst 1.000), **weighted
  13 / 14 / 39 → 4 / 4 / 10** (worst 0.822 / 0.817 / 0.801). The mechanism is the one the fix already names: a
  weighted value is a sum of per-frame *weights*, so one panel occupies a *band* of values rather than a level,
  the panel-vs-ramp shape test sees speckle rather than blocks, and the reference itself wanders. **The reachable
  population is runs recorded before `_framecov.fits` existed**, which `_trim_rect_for_run` falls back to the
  weighted map for; a re-stack writes the sibling and moves the run into the fixed column.
  **Before starting, read the five rejected levers and the shipped rule in [`SHIPPED.md`](SHIPPED.md) (search
  `FRINGE_OUTSIDE_FRAC`)** — four scalar levers are measured and closed, and the answer here is unlikely to be a
  sixth. The honest next step, if this is ever worth it, is to make the *shape* test survive jitter (a local mean
  before the plateau/connectivity work) rather than to move a constant. **Probably not worth building**: the
  cheaper and more useful fix for a real install is a re-stack, and the whole population shrinks every night the
  owner shoots.

- **🟡 BROKEN-UX / AUTONOMY (Scout QA audit 2026-08-26 #4, traced + verified end-to-end) — PARTIALLY FIXED
  (misleading-copy half shipped v0.272.2; optional behavioural half open) — the `astap_timeout_s` setting bounds
  ONE solve *attempt*, not one frame, so an unsolvable sub can burn up to 3× the configured seconds; the Settings
  help text used to say the opposite and now says so honestly.** *(Severity was broken-UX / autonomy — it
  silently triples the wasted time on a cloudy walk-away night, the owner's exact workflow; not wrong-result.
  Confidence: traced against the code.)*
  `ASTAPSolver.solve` (`seestack/solve/astap.py:206`) runs a **3-rung** ladder (`_SOLVE_LADDER`, ~line 147:
  default → full-res `-s 1000` → bin-2×), and each rung calls `_solve_once` → `subprocess.run(timeout=self.timeout_s)`
  (~line 294). A timeout on a rung raises `ASTAPError`, which is caught and **falls through to the next rung**
  (~line 216–226) — each getting the *full* `timeout_s` again. So a frame that never solves (heavy cloud, star-poor
  sub) consumes up to `3 × astap_timeout_s` of wall clock: **180 s at the 60 s default**. Meanwhile the
  frontend tooltip (`frontend/src/routes/Settings.tsx:52`) reads *"Give up on solving a single frame after this
  many seconds."* — literally per-frame, which is false. On a clear night this is invisible (frames solve on rung 1
  in a second or two; only *timeouts* accumulate), but on a cloudy night with hundreds of unsolvable subs it can turn
  an expected ~100 min of wasted solve time into ~5 h, delaying the very auto-stack the owner walked away for.
  **Fix options (the ladder's multi-attempt rescue is load-bearing, so don't just cut it):**
  (a) ~~*Honest-copy, safe:* correct the tooltip.~~ — **SHIPPED v0.272.2** (Scout 2026-08-26, this run): the
  `astap_timeout_s` hint now reads *"Give up on each solve attempt after this many seconds. The solver tries up to
  3 strategies per frame, so a frame that never solves can take up to about 3× this before it's set aside (and
  retried on the next scan)."* with a `Settings.test.tsx` assertion pinning the per-attempt wording. So the setting
  is no longer *misleading*; the wasted-time behaviour itself is unchanged. **(b) is the remaining open half:**
  *Behavioural, careful:* budget the timeout across the ladder (e.g. full `timeout_s` on rung 1 where most frames
  solve, a fraction on rungs 2–3, or a shared deadline for the whole frame) so the setting bounds *per-frame* time as
  its name implies, without starving the coarse rescue rungs — needs a test that a hard frame still gets its rescue
  attempts and that total per-frame time is bounded. Only worth doing if the owner wants true per-frame bounding;
  the label fix above already removes the surprise.
  **Builder 2026-08-26 — considered and deliberately DECLINED this run; read this before picking it up.** I sized
  it against the real code and stopped, because every workable shape is a **blind threshold flip on the
  on-by-default hot path**, which AGENTS.md §1 tells an agent not to do. The ladder cannot be given a true
  per-frame bound without a per-rung floor (a shared deadline alone gives rungs 2–3 *nothing* on exactly the
  frames a timeout means they exist to rescue), and the floor's size *is* the tradeoff: at 25 % of `timeout_s`
  the worst case falls 3× → 1.5×, at 50 % it falls to 2×, and in both cases a hard frame that rung 3 would have
  cracked in, say, 20 s is now abandoned. Which frames that loses is unmeasurable from the repo — it needs a real
  cloudy night's subs, which no agent has. Meanwhile the cost of leaving it is now *bounded and honest*: the
  Settings hint says "up to about 3×" (v0.272.2), and as of **v0.276.4** a sub that burned the whole ladder is
  no longer silent — it lands in its own "Ran out of time being located" bucket on the Target page telling the
  owner to raise the timeout. So the surprise and the invisibility are both gone; only the wasted minutes
  remain. **Leave this for the owner to ask for**, and if they do, ship it with the floor as a named constant and
  the measured before/after on their own data — not on a synthetic frame.

- **⚪ HARDENING NOTE (Scout QA audit 2026-08-27 #8, traced — possibly by-design; low confidence) — the folder
  watcher's stability gate compares host wall-clock `now` to the source file's `mtime`
  (`(now - mtime) >= quiet_period_s`, `webapp/watcher.py` ~line 94), so if the NAS/SMB source filesystem's clock
  runs AHEAD of the host, completed files may never satisfy the age gate and never go stable → never ingested
  until the host clock catches up.** *(Severity: low — needs a genuinely skewed source clock, and a manual
  "Scan incoming" or app restart re-globs and picks the files up anyway; the mtime-age gate is a deliberate
  "has the write finished settling" heuristic, so this may be acceptable as-is. Confidence: traced, not
  reproduced; flagged so it isn't re-investigated.)* **If ever worth hardening:** gate on size-stability across
  two polls (already tracked) rather than absolute mtime age, or clamp a negative `now - mtime` to "treat as
  just-modified" so a skewed-ahead clock can't strand a file forever. Only worth doing if the owner reports
  files that never ingest until a rescan.

- **⚪ HARDENING NOTE (found incidentally, 2026-08-17 audit — not currently firing for the owner, no fix
  needed yet, just a landmine to know about) — the mosaic-canvas outlier-exclusion pass's rejections are
  PERMANENT with no reconcile path**, unlike auto-grade's post-v0.221.0 behaviour. Verified not to have fired
  for the owner's data (3° floor + median-separation term; the owner's ~3.6°-apart panels excluded nothing).
  If a future mosaic legitimately trips this exclusion, there is currently no path back for those frames the
  way `apply_grade_reaccepts` provides for auto-grade. Worth a reconcile pass eventually, same shape as the
  auto-grade fix, but not urgent — file only, don't build until it's someone's actual problem.

- **Follow-up to the v0.225.0 mosaic-Auto fix — bisect the rest of the v0.158→v0.220 colour chain on a synthetic
  mosaic.** The measured root cause (noise misread → `detail.chroma_denoise` at full strength) is fixed and the op
  no longer fires on a deep mosaic, but the original entry rated confidence only **medium** that it was the *sole*
  contributor to the owner's seam grid. **Do this only if the owner reports the grid persists on v0.225.0** — the
  synthetic 4-panel mosaic scene now lives in `tests/test_auto_noise_measure.py::_scene(mosaic=True)`, so the
  bisect is cheap: run `get_proxy → auto_recipe → apply_recipe` with SCNR, the per-frame flatten and
  `remove_final_gradient` individually disabled and measure the chroma step across a panel boundary vs within a
  panel. Note the shipped fix's own measurement found the *absolute* seam step is dominated by the injected panel
  offsets themselves (the smoother reduces it), so any further work should measure the **visible plateau/edge
  structure** the smoother creates, not the raw step. (M, image quality — PRIORITY 1/4.)

- **Minor / low-priority (traced, filed for completeness — fix only if touching these files):**
  - ~~`seestack/stack/output.py:654` (+400, 413, 428, 446, 525) every float→uint export **truncates**
    instead of rounding, biasing every exported pixel downward by ~½ a step.~~ — **FIXED v0.354.1** (all six
    sites now go through one shared `output.pack_unit`, which `np.rint`s; the entry, the measurements and the
    test re-reasoning are in [`SHIPPED.md`](SHIPPED.md)). **Two non-bugs from the same 2026-09-05 mosaic/output
    QA audit are kept here so they aren't re-investigated:** `output.py` `_write_coverage_fits` writes a **2-D**
    coverage map verbatim without the `.astype(np.float32)` its 3-D branch and `_write_frame_coverage_fits` both
    apply — a double-size FITS if a float64 2-D map ever reached it, which the production accumulators never
    emit; and `_same_map`'s `np.array_equal` returns False on identical-NaN maps, moot because coverage maps are
    0-filled, never NaN.
  - ~~**LEAD — the same truncating pack lives in `seestack/render/`, on the *display* side.**~~ —
    **FIXED v0.354.2**, and wider than the lead framed it: fifteen hand-spelled sites across
    `seestack/render/`, `seestack/printexport.py`, `seestack/stack/stacker.py`, `webapp/routers/`,
    `webapp/pipeline.py` and `webapp/video.py` now go through `output.pack_unit`, with a drift test that
    greps the tree so a sixteenth can't appear silently. Two of them — `printexport.render_print` and the
    Moon still's 16-bit TIFF — were *exports* the v0.354.1 sweep had missed because they live outside
    `stack/output.py`. Entry in [`SHIPPED.md`](SHIPPED.md).
  - `seestack/stack/weighting.py:97` the FWHM factor computes `(best_fwhm / f.fwhm_px) ** 2` with a Python float, so a
    pathologically tiny `fwhm_px` would raise `OverflowError` (before `np.clip` can clamp it) rather than saturate.
    **Unreachable on real data** — every writer of `fwhm_px` traces to `median_fwhm`, which persists only values in
    (0.5, 20) or None, and overflow needs `fwhm_px < ~1.5e-154` (a crash reproduces only at ~1e-300). Defensive-only:
    cast to `np.float64`/guard the ratio if the file is touched. (Cosmetic — unreachable; confidence: traced + repro'd
    at the unreachable boundary.) — **FIXED v0.367.1**: the ratio is computed in `np.float64` under
    `errstate(over="ignore")`, so it saturates to `inf` and clips to the 1.0 the formula already wants.
    Regression `tests/test_engine_defensive_guards.py::test_a_pathologically_tiny_fwhm_saturates_instead_of_crashing_the_stack`. _(Found by the 2026-07-24 weighting audit.)_
  - `seestack/stack/align.py` (subpixel-refine cap, ~line 400/490) the guard `|dy| > CAP or |dx| > CAP` does **not**
    reject a NaN shift (NaN fails both comparisons → the shift is applied). **Unreachable** — the correlation patches
    are NaN-filled to finite before `phase_cross_correlation`, and finite inputs never return a NaN shift (a featureless
    overlap returns a finite spurious `(-0.7,-0.7)` whose ≤5px NaN edge-ring is exactly consumed by the
    `pad=SUBPIXEL_SHIFT_CAP_PX=5` window). Defensive-only: rewrite as `not (abs(dy) <= CAP and abs(dx) <= CAP)` so a NaN
    is treated as "too large" and skipped, belt-and-suspenders, if the file is touched. (Cosmetic — unreachable;
    confidence: traced.) — **FIXED v0.367.1**, at *both* sites (`_apply_subpixel_shift` and the windowed one).
    Regression `tests/test_engine_defensive_guards.py::test_a_nan_subpixel_shift_is_refused_rather_than_smeared_over_the_frame`
    (patches `skimage.registration.phase_cross_correlation` to return a NaN shift; fails before — `nd_shift`
    wiped the whole frame to NaN). _(Found by the 2026-07-24 align audit.)_
  - `seestack/stack/align.py::extract_reference_patch` fills NaNs with `np.nanmedian(luma)`, which on an **all-NaN**
    patch emits a RuntimeWarning and returns NaN — so the shared reference patch would be entirely NaN and every
    frame's sub-pixel refine would silently correlate against nothing (each `phase_cross_correlation` returning a
    meaningless shift, or the call failing and the frame stacking unrefined). **Unreachable in practice** — the
    patch is the *centre* of the reference frame's own aligned array, which is finite by construction; a fully
    uncovered centre would mean the reference didn't land on its own canvas. Defensive-only: fall back to `0.0`
    when the median isn't finite, if the file is touched. (Cosmetic — unreachable; confidence: traced.)
    — **ALREADY FIXED** (found done while sweeping this batch, v0.367.1): `extract_reference_patch` computes
    `fill = float(np.median(luma[finite])) if finite.any() else 0.0`. Struck so nobody re-picks it.
    _(Found by the 2026-08-07 align/accumulator audit, which otherwise traced clean: the windowed and full-canvas
    accumulator adds, the min/max k-set insertion and its ±inf identities, the mosaic canvas RA-unwrap and outlier
    passes, the photometric scale/weight composition, and the reproject inset/pad arithmetic all held.)_
  - `webapp/routers/storage.py:193` `prune_stack_runs` closes `proj` then `lib` in a **single** `finally` (not
    nested like `gallery.py`/`storage.py::get_storage`), so if `proj.close()` itself raised, `lib.close()` would
    be skipped and the Library handle would leak. Trigger is essentially unreachable (`sqlite3.Connection.close()`
    does not raise in practice), so this is a consistency nit, not a live leak — nest the two closes if the file is
    touched. (Cosmetic; confidence: traced.) — **FIXED v0.367.1**: nested, matching `get_storage`/`gallery.py`.
  - `seestack/solve/runner.py:204-218` the "unreadable plate solution" self-heal branch's comment claims recording a
    `reject_reason` makes the frame "stop being re-offered," but `build_solve_arglist` (`runner.py:166`) skips frames
    only on truthy `wcs_json` — nothing gates on `reject_reason`, so a consistently-unparseable `.wcs` sidecar is
    re-solved every scan (identical to the ordinary transient-failure branch it says it "mirrors"). The re-offer
    behaviour is itself harmless/safe (a transient corruption recovers on retry); only the comment over-promises. Fix
    the comment (or, if genuinely un-recoverable, gate the skip on the stored reason) if the file is touched.
    (Cosmetic — comment vs behaviour; confidence: traced.) — **FIXED v0.367.1** the comment, not the behaviour:
    re-offering is deliberate and correct here (an unreadable sidecar is usually transient), and
    `build_solve_arglist` says so explicitly — so the comment now states what the branch actually buys (the frame
    is no longer stored as *solved-yet-unusable*) instead of promising a skip nothing implements.
  - `seestack/stack/reference.py:42-44` `pick_reference_frame` filters candidates on `ra_center_deg is not None` but,
    unlike `pointings.py:78-80`, does not also require `math.isfinite` — so a hypothetical NaN centre would propagate
    into the unwrap/median/score and pick an arbitrary reference. Effectively unreachable (a successful solve writes a
    finite `wcs_json` + centre; a failure leaves `wcs_json` NULL and is filtered by the `f.wcs_json` clause), so this
    is a defensive consistency nit, not a live bug — add the `isfinite` guard to match `pointings.py` if the file is
    touched. (Cosmetic; confidence: traced.) — **FIXED v0.367.1**. Regression
    `tests/test_engine_defensive_guards.py::test_a_nan_pointing_never_becomes_the_reference_frame` (fails before:
    the NaN frame was picked, and a NaN-only list returned a frame instead of `None`).
  - `seestack/post/skymap.py:266` the **offline** galactic-plane fallback (astropy absent) draws the Milky Way
    curve with a linear-in-sin approximation that is up to ~29° off in declination. In this deployment astropy is
    a hard dependency, so the exact `except` branch is dead code and never renders — noted only so a future
    dependency change doesn't ship a wrong overlay. (Cosmetic/dead-code; confidence: traced.)
  - `seestack/io/merge.py:88-99` `MergeResult.n_skipped_missing_file` mislabels *added* frames: a frame is
    counted `added` (L84) before the cache block, and when `old_cache.exists()` is False it does `missing += 1`
    while the frame is **still merged** (usable via `source_path`, `cached_path=None`). So the counter reports
    "added-but-cache-missing", not "skipped". Reporting-only; no data loss. (Cosmetic; confidence: traced.)
  - ~~`seestack/io/ingest.py:93-103` `_cache_stale` refreshes on source *shrink* too, not just growth: the
    docstring justifies it as "source grew after it was cached" but the `st_size != st_size` test is symmetric,
    so a source later truncated/replaced smaller than its cache overwrites a good Stage-1 cache and resets that
    frame's QC.~~ — **CLOSED as already-defended, not fixed; re-traced 2026-09-07 so nobody spends a slot on it.**
    `_cache_stale` is symmetric and stays that way, because the harmful half is caught **before** it is reached.
    A shrunk source means `fp_changed` → `content_changed`, and `_source_incomplete(src)` (`ingest.py:338`) runs
    first: it *loads the pixel data*, so a mid-rewrite truncation fails to read and the whole frame is skipped
    with `skip_reason="still copying (incomplete rewrite)"` — nothing touched, cache intact, re-checked once the
    source settles. A source that shrank and is still a **complete, readable** FITS is a genuinely different,
    smaller capture at a reused path, and refreshing the cache is then the *right* answer (it is the second case
    `_refresh_frame_metadata`'s docstring names). The only residue is a pre-fingerprint row from a library
    upgraded and not yet re-scanned, where `stored_fp is None` skips the guard for exactly one scan before the
    fingerprint is backfilled — and its worst outcome is a re-QC. Do not "fix" the symmetry: making it
    growth-only would strip the content-swap refresh that keeps a new capture from stacking at the old sky
    position. (Confidence: re-traced against the current code.)
  - `seestack/io/scanner.py:123` + `ingest.py:143` a symlinked duplicate subdir double-ingests: if `root`
    contains both a real subdir and a symlink to it, both pass `is_dir()` and become separate targets/projects,
    and the per-project `realpath` dedup (built only from that project's own frames) doesn't catch the same
    physical raws landing in a second project. Only harmful if the user later stacks both. (Edge case; traced.)
  - ~~`seestack/bg/per_frame.py:289-297` `_subtract_background_cpu` on the **stack path** (`errors=None`): if one
    channel's `Background2D` fit fails it's skipped while the others subtract, then `_zero_sky_per_channel` runs —
    a per-channel-asymmetric result that could introduce a faint colour cast.~~ — **FIXED v0.173.2** (Builder
    2026-07-23, branch `claude/pensive-faraday-tfvkyx`; regression-tested). The stack path now fits all three
    channels *before* subtracting and, if any channel's ladder fit fails, degrades to **no** subtraction (leaves
    the gradients) rather than a per-channel-asymmetric one — matching the editor path's already-documented
    reasoning ("don't leave a partial per-channel subtraction that would colour-shift the image"). A per-frame
    colour cast is coherent and does not average out in the stack, so all-or-nothing is the correct degradation.
    Regression `tests/test_bg_modes.py::test_stack_path_bails_on_a_single_channel_fit_failure_no_colour_cast`
    (monkeypatches the ladder to fail on channel 0 only; asserts the frame is returned unchanged — fail-before it
    partial-subtracted G/B). Additive; no config/DB/API/on-disk change. Severity: image-quality/correctness, Low
    (only on a degenerate fit, now rare given the robust ladder). (Confidence: traced + regression-tested.)
  - `seestack/qc/streaks.py:107-112` `streak_count` **over-reports** a single continuous trail as 2–5 (one
    satellite/plane trail fragments into several collinear `probabilistic_hough_line` segments; `line_gap=8` +
    `disk(1)` dilation don't re-merge them). Reproduced (Scout 2026-07-23, adversarial QC audit): a clean diagonal
    trail → count 2 (width 1) / 5 (width 2–3). **Not surfaced in the live web app** — `streak_count` is displayed
    only in the historical desktop GUI (`seestack/gui/preview.py:209`, `frame_table.py:60`), which is
    deprioritised; it *is* persisted to `project.sqlite`. **Does NOT affect stacking or auto-reject** — the
    `streak_detected` boolean that drives `auto:streak` is correct in every tested case. The docstring's primary
    definition ("number of distinct line segments") is technically accurate; only the "N satellites" framing is
    optimistic. Fix only if this count is ever surfaced in the web UI (then post-merge collinear segments into
    trails). (Broken-UX but web-invisible today; confidence: reproduced.)

- **Sky-atlas overlay WCS uses a rotation sign that deviates from the FITS/AIPS `CROTA2→CD` convention
  (display-only; needs a real solved frame to validate before flipping — NOT a blind Builder change).**
  **⚠ LARGELY SUPERSEDED by the v0.142.4 Sky-map placement fix (Bug 2 above):** `get_sky` now places
  the overlay from the stack's **stored canvas WCS** (`wcs_dict_rescaled_to_preview`), so `_tan_wcs` is
  only reached as the **fallback for a run whose master FITS is missing/headerless** (older/edited runs) —
  the ordinary path never hits the suspect sign anymore. The remaining sign issue affects only that
  fallback, so it's now low-impact; still real-data-gated (validate ASTAP's CROTA2 sign on a real solved
  frame before flipping). Original trace kept for the fallback fix:
  *(Traced, Builder audit 2026-07-10; high confidence it deviates from the convention, low confidence it
  visibly matters.)* `webapp/routers/sky.py::_tan_wcs` (~L92) builds the derived TAN WCS for the sky-atlas
  preview overlay with `CD1_2 = +scale·sinθ`, `CD2_1 = +scale·sinθ`. With the RA axis flipped
  (`CD1_1 = −scale·cosθ`, i.e. `CDELT1 < 0`), the standard AIPS `CROTA2` convention wants **both** off-diagonals
  **negated** (`CD1_2 = CD2_1 = −scale·sinθ`) — the current signs are equivalent to using `−θ`, so on a frame
  with non-zero field rotation the Aladin overlay is rotated by `2θ` from correct (a mirrored rotation). It is
  **display-only**: it never touches the stored `wcs_json` or any stacking/science result (the built-in viewer
  is unaffected), and the code comment already flags "Sign of the rotation is a best-effort starting point."
  **Why NOT a blind fix:** whether ASTAP's `CROTA2` follows the same sign sense as the AIPS convention decides
  which way is right, and some solvers differ — flipping the sign without checking could just rotate it wrong
  the *other* way. Validate against a **real** Seestar frame solved with a known non-zero field rotation (compare
  the overlay placement to the true sky) before changing it; a synthetic can't stand in for ASTAP's convention.
  (S code / S validation, display-only/friendliness — low priority, deprioritised sky-atlas surface.) Found by an
  adversarial audit of the plate-solving path (`solve/*` + its persistence/consumers), which otherwise traced
  clean — WCS parse, solve-success detection (returncode + sidecar), RA-wrap in the center consumers, hint
  unit conversion, and setup-error classification all held.
  _(Scout 2026-07-21 — **reproduced the 2θ divergence + pinned the provenance**, strengthening confidence the
  code (not the convention) is wrong, while the fix stays real-data-gated. (1) **Provenance:** the
  `rotation_deg` fed to `_tan_wcs` is, by definition, ASTAP's **`CROTA2`** keyword — `solve/astap.py:359`
  reads `rotation = values.get("CROTA2", 0.0)`, carried unchanged through `runner.py`→`project.py`→`sky.py`
  (`_representative_pixscale_rotation`). So the code is converting a genuine CROTA2 with a hand-rolled matrix,
  and the correct target is the **FITS-standard** CROTA2→CD conversion (which is exactly what `astropy.wcs`
  applies when you set the `CROTA2` keyword). (2) **Reproduced** (astropy `WCS`, run under `.venv`): comparing
  the code's CD matrix against the FITS-standard conversion (`CDELT1=−scale`, `CDELT2=+scale`) by the on-sky
  position angle of the image "up" axis — at `CROTA2=30°` the code places the overlay at PA **30°** vs the
  standard **330°** (a **60° = 2θ** error); at `CROTA2=0°` the two agree **exactly** (diff 0.0) and the CD
  determinant is `−scale²` (correct RA-left celestial parity), so there is **no hidden global y-flip masking
  the sign** — the divergence is purely the rotation term, genuinely reversed. (3) **Still NOT a blind fix,
  same gate as before:** whether ASTAP actually emits a FITS-standard-signed CROTA2 on a real Seestar solve is
  the one thing a synthetic can't settle; astropy's standard conversion assumes it does. So validate on one
  **real** solved Seestar frame with a known non-zero field rotation before flipping both off-diagonals to
  `−scale·sinθ`, and pin the sign with a known-orientation regression test. This is the same underlying bug as
  Sky-map placement Bug 2 (the ⭐ owner-reported entry above) — fix them together. Repro kept in the session
  scratchpad (`wcs_repro.py`).)_

---

## Ideas (priority order — work top sections first; AGENTS.md §1)

> **⚠ Scout — the Ideas list is running stale: several entries below were already
> fully implemented in code but never struck through.** In a single 2026-07-22
> Builder run, five "open" ideas were found already shipped (SExtractor sky-mode
> guard across all 4 sites; plate-solve per-rung timeout fall-through in
> `astap.py`; the "Clouds & haze" transparency-trend card; the Stack-form
> photometric-normalize nudge; the √N "should I keep shooting?" text via
> `readiness.ts`) — each cost real investigation time before being ruled out.
> They've been curated to Shipped this run, but **please do a full sweep**: grep
> the codebase for each open Idea before leaving it open, and strike through
> anything already built. A stale backlog makes every Builder run start by
> re-discovering finished work.

### Autonomy & friendliness (PRIORITY 2–3)

- **LEAD (Builder 2026-09-14, read off a `--mosaic` dogfood pass that was otherwise CLEAN) — the mosaic
  effort clause prices the grid from scratch on a target that is *already a mosaic*, and its own stand-down
  was argued for a target that is not.** *(Pillar: friendliness / trust — PRIORITY 3; size S to write,
  **M to be sure of** — it is real-data-gated; low severity. Confidence: the two sentences were photographed
  in a browser this run on the bundled 2×2; the arithmetic on the owner's own mosaics is **not** measured.)*
  On `Sample_M42_mosaic_2_2` — a target that **is** a 2×2 mosaic — the framing note reads *"About a 3×3 mosaic
  (9 panels) covers all of it. Giving all 9 panels the depth you'd give one field (~2 h each) is about 18 h of
  shooting"*, which is the identical sentence the single-field sample gets. `mosaicEffort.mosaicDepthText`'s
  own docstring says this is deliberate — *"the panel grid is a NEW way to shoot the object, and the subs
  already on one pointing are a few minutes against a figure in hours… being about 'next session' rather than
  'what's left', it deliberately does not try to subtract them"* — **and that argument is about a target the
  owner has not started.** It is the half the stand-down did not consider: on a target that already carries
  four panels the premise ("a few minutes against hours") is an accident of the sample's depth, and the owner
  is a heavy mosaic user with 26 mosaics, some many nights deep. There, *"about 18 h of shooting"* may be
  quoting a job most of which is done.
  **Why it is filed rather than built, and what to check first.** It is **not** obvious that the existing
  depth carries over: `mosaic_plan` derives a grid from the object's size and the owner's measured frame
  field, and a 3×3's panel centres are not a superset of a 2×2's — so "you already have 4 of the 9" may
  simply be false, in which case 18 h is the honest number and the right answer is **(b) leave it alone**.
  The measurement that decides it is on the owner's own library, not in this repo: take a real
  `<T>_mosaic_sub/` target with a `partial` verdict, and compare its **measured** per-panel coverage
  (`coverage_median_depth` / the `pointing_groups` the panel map already computes) against the plan's grid.
  Only if the existing pointings genuinely fall inside the proposed grid is there a *"~10 h of that is still
  to shoot"* to say — and even then it wants to be a clause on the existing sentence, not a third figure in
  hours (the standing "extremely busy" priority). **Do not blind-subtract the banked hours.**
  **↳ REPRODUCED A SECOND TIME, 2026-09-17** (Builder, a post-v0.450.0 `--mosaic` pass that was otherwise
  CLEAN — record in [`PROCESS-NOTES.md`](PROCESS-NOTES.md)). Unchanged, word for word, on the same 2×2. The
  gate is unchanged too: it is the owner's own library that decides, not this sample. Noted so the count of
  reproductions is honest rather than to re-argue the entry.
  **↳ THE DISCLOSURE HALF SHIPPED AS v0.451.1, 2026-09-17; the subtraction is still gated exactly as above.**
  *(Builder, the run that reproduced it a third time — `GET …/stack-runs/1/framing` on the live scratch install
  answers `level: partial, canvas: "mosaic"` on the 2×2, which is what made the fix decidable without the
  owner's library.)* What shipped is **not** a number: `mosaicDepthText` takes an `alreadyAMosaic` flag and, on
  a picture that is itself a mosaic, ends *"— the whole grid from scratch, not counting what this picture
  already has."* That is true whether or not the existing pointings fall inside the proposed grid, so it needs
  none of the measurement this entry is gated on; it closes the *misreading* (three sentences in a row, the
  first two about what is left, the third silently about the whole job) without guessing at the hours. The
  flag comes from `StackFraming.canvas`, the same fact `framingTitle` already switches on two functions up, so
  a single-frame picture and an older backend that omits it get today's sentence byte for byte.
  **What is still open is exactly what was open before: whether there is a "~10 h of that is still to shoot"
  to say at all**, which is still the owner's-library measurement above. Do not blind-subtract the banked
  hours; and note the clause now makes the assumption visible, which lowers the urgency of ever doing so.

- ~~**LEAD (Builder 2026-09-14, photographed on the bundled single field while shipping the v0.443.0 framing
  rung) — the readiness card still prices the canvas the coaching card has just told you to stop shooting.**~~
  — **✅ SHIPPED v0.444.2** (Builder 2026-09-14); entry cut to [`SHIPPED.md`](SHIPPED.md), one-liner under
  "Shipped" below. Built as the lead's shape (a), and its **"check first"** is what settled the gate: the
  question *"how often does a `partial` verdict co-occur with a readiness card?"* is already answered by the
  number v0.443.0 measured — `partial` fires on **any** object bigger than its canvas (95 % captured
  included), which is most of a big-object library, so the clause is gated on the *fragment* bar
  (`FRAMING_MAX_COVERAGE`) rather than on the verdict. Shared as one predicate, `framingIsFragment`, so the
  card that scopes the goal and the card that prescribes the wider framing cannot come to different opinions
  about which canvas is the right one.

- ~~**LEAD (Builder 2026-09-14, found by a `--mosaic --editor` dogfood pass that was otherwise CLEAN) — the
  coaching card and the framing card prescribe *different next sessions*.**~~ — **✅ SHIPPED v0.443.0**
  (Builder 2026-09-14); entry cut to [`SHIPPED.md`](SHIPPED.md), one-liner under "Shipped" below. Built as the
  lead's shape (a), a new `framing` rung, with the crowding-out risk answered by a coverage bar rather than by
  the verdict alone: `partial` fires just as readily at 95 % captured, so the rung asks for a third or more of
  the object to be *missing* (`FRAMING_MAX_COVERAGE = 0.67`). The lead's "check first" was carried out and is
  what set that bar.

- ~~**LEAD (Builder 2026-09-13, filed with v0.438.10) — a cropped export reports its depth against
  the canvas it has left.**~~ — **✅ SHIPPED v0.438.13–v0.438.14** (Builder 2026-09-13); entry cut to
  [`SHIPPED.md`](SHIPPED.md), one-liner under "Shipped" below. The lead's own first instruction was
  carried out first — measured on the bundled 2×2 mosaic against its `_framecov.fits` — and it answered
  the lead's open question: the two halves it separated really do diverge differently (the border trim
  +6.0 %, a content crop **+217 %**), but they take **one** rule, because reading the source stack's
  canvas is within 1.8 % / 12.8 % and errs *low* in both where the row's own canvas errs high.

- **LEAD (Builder 2026-09-13, the two halves v0.437.6 deliberately left out) — the "My best pictures" wall
  now *says* a mosaic's depth but nothing on it *shows* the thin case, and the scale it says it with is a
  canvas mean rather than the measured depth.** *(Pillar: trust — PRIORITY 3; size S each; **read the
  reasons before picking either up**, both were weighed and declined on purpose.)*
  (a) **No thin-stack cue.** `FrameCountBadge` turns orange on a picture that is one sub deep everywhere, and
  the Gallery card of the very same run shows it — the wall does not, because it has no badge row at all, only
  the one-line caption. v0.437.6 put the honest number *in* that caption, which is most of the value; a badge
  would be a new element on a wall the standing IA priority says not to add elements to. Worth it only if a
  thin raster is actually seen sitting high on the wall.
  (b) **`coverage_median_depth` is the directly measured depth**, where `field_fulls` is canvas area ÷ one
  native frame (a mean, which `perPixel.ts` argues is the right conservative choice for surfaces that
  *report*). On the bundled 2×2 sample they agree to 4 % (6.0 vs 5.78). It was **not** used here because it is
  lazily backfilled (`coverage_backfill`, on the request that grades a run) and so `None` on most runs nobody
  has opened — and this ranking is *set-relative*, so a healed run and an un-healed one would be normalised
  against each other in two different currencies. If it is ever used, it has to be all-or-nothing across the
  candidate set, not per entry.

- ~~**LEAD (Builder 2026-09-12) — the "Add more to what you're shooting" table loses its last column to a
  target's own `safe_name`.**~~ — **✅ SHIPPED v0.437.2** (Builder 2026-09-13); entry cut to
  [`SHIPPED.md`](SHIPPED.md), one-liner under "Shipped" below. Built as the lead's own shape and its Care note
  honoured exactly — the new `tonight.targetRowLabel` changes the **already-targeted branch only**, and the
  catalog rows still read `M31 — Andromeda Galaxy`. One thing the lead had not checked and the fix did: a
  renamed target's `name` and `safe_name` genuinely diverge (`rename_target` leaves the folder alone on
  purpose), and the name is the half a reader recognises — so the row shows it, and the safe name stays what
  it already was here, the link's destination.
- **NEW IDEA (Builder 2026-09-03, the cost the v0.335.0 endpoint knowingly accepted) — `/rejection-outlook`
  pays for a whole `estimate_stack` to learn two numbers.** *(Pillar: performance — size XS; **only if the
  note is ever un-gated**, see the entry two above.)* It needs the accepted+solved count and the mosaic's
  per-pixel depth, and takes both off `estimate_stack`, which also picks a reference frame and computes the
  union canvas. That is the right call today — one definition of `panel_depth`, and the query is only issued
  when a streak is present, so a target page normally never asks. But if the note is ever shown unconditionally
  it becomes a per-page-load canvas computation across the library's biggest targets, and the cheap
  equivalent already exists: `auto_reject_depth(_frame_radecs(frames))` (grid-snapped, sub-millisecond — see
  the measurement above) plus a plain count, no canvas at all. **Care:** the two are not identical —
  `estimate_stack` drops the gross plate-solve outliers `compute_mosaic_canvas` excludes before counting, and
  the cheap path would not, so a target with a few wild solves would report a slightly higher `n_frames`.
  Pin that difference in a test before swapping, or the "reaches" answer moves for a reason nobody can see.

- **NEW IDEA (Builder 2026-09-02, spotted while building the v0.323.1 print button) — sweep the app for
  sentences that *name* a number the form could just set, and give each one the button.** *(Pillar: autonomy —
  PRIORITY 2; size XS per site once found. Confidence: two live sites already have the button, the rest are
  unenumerated.)* The Stack form now has two: the `memoryFix` button ("Use drizzle ×1.4 instead — fits at ~2.1
  GB") and, as of v0.323.1, the print one ("Use drizzle ×1.4 — prints at A3"). Both existed first as a
  *sentence* naming a machine-actionable value, and in both cases the knob was inside the collapsed advanced
  disclosure — so the sentence was advice a beginner could read and not act on. **The identifying test:** does
  the copy contain a concrete value (a scale, a κ, a count, a mode name) that some control on a screen the user
  can reach would accept? If yes, it is a candidate. **Named starting points, none checked yet:**
  `drizzleTooFewHint` ("consider turning Drizzle off" — a boolean, so trivially actionable),
  `drizzleClipHint` (names `drizzle_reject` outright), `backgroundModeNudge` (names a mode), and the
  calibration-suggestion copy. **Care, and the reason this is a sweep rather than a rule:** a button is a second
  element on a dense form, against the owner's standing "extremely busy" priority — so each site has to justify
  itself the way the print one did, by being *conditional on something rare* rather than always-on. An advisory
  that fires on most stacks should stay a sentence. And check the query-key trap the print button hit: a fix
  that sets two form keys must land them in **one** state update, or the panel re-queries through an
  intermediate state and flickers between two verdicts.

  **⚪ SWEPT AND CLOSED — every named starting point already has its button (Builder 2026-09-04, read in the
  code, not assumed). Do not re-pick this.** All four candidates the entry names were checked in
  `frontend/src/routes/Stack.tsx` as it stands: `drizzleTooFewHint` has *"Turn off Drizzle"*, `drizzleClipHint`
  has *"Turn on drizzle outlier rejection"*, `backgroundModeNudge` has *"Use <mode> background flatten"*, and
  the calibration-suggestion copy has **"apply recommended"** (`applyRecommended`, which sets every
  recommended master *and* `scale_dark_to_light` in one go, precisely because applying half of a
  scaling-dependent pairing would mis-subtract the pedestal). The neighbours are done too — the min/max
  weighting hint, the transparency hint, the quality-weighting and photometric nudges, the drizzle nudge and
  the two memory fixes all carry theirs. **The identifying test still stands for anything newly written**
  (does the copy name a concrete value some reachable control would accept?), and so does the entry's care
  note — a button earns its place by being *conditional on something rare*; an advisory that fires on most
  stacks stays a sentence. But there is no backlog of un-actioned sentences left on the Stack form to sweep.

- ~~**NEW IDEA (Builder 2026-08-30, the generalisation of the v0.311.3 "First light" bug) — sweep every date the app shows a beginner and ask whether it means *when you shot this* or *when the app did something*.**~~ — **✅ SWEEP FINISHED; cut to [`SHIPPED.md`](SHIPPED.md) 2026-09-11 (search "sweep every date") — do not re-pick it.** All five named surfaces are closed (Dashboard strip, keepsake and Target hero by earlier runs; the Gallery card and History row as v0.321.2; the Sky footprint line as v0.321.3), and the Library tile was measured to show no date at all — it reads `last_activity_utc` only to *sort*, which is the Care note's own exception. The rule that survives, and the only part still worth reading: **a stack run's own timestamp is right for "which run is newest" and wrong as the caption on a picture**; where both dates matter, say both ("shot 15 Nov 2024 · stacked 30 Aug 2026") and never flip a *sort* to capture time. `pictureDateLabel` / `formatStampDateTime` are the shared helpers — use them rather than slicing an ISO stamp.
- **NEW IDEA (Builder 2026-08-30, the one case the v0.312.1 tint fix deliberately fenced off rather than
  solved) — a many-sub stack whose canvas is no bigger than its preview still gets the cyan wash.**
  *(Pillar: trust — PRIORITY 3; size S–M; **low urgency, and check the case is reachable before building**.)*
  The fix subtracts the map's own uniform noise floor only where the resize *averaged*, because at 1:1 a trail
  pixel and a noise-tail pixel are both "one sample lost here" and nothing pointwise separates them — measured,
  a floor there zeroed every count-1 pixel of the planted trail. So a dense map rendered 1:1 is deliberately
  byte-identical to the old, washed behaviour. **That needs a canvas no bigger than the stored preview (capped
  at 1024 px on its long edge), which for a Seestar stack means a small crop** — so it may not be reachable at
  all, and the *first* thing to do is find a real run where it fires. **If it is reachable, the honest fix is a
  genuine local density**: area-average the counts over a small neighbourhood before thresholding, instead of
  relying on the output resize to do it. **Care:** that would dim a lone hot pixel, which
  `test_pixels_that_lost_nothing_stay_fully_transparent` and `test_a_lone_hot_pixel_does_not_hide_the_trail`
  both pin — so it needs a shape that keeps a single high-count pixel opaque while spreading a count-1
  neighbourhood, not a plain box filter.

- **🟡 SWEPT ONCE, ONE UNTRUTH FIXED (Builder, v0.309.1, branch `claude/compassionate-galileo-x2nj2o`); the
  colour-space axis is still open below — QA LEAD (Builder 2026-08-30, generalised from the v0.308.1 copy fix)
  — sweep every download control's *copy* against what its endpoint actually serves.** *(Pillar: trust.)*

  **Found and fixed: "Full-res PNG (native size)" is not native size on a big mosaic — and History printed the
  exact dimensions the file misses.** `download_full_res_png` renders through
  `_FULL_RES_PNG_MAX_LONG_EDGE = 8000`, a deliberate ceiling that bounds the render's memory and the response
  on a RAM-capped NAS. Four surfaces described that file and none of them knew: the Target page's and the
  Dashboard strip's menu items said *"(native size)"*, the shared `ImageLightbox` menu said it on **three more**
  surfaces (Gallery, My best pictures, History's viewer), and History's artifact menu went furthest —
  *"Same look, full size (12000×9000 px)"*, quoting a number the download demonstrably does not have. Exactly
  the size axis this entry named, on exactly the picture where it matters: the owner's union mosaics, and
  discovered at the worst moment (trying to print from a backup). This is also the *destination* the v0.308.1
  fix redirected people to — the wall card now says "to print one, open it and choose Full-res PNG" — so the
  two lies were chained.

  **The fix is one sentence in one place.** New `frontend/src/fullres.ts` owns the wording
  (`fullResPngCapped` / `fullResPngLabel` / `fullResPngHint`), so five surfaces cannot drift into five claims
  about one file. Wording is **unchanged for every canvas the render really does serve whole** — the point was
  never to hedge everywhere, only to stop claiming native size where it is false; a capped picture gets
  *"Full-res PNG (up to 8000 px)"* and, where there is room for a hint, the canvas it was capped **from** plus
  the pointer to the FITS/TIFF that do hold those pixels. `ImageLightbox` takes an optional `fullResCanvas`
  (a surface that doesn't know the dimensions keeps the common wording, which is right under the cap), and
  `/api/stats`'s `recent_stacks` gained additive `canvas_w`/`canvas_h` so the Dashboard strip can answer too.

  **Upgrade-safe (§9):** two additive response fields with `0` defaults that read as "unknown" (an older
  frontend ignores them; an older backend omitting them gets the common wording). No config, schema, on-disk,
  default or API-shape change; the endpoint's behaviour is untouched — only what we *say* about it.

  **Tests (+11).** The claim is pinned to **bytes, not strings**, as the entry demanded:
  `tests/webapp/test_full_res_png.py` renders a canvas past the *production* ceiling (not an injected one) and
  asserts the served PNG is `!= native` and capped exactly at it, plus the boundary case *at* the cap coming
  back whole. `tests/test_fullres_cap_mirror.py` is the drift guard — the hand-mirrored TS constant against
  `_FULL_RES_PNG_MAX_LONG_EDGE`, same shape as `test_pace_constants_mirror.py`, because a stale copy would put
  the untruth straight back with nothing failing. Then `fullres.test.ts` (5) over the wording itself, and one
  test each on `ImageLightbox` and `History` that the capped picture stops claiming native size while an
  ordinary one still quotes its exact dimensions.

  **What the sweep found *not* to be wrong** — recorded so it isn't re-walked: the pictures zip (fixed in
  v0.308.1, and its "open it and choose Full-res PNG" pointer is now true too); "Quick preview PNG (up to
  1024px)" (`PREVIEW_MAX_WIDTH = 1024` is a *width* cap and History words it "up to 1024 px wide", which is
  exact); the JPEG, nameplate, scale-bar and keepsake items, which describe what they bake rather than a size;
  and the FITS, whose "Raw data — for re-processing, not sharing" is right.

  ~~**Still open, filed as its own item below:** the **colour-space** axis — the TIFF download carries *no*
  description at all, and a plain stack's TIFF is written **linear**, so it opens looking black.~~ — **DONE, and
  this line was stale** *(struck 2026-09-08 by a Builder that grepped before building)*: `frontend/src/tiffDownload.ts`
  owns the wording (`tiffOpensAsShown` / `tiffDownloadHint`) and every TIFF item renders it through the shared
  `SavePictureMenu` — *"16-bit raw levels — opens dark until you stretch it in another app"* for a linear stack,
  *"16-bit — the finished picture, at full depth"* for one saved in display space, with `tiffDownload.test.ts`
  pinning both. The
  **geometry** axis (cropped/rotated vs the stored canvas) was not swept.
  **▶ The geometry axis was then swept by the `…-e1p1x8` Builder and turned up a real one straight away:**
  "Full-res PNG (native size)" served a picture **rotated away from the one on screen** on any run saved North
  up — fixed as **v0.311.1**, entry at the top of "Bugs (fix these first)". The *crop* half of that axis (a
  preview that shows only part of the canvas) is still unswept.

  **▶ Swept independently in the same hour, on the SAME axis, by the `…-e1p1x8` Builder — and the two halves
  are complementary, not duplicates: that run fixed the FILE where this one fixed the COPY.** The wallpaper
  and the share JPEG were both *made out of* the 1024 px preview, so no wording could have made them honest —
  the presets name real device resolutions (1170 × 2532 …) and the endpoint fed the crop a third of that.
  Fixed as **v0.310.0** (wallpaper) and **v0.311.0** (share JPEG, keepsake and scale-&-compass), both entries
  filed below. So on the **size** axis the sweep now stands at: full-res PNG copy corrected (v0.309.1),
  pictures zip corrected (v0.308.1), wallpaper and share JPEG *re-sourced* (v0.310.0 / v0.311.0). Also swept
  and cleared by that run: the share JPEG's own "served at the same resolution" docstring, which was true and
  is now obsolete rather than wrong. ~~**Still open on size:** the **zoom clip** (built from the same preview,
  and the cap sets its resolution directly — 569 px where 640 was available)~~ — **SHIPPED v0.400.0**: the clip is
  now cut from the same cached share render every other hand-out already uses, so it comes out at the
  `CLIP_LONG_EDGE` it always asked for and its deepest frame is supersampled rather than the preview at 1:1
  (`_zoom_clip_source`, `zoom_clip_min_source_long_edge`, `ZOOM_CLIP_SOURCE_OVERSAMPLE`); entry in
  [`SHIPPED.md`](SHIPPED.md). **Still open on size:** the wallpaper/share on a
  **"Process target"** run, which both deliberately decline.
  **▶ The print export was swept 2026-09-13 and turned up a real one on a fifth axis the entry hadn't named —
  *the lever*, not size/colour/geometry:** the export job's refusal promised that "another night or two of subs"
  would fix a picture that needs pixels, contradicting `print_advice`'s own documented rule — fixed as
  **v0.438.5**, which also made the refusal share the offer's wording so the two cannot drift again. The
  **montage/wall** was read in the same pass and is **clean** (`montage_title`'s count and integration are both
  taken from the tiles actually placed, and `_montage_tiles` resolves the same cover-then-newest picture the
  Library tile does). ~~**Still untouched on any axis: the imaging log.**~~
  **▶ The imaging log was swept 2026-09-13 and the axis it failed on was neither size, colour, geometry nor
  the lever — it was *how many rows a thing is*.** On any library where a picture has been finished in the
  editor, the log printed that night **twice**, and the duplicate led the file with no integration time and
  "none" under Calibration. The root cause was upstream of the log and wider than it:
  `_apply_editor_to_run` carried the source run's capture window forward and nothing else, so every editor
  export the app has ever written is a `stack_runs` row with `total_exposure_s`, `calstat` and
  `transparency_ratio` NULL — which is also why the Gallery and History cards of a *finished* picture named no
  integration, and why "My best pictures" ranked it over two of its four metrics. Fixed as **v0.438.7** (the
  export carries the facts about the light, and documents the columns it must *not* — `is_mosaic` is read
  behaviourally by `editor._run_is_mosaic`), **v0.438.8** (`derived_from_run_id`; one row per stack in the
  log) and **v0.438.9** (`webapp/derived_light.py`, the read-side heal for the exports already on disk).
  Entries in [`SHIPPED.md`](SHIPPED.md). **Every download control has now been read on some axis**; what the
  sweep has never been run against is the *listings* — a card's copy vs the row behind it — which is where
  this one actually lived.
  **▶ The listings had their first pass 2026-09-13 and it turned up one straight away, on a sixth axis: *a
  setting that was asked for vs a setting that counted*.** The Gallery card's headline chips are read off
  `options_json`, and min/max rejection discards `quality_weighted` — so a run the engine had stamped
  `WGTSKIP` on carried a violet "Quality-weighted" chip an inch from the "min-max" chip that had thrown it
  away, contradicting History's own run-info panel about the same picture. Fixed as **v0.438.15**. **The
  transferable rule, and where to look next:** a listing renders from the *stored request*, while every
  surface that makes a verdict renders from the *recorded result* (a header card, a measured column) — so
  the listings are where a request that the engine declined survives as a claim. The same run then found a
  second one a layer down — the settings *list* under those chips printed `Off` against the two passes a
  mosaic canvas runs by itself — fixed as **v0.438.16**, which also added `GalleryItem.is_mosaic` and
  `frontend/src/stackSettings.ts` as the one place "the stored value is not the whole truth" is recorded.
  **What is still unread on this axis:** `Gallery.highlightBadges`' other two chips — `background_flatten`
  (the stack path degrades to **no** subtraction when any channel's fit fails, v0.173.2) and
  `lucky_fraction` — and, more promising, the *other* listings: the Library tile, the Life list, "My best
  pictures" and Compare's side-by-side, none of which has been read against the row behind it. Note that
  `final_gradient_removal`'s **chip** is still absent on a mosaic that got the pass (the chip is driven by
  the stored option, and only the settings row was annotated): an *under*-claim, deliberately left, because
  a chip that fires on every mosaic is noise on the one row the IA priority says not to lengthen.
  **▶ The four "other listings" were read 2026-09-14, and the axis turned out to have a second face on them
  (two shipped as v0.440.0 / v0.440.1).** On the Gallery card the divergence is *stored request vs recorded
  result*; on a listing that renders no options at all, it is **one page telling the same fact two ways** —
  which is the same failure and invisible to a sweep looking for a settings row. **Compare** (v0.440.0):
  `AbSide`, the A/B provenance strip above Split and Blink, printed a raw `n_frames_used` where the Side-by-
  side card on the *same page* has run the identical number through `FrameCountBadge` — and so through
  `field_fulls` — since v0.437.7, so a mosaic's thin-stack cue vanished the moment you changed comparison
  mode, under a docstring claiming those modes are "as trustworthy as Side by side". **"My best pictures"**
  (v0.440.1): the wall's count-badge hint described the ranking as *"total integration time, cleanliness,
  and frame count"* — three of the four metrics `PORTFOLIO_WEIGHTS` blends, with the leading one called a
  **total** where `rank_portfolio` deliberately reads it per pixel. **Clean on the other two, and checked
  rather than assumed:** the **Library** tile's `total_exposure_s` is summed `accepted_only=True`
  (`library.py::update_target_stats`), so it agrees with the `n_accepted/n_total` badge beside it; the
  **Life list**'s `captured` gate and its "You've captured N of 110" header read one function
  (`lifelist.build_life_list`), so the tiles and the count cannot disagree. *(One judgement call recorded,
  not filed as a bug: `build_life_list` gates on `n_frames > 0` rather than `n_frames_accepted > 0`, so a
  target whose every sub was graded out still lights up "Got it" — arguable either way, since he did point
  the scope at it, and the tile already has its own "Not stacked yet" state.)*
  **And one genuine divergence measured and NOT shipped — read this before picking it up.**
  `Gallery.highlightBadges`' `lucky_fraction` chip ("Lucky 50%") is a claim about what fraction was kept,
  and `stacker.run_stack` (~line 2714) keeps `kept + without_fwhm`: frames carrying no QC FWHM are ranked by
  nothing and kept *whole*, and when **no** frame has one the selection is skipped silently. So the real
  kept fraction runs from `lucky_fraction` up to 1.0 and nothing records which. **Left alone deliberately:**
  `lucky_fraction` defaults to 1.0, no automatic path sets it, and there is no recorded result to render the
  honest number from — so the fix is an engine provenance stamp on an opt-in advanced knob, not a copy
  change, and it is a long way down the value list. Do not "fix" it by making the engine drop un-measured
  frames: keeping a frame whose sharpness was never measured is the safe direction.

  Original spec, for the record:

    *(Pillar: trust — PRIORITY 3; size S per surface, and the sweep
    itself is one run.)* "Download all my pictures" promised **"the full-size pictures themselves"** and handed over
    1024 px previews; nothing failed, no test caught it, and it would have been discovered by a user at the moment
    it cost them most (trying to print from their backup). That is a **bug class**, not one slip: a download's copy
    is written once, next to the button, and then the endpoint underneath it evolves — the picture it serves gets
    capped, re-rendered, cropped, tone-mapped or renamed — with nothing tying the two together. **The sweep:** for
    every control that hands over a file (the pictures zip, the montage, the wall, the keepsake, the print export,
    the wallpaper, the zoom clip, the share JPEG, the full-res PNG, the imaging log, each artifact kind on
    History's menu), read the sentence beside it and then read what the handler actually writes, and reconcile the
    two — **fixing the copy where the file is right, and the file where the copy is right.** The properties that
    keep drifting are **size** (capped preview vs native), **colour space** (linear TIFF vs display-space), and
    **geometry** (cropped/rotated vs the stored canvas). Where a claim is worth keeping true, pin it with a test
    that reads the served bytes rather than the string — `tests/webapp/test_north_up.py` is the shape.

- **PERF WATCH ITEM (Builder 2026-08-30, introduced knowingly by the v0.301.0 recipe-matched reveal) — the
  reveal's "before" is now a full edit pipeline per request, and nothing caches it.** *(Pillar: friendliness —
  PRIORITY 3; size S; measure before building.)* `reference-sub` has always debayered a full sub per request
  and answered `Cache-Control: no-store`; on an auto-edited run it now *also* runs the whole Auto recipe
  (gradient fit → colour calibrate → STF stretch → SCNR → saturation → auto curve, plus denoise/sharpen when
  the recipe carries them) over that sub, at the 1024-wide proxy scale. That is comparable to one live-preview
  render, in a threadpool, and only when the card is revealed — so it is very unlikely to matter, and it was
  shipped without a cache deliberately rather than guessing at one. **But measure it on the owner's box before
  assuming:** if a reveal on a big target is visibly slow, the pattern to copy is already in the same file —
  the noise-ratio endpoint's fingerprinted meta stamp (`NOISE_RATIO_META_PREFIX`, keyed on the master and the
  representative sub), which would key here on the sub *and* the recipe look, so a re-edit invalidates it.
  Don't add a cache on speculation; a stale "before" is worse than a slow one.

- **NEW IDEA (Builder 2026-08-27, spotted while fixing the v0.286.1 stack-time-crop sharpen bug) — the video
  still's stack-time crop *knows* its box and then throws it away, so every later operation has to infer the
  picture's shape from file sizes.** *(Pillar: trust / maintainability — PRIORITY 3. Size: S. Confidence:
  certain — this is the code the bug lived in.)*
  `_video_stack_body` computes `framing.box`, crops with it, and writes `crop_applied=True, crop_box=[]` —
  the empty list meaning "the *stack* did this, not an in-place edit". That overload is what made the
  v0.286.1 bug possible: two genuinely different on-disk shapes (a cropped soft backup vs a full-frame one)
  both present as "cropped, no box", and the fix had to recover the distinction by comparing PNG dimensions.
  That check is correct and now tested, but it is *inference where a fact was available*.
  **Shape:** record the stack-time framing in its own additive field (e.g. `stack_crop_box`, defaulting to
  `[]` so every existing `meta.json` reads exactly as it does today), leaving `crop_box` to mean only what it
  has always meant. The size test stays as the fallback for the stills already on disk — this is not a
  migration, it is making *new* stills self-describing. **Only worth doing alongside another change in
  `webapp/video.py`**, and only if the field earns its keep: if nothing but a comment would read it, the
  dimension check is already the honest answer and this should be closed rather than built. Explicitly do
  **not** rewrite the four in-place operations around it.

- **NEW IDEA (Builder 2026-08-17, the one thing deliberately left out of "Finish them all" v0.265.0) — put a real
  byte figure in the batch-export confirmation, without making the Dashboard's note expensive.** *(Pillar:
  friendliness / trust — PRIORITY 3; size S; **only worth doing if someone actually wants the number**.)* The
  confirmation currently says "N new sets of files, each about the size of the stack it came from" and points at
  Storage. That is true and enough to decide with, but it is a description rather than a measurement. **Why it
  wasn't just added:** `GET /api/gallery/unexported-edits` is read on every Dashboard visit and its stated design
  is that it does **no file stats at all** (`test_unexported_edits_never_lists_a_never_edited_targets_runs` pins
  the harder half of that), so summing each flagged run's existing outputs there would trade a cheap poll for a
  disk walk on every visit — the wrong side of the trade for a number nobody has asked for. **Slice, if it is ever
  wanted:** a separate `GET /api/gallery/unexported-edits/estimate` that the confirmation fetches **when the
  dialog opens**, summing the flagged runs' recorded `fits`/`tiff`/`preview` sizes (an editor export writes about
  the same set), so the cost is paid exactly when the user is deciding and never on the poll. **Care:** it is an
  estimate, not a promise — say "about", and don't block the button on it if the read fails.

- **PERF WATCH ITEM (Builder 2026-08-13, introduced knowingly by the ingest mtime fix v0.254.2) — a mass re-sync of
  `incoming/` now costs one FITS *header* read per touched frame, where it used to cost a QC reset.** *(Not a bug;
  recorded so a future run doesn't rediscover it as a mystery.)* `_same_capture()` only runs on the
  size-equal/mtime-moved path, so an ordinary re-scan of untouched files reads nothing extra and the hot path is
  unchanged. But the case it exists for is exactly the *mass* one: re-copy 8 000 subs without preserving
  timestamps and the next scan opens 8 000 headers. That is far cheaper than what it replaces (nulling QC on all
  8 000, re-QC'ing and re-solving them, plus the risk of an auto-stack firing in the gap), and it happens **once**
  per touch because the new mtime is adopted either way. **If it ever does show up as slow,** the cheap next step
  is to short-circuit on the *first* mismatch across a batch (if the first N touched frames all confirm as benign,
  the whole re-copy almost certainly is) — but measure before building that; a header read is milliseconds and the
  scan is already I/O-bound on the same files.

- **NEW IDEA (Builder 2026-08-08, the sibling question raised by shipping the walk-away quality weighting v0.251.0)
  — should the walk-away path also turn on `photometric_normalize`? NOT blind-shippable; needs a Scout vet on real
  data first.** *(Pillar: autonomy + image quality, PRIORITY 2/4; size S to build, M to justify.)* Weighting and
  photometric normalization answer the same complaint — *thousands of subs across nights of different transparency*
  — and the engine says they "compose cleanly" (`combine_weights_with_photometric`). Having just auto-enabled the
  first on the `auto=True` path, the obvious next question is whether the second belongs there too. **Do not treat
  this as a done deal, because the two are not equally safe.** Quality weighting only changes how much each frame
  *counts*, is floored at 0.1, falls back to a neutral 1.0 for any metric it couldn't measure, and is provably inert
  on the min/max path — worst case it does nothing. Photometric normalization *multiplies frame values* before they
  combine, so a mis-estimated scale changes pixels, and the "neutral fallback" only covers a frame with no
  `transparency_score` at all, not one with a bad score. It is also correctly off by default for that reason.
  **What a vet needs to establish, on the owner's real multi-night data:** (a) that the per-frame scales land in a
  sane band on an ordinary clear-night set (i.e. it's ~inert when transparency really is uniform, so we're not
  paying pixel risk for nothing); (b) that a genuinely hazy night is scaled *up* by a plausible factor rather than
  amplified into noise; and (c) that the rejection spread narrows rather than widens. **Related and already filed:**
  the "nudge the user on the Stack form when the transparency spread is wide and `photometric_normalize` is off"
  idea (search `suggest_photometric_normalize`) — that nudge is the *lower-risk half* of this and could ship first,
  since it asks the user rather than deciding for them. **If it does get built, mirror v0.251.0 exactly:** inject
  only on `auto=True`, only when the merged options carry no explicit key, and leave the engine default False.

- **NEW IDEA (Builder 2026-08-04, spotted while shipping "Point here right now" v0.231.0) — say "another hour
  would cut its noise about N%" in *one* voice across the app.** *(Friendliness / trust — PRIORITY 3; size S;
  pure dedup with a real user payoff.)* The new `nightplan.noise_gain_from_more_time(t)` = `1 − √(t/(t+1))` is the
  honest, beginner-legible answer to "would more subs help?", and the best-tonight card now says it in plain
  words. But the app has **several other places that answer the same question in different currencies** — the
  per-target integration goal / "is it enough yet?" readiness verdict, the `integrationTrend` line, and the
  "cut your noise ~N×" at-completion badge — each with its own framing. A beginner reading two of them shouldn't
  have to reconcile them. **Slice:** reuse the one helper (or its frontend mirror) so the readiness surface can
  add the same sentence, and check the wordings agree on the *direction* and *magnitude* of the claim. **Care:**
  don't collapse genuinely different questions into one — "have I shot enough?" (a goal) and "would another hour
  help?" (a marginal return) are related but not the same; this is about the *marginal-return* sentence only.

  **⚪ MEASURED AND STOOD DOWN — do NOT build this; the disagreement it exists to fix is not there
  (Builder 2026-09-11, branch `claude/sweet-babbage-kg3yfc`).** I did the entry's own first step — "check the
  wordings agree on the *direction* and *magnitude* of the claim" — against the real code rather than from
  recall, and it closes the idea instead of sizing it.

  **The two sentences are already one voice: the same formula, in the same currency.**
  `nightplan.noise_gain_from_more_time` is `1 − √(t/(t+h))`; `integrationTrend`'s projection is
  `1 − 2^−p` with `p` clamped to the ideal `0.5`, which is *the same expression* for `h = t`. Measured at
  the one point where both name the same extra time (a 1-hour target, where "another hour" **is** "double
  your time") they agree to the decimal: **29.29 % vs 29.29 %**. Direction agrees everywhere, and
  `integrationTrend` uses the target's own *measured* falloff exponent capped at ideal, so it can only ever
  under-claim relative to the theory — never over-claim.

  **What looks like a conflict is two different `h`, each stated in its own sentence.** At 20 h captured the
  Tonight card says ~**2.4 %** (for `h` = 1 hour) and the Target page says ~**29.3 %** (for `h` = 20 hours) —
  both correct, and neither is ambiguous, because each sentence names its own extra time out loud ("another
  hour" / "double your 20.0 h"). Full table, if it is ever re-examined (captured → +1 h → double-at-ideal):
  0.25 h → 55.3 / 29.3; 0.75 → 34.5 / 29.3; 1.0 → 29.3 / 29.3; 2.0 → 18.4 / 29.3; 5.0 → 8.7 / 29.3;
  20.0 → 2.4 / 29.3.

  **And the other half of the slice is a cost, not a win.** "So the readiness surface can add the same
  sentence" means putting a *third* marginal-return sentence on a page, against a standing owner complaint
  that the UI is busy and AGENTS.md §1's "prefer a consolidation over a new card". The retrospective
  surfaces this entry lists alongside them — `oneFrameVsStack` / `StackNoiseBadge`'s "stacking cut your noise
  ~N×" — answer *"what did stacking already buy me?"*, which the entry's own Care note fences off as a
  genuinely different question. So there is nothing left that is both in scope and worth doing.
- **NEW (Builder 2026-07-30, found while shipping the Check & locate outcome line v0.222.2) — the legacy desktop
  dialog reports "solved N/M" from a *progress counter*, so it claims a perfect solve on a field where nothing
  located.** *(Correctness of a user-facing figure — but in the **deprioritised** desktop GUI, so low priority;
  size XS.)* `seestack/gui/library_dialog.py:147` prints
  `f", solved {summary['solve_done']}/{summary['solve_total']}"`. `solve_done` is `_map_jobs`' progress counter —
  frames *attempted* — so it reaches `solve_total` even when every solve failed; the line reads "solved 40/40" on a
  star-poor field that located nothing. This is the exact defect the web Jobs page just avoided: `run_qc_and_solve`
  now also returns an honest **`solve_ok`** (results that came back with a usable WCS), so the fix is to read that
  instead and fall back to omitting the clause if it's absent. Left unfixed here deliberately — the desktop GUI is
  historical (`PLAN.md`-era) and its only tests are the three Qt ones, so a drive-by change at merge time wasn't
  worth it; take it if you're already in that file. Confidence: traced (the counter semantics are proven by
  `tests/test_solve_runner.py::test_run_qc_and_solve_reports_the_frames_it_actually_located`).
- **If a same-sky-area auto-merge is ever wired up, gate it on same-framing.**
  *(S, correctness — PRIORITY 2; latent, no live caller today.)* `library.
  find_target_within()` exists but is currently unused, so nothing folds a mosaic
  target into a single-field one by proximity. If a "merge by sky position" feature
  is built, it must **not** merge a mosaic target (`"<T> (mosaic)"`) into a
  single-field `"<T>"` (or vice-versa) just because they solve to the same region —
  their footprints/canvases differ. Gate on both-single-field or both-the-same-mosaic,
  not proximity alone. (Recorded here so the guard isn't forgotten when the merge
  lands.)

### ⭐ Editor — make it excellent (PRIORITY 1)

The editor is where a good stack becomes a good *picture*, and it has real
problems. Dogfood it every big-picture run and fix root causes.

- **Live preview** — the preview must show **every** enabled action (that's the
  whole point of it). **DONE (v0.57.0):** the last hold-out, Deconvolution, was
  `proxy_safe=False` and got *skipped* in preview (only a badge told you it was
  hidden); it now renders on the proxy with a `proxy_scale`-corrected PSF, and the
  pipeline no longer skips any op. What remains here is *responsiveness* (heavy
  ops on the proxy can lag) and closing any remaining proxy↔export look
  differences — chase those, but never by hiding an action again. (S–M, editor)
  **▶ RESPONSIVENESS, FIRST BITE — ✅ v0.382.2 (`webapp/edit_fit_cache.py`):** the
  measurements an op makes before it touches a pixel (the stretch's stats, the
  curve's points, colour calibration's star solve) are now carried from one
  live-preview render to the next for the **longest common prefix** of enabled
  ops. Measured on a 1500×1000 proxy carrying the one-click Auto recipe: **4.25 s
  a render → 2.39 s (1.78×)**, output **bit-identical**. Full entry, and the
  measured next slice, in [`SHIPPED.md`](SHIPPED.md).
  **▶ SECOND BITE — ✅ v0.382.3 (`seestack/edit/proxy.py::_load_map`):** and the
  bigger half was not in the ops. Each render also read the run's **full-resolution**
  coverage *and* frame-coverage canvases whole (`np.asarray(fits.getdata(…),
  float32)` materialises despite the memmap) before striding them to the proxy —
  two maps × two requests = four full-canvas reads and allocations per edit, on
  canvases that are hundreds of MB at this owner's mosaic sizes. Slicing before
  the cast: **2.65 s cold / 0.21 s warm → 0.011–0.021 s** per read on a 480 MB
  map, identical values.
  _(Builder note 2026-07-10: closed the big proxy↔export gap in the mosaic
  "Coverage leveling" op — its per-level pixel-count floor is now scaled by
  proxy_scale so the same panels are leveled in preview and export, v0.103.16
  (see Bugs → fixed). A **smaller, second-order parity nuance remains in the same
  op** and is filed here rather than blind-fixed: `level_by_coverage`'s object-mask
  dilation (`dilate_object_mask_px=4`) is a **fixed pixel count applied at both
  resolutions**, so on a ×N proxy it grows the star/nebula mask by 4 strided px ≈
  4·N full-res px — a wider sky exclusion than the export's 4 full-res px, which
  can shift a per-level sky median slightly between preview and export. Low
  severity (the median is robust to a few extra masked edge pixels, and the offset
  it shifts is tiny), so it didn't clear the bar for churn this run. If a future
  run touches this op, scale the dilation like the other pixel params
  (`round(4/step)`, matching `ctx.scaled_px`), guarding the step≥8 case where it
  rounds to 0. (S, editor/parity))_
  _(Builder note 2026-07-10, second addendum — verified while dogfooding a real 2×2 mosaic editor path
  (parity p99 1.5%, healthy): **measured the dilation nuance above and it is genuinely negligible** — on a
  ×4 proxy the far-sky per-level median it shifts moved only ~1e-4 of range (−4e-5 export vs −1.6e-4 proxy),
  well below the documented ~2% decimation-parity floor, confirming the "didn't clear the churn bar"
  disposition. **A distinct, symmetric floor nuance in the same op is worth folding into the same eventual
  fix:** the `_MIN_STRIDED_PIXELS = 12` safety floor makes `effective_min = max(12, round(200/step²))`, so on a
  *heavily*-strided proxy (step≥5 — reachable only on a very large mosaic canvas >7500px) the proxy requires
  **more** full-res-equivalent sky pixels than the export (step5→300, step6→432, step8→768, vs the export's
  200), so a thin panel with 200–768 full-res sky pixels is leveled in the export but *skipped* in the preview
  — the same preview≠export class the v0.103.16 fix closed at moderate stride, re-opening at heavy stride.
  Both are the *same* op and would be fixed together; both are low-severity edges (the floor is a deliberate
  "never median over a handful of pixels" guard, so any fix must keep a sane absolute minimum rather than let
  the proxy median run over <12 pixels). Neither cleared the churn bar alone; recorded so a future run in this
  op resolves the dilation scaling **and** the heavy-stride floor in one pass. (S, editor/parity))_
  **— BOTH NOW RESOLVED (Builder 2026-08-06, branch `claude/relaxed-turing-6zdskv`).** The **dilation
  scaling** turned out to have been done already: `edit/ops/background.py::_level_coverage` passes
  `dilate_object_mask_px=_scaled_box(ctx, 4, minimum=0)`, so the preview's object-mask halo is already a
  full-res-equivalent measure. The **heavy-stride floor** is fixed in **v0.237.2** — see the Shipped entry
  "Level a big mosaic's thin panel the same way in the preview and the export". Reproduced and measured on a
  ×6 proxy: the preview left a small overlap panel's **entire 162.7 ADU** offset in place while the export cut
  it to 30.0 (a **132.6 ADU** preview↔export divergence); the preview now lands on **30.7**. The floor is
  *not* loosened — `_MIN_STRIDED_PIXELS` still gates *measuring* a median — it is only no longer allowed to
  drop the level out of consideration, so a level it can't measure takes the neighbour-interpolated offset the
  export already gives its own unmeasurable levels.
- **Confusing / clunky controls** — too many ops with terse params and no obvious
  starting point. Add plain-language help, a simple/guided default layout, curated
  presets, and progressive disclosure of advanced ops so a beginner gets a good
  result without understanding every knob. (M, editor)
- **Weak default result** — the auto/default processing should produce a genuinely
  good image out of the box for a typical Seestar OSC stack (good stretch, colour,
  gentle denoise/sharpen). Improve the auto recipe so "Auto" is a great one-click
  start. (Gentle SCNR green-cast removal added to the auto recipe in v0.56.6 —
  more of these incremental tweaks welcome.) (M, editor)
- **Editor bug hunt (ongoing)** — there are undocumented issues. Each big-picture
  run, use the editor end-to-end and fix what's broken/ugly: op failures, export
  mismatch, undo/state glitches, mobile layout, error handling. (ongoing, editor)
  _(Builder note 2026-07-14, found dogfooding the beginner editor flow — **SHIPPED v0.121.6**
  (branch `claude/pensive-faraday-47ditq`): the editor showed an **endless spinner with no error**
  when its run was missing/deleted (a stale "View result" link, or the stack run deleted from
  History). `EditorView`'s render guard checked only `saved.isLoading`; on a `getRecipe` 404
  `isLoading` is false but `saved.data` is undefined, so the chrome rendered while the preview
  never seeded (the seed effect needs `saved.data`) — the panel fell through to a `<Loader/>`
  forever. There was no `saved.isError` branch anywhere, unlike the sibling `Target.tsx` route
  (which shows a `QueryError` + Retry for exactly this deleted/stale-link case). Fix: after the
  loading guard, show the shared `QueryError` (Retry) when `saved.isError && !saved.data` — and
  the same for `opsSchema` (the editor can't function without the op schema) — each gated on
  `!data` so a background-refetch blip never blanks a working editor. Frontend-only, additive; no
  backend/schema/API/default change. Regression `Editor.test.tsx::"shows a recoverable error, not
  an endless spinner, when the run is missing"` (getRecipe rejects → asserts the error card + Retry
  appear and the editor chrome does not; fails before as it spins). (S, editor/error-handling —
  PRIORITY 1.))_
  _(~~Builder note 2026-07-12, found in an adversarial frontend-editor-route audit: "Compare a
  look" → "Switch to this look" (`adoptLook`) silently dropped the user's crop/geometry — it set
  the look's **raw** ops, while the split preview the user was judging renders the look on the
  current edit's framing via `lookCompareOps(lookSel.ops, baseGeometryOps)`. So a user who cropped,
  compared a look, then switched to it got the **uncropped** frame — a different image than the
  split they'd just evaluated (WYSIWYG violation on the PRIORITY-1 editor compare→adopt loop).~~ —
  **SHIPPED v0.109.20** (Builder 2026-07-12). `adoptLook` now adopts exactly what the divider showed
  — `lookCompareOps(lookSel.ops, baseGeometryOps)` (the look's tone/colour/detail on the current
  recipe's enabled geometry ops) — so the adopted recipe renders identically to the compared split.
  A no-op when the current recipe has no geometry op (the look's ops verbatim, exactly as before), so
  the common case is byte-for-byte unchanged. Frontend-only, additive, one undoable step; no
  backend/schema/API change. Regression `Editor.test.tsx::"preserves the current crop when adopting
  the compared look (WYSIWYG)"` (crop in the recipe → compare a Curves-only look → Switch → assert
  both Curves **and** Crop survive; fails before as the crop is dropped / passes after). (XS,
  editor/consistency — PRIORITY 1.))_
  _(Builder note 2026-07-10: the `edit/ops/detail.py::_hot_pixels` NaN-fill/restore band-aid
  (the `_with_nan_filled` wrapper) is now **redundant** — v0.103.23 made
  `bg/hot_pixels.py::suppress_hot_cold_pixels` NaN-aware at the root, so the op no longer needs a
  caller-side shim to avoid no-oping on a mosaic/partial-coverage image. Low priority and not worth
  churn on its own: the shim is harmless (it feeds NaN-filled input to an already-NaN-safe function).
  If a future run is already in `detail.py`, it could drop the wrapper for `_hot_pixels` and call
  `suppress_hot_cold_pixels` directly — but only after confirming byte-for-byte parity (the shim
  repairs a hot pixel *at* a coverage boundary using a median-fill neighbourhood, where the root
  function leaves it, so verify that edge doesn't matter on a real mosaic before simplifying). (S,
  editor/maintainability))_
  _(~~Builder note 2026-07-11, found during the frontend editor-logic audit that shipped v0.109.6/v0.109.7:
  the editor's **histogram** query (`Editor.tsx` `hist = useQuery(["edit-hist", …])`) is **not** gated on
  `seeded`, unlike the `preview` query right above it…~~ — **SHIPPED v0.109.19** (Builder 2026-07-12). The
  `hist` query is now gated `!!opsSchema.data && !saved.isLoading && seeded`, mirroring the live preview, so it
  no longer fires against the empty pre-seed recipe before the saved recipe loads — removing a wasted request
  and the brief pre-seed histogram/clipping-advisory flash on first open (most visible on the walk-away
  Process-target deep-link, which opens on a saved auto-edit recipe). Frontend-only, additive; no
  backend/schema/API change. Regression `Editor.test.tsx::"does not fetch the histogram until the saved recipe
  has loaded"` (holds the recipe query pending and asserts `getHistogram` isn't called until it resolves —
  fails before / passes after). Upgraded from "too low-value to ship standalone" because it's on the PRIORITY-1
  editor default surface and the north-star walk-away flow lands there with a saved recipe, so the flash is
  genuinely user-visible there. (XS, editor/polish.))_
- **"Original" compare should match the stack's own baseline** — the editor's
  Compare ("Original") renders an *empty* recipe, which the backend tone-maps with
  a hard-coded default asinh (stretch 0.5 / black 0.35). **Analysis (2026-07):** that
  default *matches* the `render_stack_run` endpoint's own defaults (`_STRETCH_DEFAULT
  0.5 / _BLACK_DEFAULT 0.35`), so if the user saw the live adjustable render before
  editing, "Original" already lines up. The real mismatch is against the run's
  **stored** `preview_path` PNG (History/Target thumbnail), which `_write_preview_png`
  renders with `_autostretch_for_export` (MTF/STF), *not* asinh — a different look —
  and which `save_stack_preview` may have overwritten at a user-chosen stretch (whose
  values aren't persisted on the run). The clean, fully-honest fix is to serve the
  run's actual stored `preview_path` as the "Original" overlay (literally what the
  user saw), accepting that it's the ≤1024 px preview rather than the ≤1500 px editor
  proxy. Care: it's a behaviour change to Compare, so gate/validate the resolution
  swap doesn't jar the A/B. (S, editor/trust)
  _(Builder note 2026-07-11 — re-traced this after the v0.109.0 change and it is **not a clear win; do
  not blind-take it.** Two things have shifted the premise: (1) the empty-recipe "Original" render no longer
  uses the fixed asinh 0.5/0.35 — since v0.109.0 both editor fallbacks call `render.thumbnail.autostretch`
  (STF) at the **preview** `target_bg≈0.20`, so it already resembles the stored thumbnail's algorithm. (2) But
  the stored `preview_path` uses `_autostretch_for_export`, which is deliberately a **much milder** stretch —
  `target_bg=0.06, sigma_factor=-2.8` (`stack/output.py::_autostretch_for_export`, "sky at ~6% grey … deeper
  shadows clipped") vs the editor proxy's ~20% grey. So serving the stored preview as "Original" would make the
  A/B *baseline* markedly **darker** than the edited image on screen — arguably a **worse** before/after
  reference than the current same-exposure empty-recipe render, not a better one. The editor's Compare is an
  interactive same-view A/B, not an attempt to reproduce the History thumbnail; matching the thumbnail's
  exposure isn't obviously the right goal. If a future run still wants "literally what the user saw", it should
  first decide whether the darker export exposure actually reads better in the A/B (needs a real-image look), and
  handle the ≤1024 px vs ≤1500 px size mismatch under the Split divider. Left filed but **down-weighted** — this
  is a judgment call, not a blind fix.)_

### Autonomy — "just works" (PRIORITY 2)

- Auto-suggest stack settings from the data (frame count, FWHM spread, streaks)
  so the user rarely needs to touch the Stack form. (S–M, autonomy)
  _(Progress: the Stack form already carries a rich set of data-driven nudges
  (calibration picks, sigma/min-max frame-count guards, streak→min-max-k, transparency
  → quality-weight, transparency-spread → photometric-normalize, auto-grade drop-outliers,
  memory sizing). As of v0.84.6 every one of them is now one-click. A proactive **drizzle**
  nudge shipped v0.87.0 (see Shipped): on a large single-field set (≥200 accepted, solved
  frames — matching the field help's "200+ dithered frames") whose drizzle-*on* dry-run sizing
  fits the memory budget, the Stack form now suggests Drizzle with a one-click "Turn on
  Drizzle", so a beginner sitting on thousands of subs reaches the biggest resolution win
  without hunting the advanced knobs — gated on a feasibility estimate so it never nudges
  toward an OOM-refused run. Remaining genuine gaps a future run could pick up, each needing a
  careful classifier: **lucky_fraction** from FWHM spread (contentious — it drops signal, so
  weigh against quality-weighting); a background/gradient flatten nudge from a measured sky
  gradient.)_

- **NEW IDEA (Scout 2026-08-27 #17) — surface calibration *match confidence* on the interactive Stack form, so a
  watching beginner gets the same smart dark/flat matching the walk-away path already does — and understands why
  calibration is or isn't applied.** *(Pillar: autonomy + friendliness + image quality — PRIORITY 2/3. Size: S.)*
  **Why (real gap).** The unattended chains already auto-bind the library's best *confidently-matching* master
  dark/flat/bias when a walk-away stack has no calibration chosen — the whole `_confident_master_binding` →
  `calibration.auto_bind_master_paths` machinery exists and compares the target's median exposure/gain/temp and
  modal frame dims against every master (`webapp/pipeline.py:2122`, `2299`). But the **interactive Stack form**
  gets none of that intelligence: today its Calibration box only says either *"No masters built yet"* or shows a
  raw picker, and a beginner who *has* built a master has no idea whether it actually fits these subs. A 10s dark
  bound to 30s lights makes the picture **worse**, silently. **Proposal:** when masters exist, run the same
  read-only confidence check for the target being stacked and show a one-line verdict in the Calibration box —
  green *"Your darks & flats match these subs (30s · gain 80)"* when auto-bind would confidently pick them, amber
  *"Your only dark is 10s but these subs are 30s — it may not help"* when nothing matches, and offer the
  confident pick as the default selection so the interactive path lands on the same masters the walk-away path
  would. Pure surfacing of logic that already exists and is already tested engine-side; no new matching rules, no
  default flip (the user still chooses), no schema/config change. Fits the "reduce the number of decisions"
  mandate: the beginner stops having to *know* what a matching dark is. **Grep first:** `routers/stack.py` /
  `get_stack_defaults` — confirm the form doesn't already thread a confidence hint before building; reuse
  `_confident_master_binding` rather than re-deriving the match.
  **Builder 2026-08-29 — did that grep, and the premise is largely already false. RESHAPE BEFORE BUILDING.**
  The entry's claim that the Calibration box "only says either *No masters built yet* or shows a raw picker" is
  not what `routes/Stack.tsx` does. It already queries `calibrationSuggestions(safe)` and, via
  `src/calibrationFit.ts`, already renders: a **per-option misfit suffix** on every master in the picker
  (`masterOptionSuffix`, so a wrong-size master is visibly unusable), an **exposure-mismatch caution** naming
  both numbers and the fix ("This dark was shot at 10s but your subs are 30s — …"), a **temperature-mismatch
  caution**, a **bias-size warning**, a **"scale it with a master bias" nudge** when the library holds one, a
  **dark-already-contains-bias** note, and a prominent **"you have masters but aren't using them"** advisory
  with a one-click **apply-recommendation** button. So "a beginner has no idea whether it fits" is not the live
  behaviour, and a green/amber verdict on top of that would be a *sixth* piece of calibration copy on a form the
  owner already calls too busy.
  **What is genuinely left, and it is small:** the form's recommendation follows `recommend_masters` (best
  *available*), while the walk-away path follows the stricter `auto_bind_master_paths` (best *confident*) — so
  the two paths can pick differently, and the form never says "this is what the unattended stack would have
  chosen". The worthwhile slice is therefore **agreement, not more copy**: surface the confident binding as the
  pre-selection / one-click recommendation so the interactive path lands where the walk-away path would, and let
  the *existing* cautions keep doing the explaining. Do not add another advisory line.

  **✅ SHIPPED — that remaining slice (Builder, v0.321.0, branch `claude/wizardly-feynman-isps6l`).** Built exactly
  as the reshape asked: **agreement, and not one new line of copy.**

  **What the disagreement actually was.** `recommend_masters` ranks a dark by *combined* distance
  (exposure ×3 + gain + temp) and returns the single closest, so an **exposure-perfect but gain-mismatched**
  dark out-ranks a **gain-matched** dark that only needs bias-scaling. The unattended binder already knows
  better — it tries every dark in ascending distance and takes the first that clears a confidence gate — so on
  that library the Stack form recommended one dark and a walk-away stack of the same subs used another, and
  nothing on screen said so.

  **One function now answers "which masters for these subs?".** `auto_bind_master_paths` is refactored into a
  new `auto_bind_master_ids` (the decision) plus a thin path-resolving wrapper (what a run needs), sharing one
  `_BOUND_ID_TO_PATH_KEY` table, and `/calibration-suggestions` serves the ids as an additive `confident` key.
  A test pins the two forms as **one decision by construction** — every id resolves to exactly the path the
  unattended binding produces, and a kind absent from one is absent from the other — so they cannot drift
  apart again. The coverage roll-up (`master_coverage`) now reads the ids directly instead of resolving each
  binding to a file and looking the id back up in the registry.

  **The form prefers the confident pick where there is one, and is never *less* helpful than before.** The
  reconciliation is a pure `masterRecommendation` in `calibrationFit.ts`, with two deliberate couplings rather
  than a per-field merge: a **flat-dark travels with its flat** (the best-available flat-dark was matched to a
  different flat, so it is stale the moment the confident binding picks another), and a **bias is only offered
  beside a dark when it is there to *scale* that dark** — in which case "Use recommended" turns
  `scale_dark_to_light` on with it, because half of that pairing leaves the pedestal mis-subtracted. Where the
  binder is silent (nothing confident, or an older backend), every field falls back to today's best-available
  answer and the existing cautions explain it — which is the right behaviour with a human watching.

  **Upgrade-safe (§9):** one additive response key, one additive optional client field, no config, schema,
  on-disk, default or existing-response-shape change; `auto_bind_master_paths` returns exactly what it did
  (its 78 existing tests pass untouched), so the unattended path is byte-for-byte unchanged.

  **Tests (+5 python, +8 frontend; the two Stack-form ones fail before).** Python: the ids-and-paths
  agreement-by-construction, the scaling triple carried in id form, an empty answer when nothing is confident,
  and the endpoint serving `confident` — asserted **against the binder itself** rather than a copy of its
  answer — plus the wrong-camera case where the best-available recommendation still names a master and the
  confident one says nothing. Frontend: six `masterRecommendation` cases (fallback, preference, the flat-dark
  pairing, the bias+switch pairing, never half a pairing, bias-only-without-a-dark) and two on the real form —
  the badge and one-click landing on the gain-matched dark *with* its bias and the scaling switch, and the
  no-confident-pick case keeping today's recommendation and its warning.

- **IMPROVEMENT IDEA (Scout 2026-07-24) — a WCS-free star-registration *fallback* so a faint field whose subs mostly
  fail to plate-solve can still stack from all its frames, instead of collapsing to a ~1–3-frame gibberish stack.**
  *(Autonomy + image quality — priorities 2/4; a direct attack on the remaining root of the ⭐⭐ thin-stack/gibberish
  top bug. Size L — file as a scoped Builder slice, and flag the dependency question below for owner sign-off before
  any new package lands.)* **Why this is the highest-value autonomy gap:** the whole engine registers frames via ASTAP
  WCS + reprojection, and `run_stack` combines **only accepted *and* solved** frames. On a faint / sparse-star target
  ASTAP fails on most subs (the documented root cause the sibling-hint seeding v0.180.0, unsolved-surfacing, and the
  relaxed-retry idea all *mitigate* but can't fully cure — a genuinely star-poor field may be unsolvable no matter the
  hint). So hundreds of accepted subs sit unsolved and never stack, and the "stack" is the handful that did solve →
  per-pixel colour speckle. **The idea:** when a run would stack far fewer frames than were accepted (e.g.
  `solved << accepted` and `solved < auto_stack_min_frames·k`), fall back to registering the *unsolved* accepted subs
  to the solved reference (or to the best sub) by **star-pattern matching** — the classic astro fallback DSS/Siril use
  when there's no plate solution. **Non-trivial, be honest about it:** the Seestar is alt-az, so field *rotation*
  accumulates over a night — a translation-only phase-correlation (what `align.py` already uses for subpixel refine)
  is **not** enough; this needs a **similarity transform** (translation + rotation + modest scale) from matched star
  triangles. Options: an in-house triangle-hash matcher over the QC star centroids we *already* detect (no new dep,
  more work), **or** the small pure-Python `astroalign` package (fast to build, but a **new dependency → per §9/§10
  record the sign-off** before adding). **Shape / guardrails:** additive and **opt-in / automatic-only-as-a-fallback**
  (never replaces a good WCS solve; engages only when solved-frame count is pathologically low), memory-bounded like
  the existing path (register→reproject one frame at a time, no unbounded accumulation), and must degrade safely
  (a frame that fails star-matching is simply left out, exactly as an unsolved frame is today — never corrupt).
  Surface it honestly on the result ("N of M frames stacked by star-matching — plate-solving couldn't locate them").
  **Tests:** synthetic faint few-star subs with a known rotation+shift, most WCS-unsolvable → the fallback recovers
  ≥K frames and output noise falls ~√N (vs single-frame today); a normal solved night is untouched (fallback never
  engages). **Why it's an *idea* not a fix:** it's a new registration path on the hot path + a possible dependency, so
  it needs a careful Builder slice (and the astroalign-vs-in-house/dependency call belongs to the owner). But it is the
  single most direct cure for the owner's real "gibberish on faint targets" report — worth prioritising once the
  cheaper solve-side mitigations are exhausted.
  **▶ VALIDATED IN PART (Audit 2026-07-24, real ASTAP CLI + d05):** the companion stack-then-solve bootstrap
  measured out — a plain mean of 8–16 subs at a faintness where a single sub detects 0–2 stars detects 6–12 (solvable),
  robust to ±2 px uncompensated drift, so the "solve the deep image, propagate WCS by registration" plan is sound and
  integer-shift-level registration is enough for a short tracked burst. See the ⭐⭐ thin-stack entry's ▶ block for
  numbers.
  **▶ PARTIALLY DELIVERED by the stack-then-solve bootstrap (v0.210.0).** The shipped bootstrap
  (`seestack/solve/bootstrap.py`) already recovers the common tracked-burst case with **translation-only** integer
  registration (phase correlation) — enough for the short sharpest-N window it integrates, per the ±2 px jitter
  measurement. This idea (a full **similarity** transform tolerant of accumulated alt-az **field rotation** across a
  whole night, and/or registering *every* unsolved sub rather than just bootstrapping the deep image) remains the
  more general L attack for long sessions where rotation between the first and last sub exceeds what a translation can
  absorb. Still gated on the astroalign-vs-in-house dependency call (owner sign-off). Reassess after the bootstrap has
  been validated on real faint-field data — the bootstrap may cover enough of the owner's cases that the full-rotation
  path isn't needed.

- ~~**IMPROVEMENT IDEA (Builder 2026-07-25) — let the bootstrap anchor on an already-solved sub when a few
  (but < min_frames) subs did solve, instead of always re-solving the deep image.**~~ — **✅ SHIPPED v0.412.0**
  (`solve/bootstrap.pick_solved_anchor` + `BootstrapResult.anchored_on_solved_sub`). Entry in
  [`SHIPPED.md`](SHIPPED.md).
- **IMPROVEMENT IDEA / SCOUT TASK (Builder 2026-07-25) — validate the stack-then-solve bootstrap on real
  faint-field data, then consider promoting `astap_bootstrap_solve` to on-by-default.** *(Autonomy — PRIORITY 2;
  size S for the Scout.)* The v0.210.0 bootstrap ships **off by default** because its gain was measured on
  *synthetic* subs; the propagation math is ground-truth-tested but the end-to-end "does it actually rescue the
  owner's real faint targets" gain needs confirming on real Seestar data (the audit harness in the plate-solve
  audit's scratchpad — `detect_exp.py`/`bootstrap_exp.py` — plus a real faint-field sub set). If it reliably lifts
  real un-located fields into a clean stack with no mis-placement, promoting it to on-by-default would make the
  owner's #1 pain "just work" without a settings trip. Until then it stays opt-in per §9.
- **▶ PARTIAL — refusal message half SHIPPED v0.184.13** (Builder 2026-07-24, branch `claude/pensive-faraday-xok0ew`;
  regression-tested). The `_guard_stack_memory` `MemoryError` (surfaced verbatim on the failed stack job) now names the
  **single least-destructive concrete lever** that brings the run within budget, with the memory it lands at — instead
  of the generic four-lever dump. New pure `_best_memory_fix(dst_shape, ref_shape, …)` (`seestack/stack/stacker.py`)
  reuses `_estimate_peak_bytes` (so the named "~X GB" can never disagree with the refusal threshold) and mirrors the
  levers `estimate_stack` already surfaces pre-submit: drizzle on → "lower the drizzle scale to ×N"
  (`_largest_drizzle_scale_within_budget`); non-drizzle, least-destructive first → "lower Extra outlier passes to 1"
  (k>1 min/max) then "switch Canvas mode to 'reference'" (mosaic union whose ref frame fits). When no single lever
  obviously fits, it keeps the generic guidance. `run_stack` now threads `ref_shape`/`is_mosaic_canvas`/effective
  `min_max_reject_count` into the guard. Engine-only, additive (new optional guard kwargs default to the old behaviour),
  **no change to *what* is refused** (same threshold) — upgrade-safe, no config/DB/API-shape/default change. Tests:
  `tests/test_stack_memory_guard.py` (+4 — drizzle-scale/reference-canvas/drop-extra-passes each named with its GB;
  generic fallback when nothing single fits). **Remaining (smaller follow-up): the pre-submit UI half** — add the
  ranked fitting options + their resulting peak to `StackEstimate` (it already computes `suggested_drizzle_scale`/
  `suggested_reference_canvas`) and render them as one-click actions on the Stack form, so the fix is offered *before*
  the run is even submitted, not only on the refusal. *(Original idea kept below for provenance.)*
- **IMPROVEMENT IDEA (Scout 2026-07-23, targets the ⭐⭐ top bug's root cause) — auto-retry a failed plate-solve with
  progressively relaxed ASTAP parameters on faint/sparse fields before giving up, so more subs get located and the
  auto-stack combines more frames instead of shipping a thin/gibberish result.** *(Autonomy + image-quality pillar,
  PRIORITY 2/4; size M; additive — no new deps, ASTAP is already bundled.)* **Why:** the top open bug is that faint,
  few-star fields yield single-frame speckle because most subs *fail plate-solve* and are silently dropped from the
  stack. v0.180.0 already borrows a solved sibling's centre as a hint; a complementary lever is that ASTAP itself
  often solves a faint field on a **second pass with a wider search radius, a lower star-detection threshold, or a
  larger max-star count / longer timeout** — the defaults are tuned for a typical field and are too strict for a
  sparse one. **Shape:** in `seestack/solve/runner.py`, when a solve fails with a "no match / too few stars" class of
  error (not a "no star database" setup error — that needs the banner, not a retry), retry once or twice with a
  relaxed parameter set (widen radius, lower the star threshold, raise the timeout modestly) before recording
  `solve_failed`. Keep it bounded (retry budget + a hard timeout cap) so it can't blow up ingest latency on a
  genuinely un-solvable frame, and log the relaxed-solve success rate so the effect is measurable. **Sane default:**
  the relaxed retry is automatic and invisible when the first pass already succeeds (the common case), so no behaviour
  change on bright fields; it only adds attempts where a frame would otherwise be dropped. **Validate** on a real
  sparse-star field (or synthetic few-star subs) that the relaxed pass recovers solves the strict pass misses without
  a flood of false/wrong solutions (guard on the solve's own residual/match quality). Tests: a `solve_failed`
  no-match path triggers the relaxed retry; a "no star database" path does **not** (still surfaces the setup banner);
  the retry budget is honoured. *(Feasibility: uses the already-bundled ASTAP, additive, bounded, testable — passes
  §4's filter. Ties directly to the highest-priority owner-reported issue.)*
  **▶ MEASURED (Audit 2026-07-24) — scope this DOWN before building:** most sensitivity levers this entry guesses at
  measured as **non-levers** on realistic faint Seestar frames (real ASTAP CLI + d05): `-check`, `-m 1`, `-speed slow`
  → zero detection change; a wider radius / longer timeout is irrelevant (a failed search costs ~4 s at the 30°
  default, 0.2 s at 5°); a deeper star database is unnecessary (d05 census: ≥124 catalog stars per Seestar FOV in the
  sparsest sky area, median ~490). What DOES move the needle: never escalate binning past 2 (the bin-4+`-s 200` rung
  detects ~0 of 25 stars even on bright frames), keep/boost the bin-1 rung (raise `-s`), and the stack-then-solve
  bootstrap (validated). Full numbers: the ⭐⭐ thin-stack entry's ▶ ROOT CAUSE MEASURED block.

- ~~**NEW (Builder 2026-07-23, slice (c) follow-on to the shipped sibling-hint fill-in v0.180.0) — a *second*
  solve pass that retries first-round failures with the sibling hint at the tight radius.**~~ — **✅ SHIPPED
  v0.411.0** (`solve/runner.build_sibling_retry_arglist` + `scanner.run_qc_and_solve`'s
  `retry_unsolved_with_sibling_hint`). Entry in [`SHIPPED.md`](SHIPPED.md).
- **NEW (Builder 2026-07-23, filed while fixing the ⭐ stale-cache bug) — decide whether a cleared/missing Stage-1
  cache should self-heal on the next scan.** *(Autonomy / friendliness; PRIORITY 2–3; size S; NEEDS a product call
  before building — that's why it's an idea, not a bug.)* The stale-cache fix (v0.174.2) makes every consumer fall
  back to `source_path` via `readable_frame_path`, so correctness is fully restored — a target with a cleared cache
  keeps working from source. But the cache is **never rebuilt**: `_cache_stale(cached_path, src)`
  (`seestack/io/ingest.py`) catches the `OSError` from stat-ing a *missing* cache file and returns `False` (not
  stale), and `ingest_files` only re-copies when `not prior.cached_path` (still truthy), so the frame runs off the
  (possibly slow NAS) source on every future scan. Rebuilding it on the next scan would restore the fast local path
  — but there's a **real tradeoff**: users often clear Stage-1 to *reclaim disk*, and auto-refilling it (Stage-1 is
  just a source copy) would silently undo that. **Options:** (a) treat a *missing* (not just size-mismatched) cache
  file as needing re-copy in `_cache_stale`/`ingest_files` — simplest, but re-fills after a deliberate clear; (b)
  have `clear_cache` null the `cached_path` column in the same transaction so the intent ("I cleared it") is
  explicit and only *then* does a scan re-copy — cleaner separation, but a small additive DB write on a path that
  currently touches no DB; (c) leave it as-is (source fallback only) and add a UI hint that clearing Stage-1 trades
  disk for slower reads. Pick one with the owner's disk-vs-speed preference in mind. Not blind-shipped because the
  "right" default is a product call. *(Found while routing the six read-sites through `readable_frame_path`.)*
- **NEW (Scout 2026-07-21b) — auto-detect a master-dark ↔ light *exposure* mismatch and guide the fix, so a
  beginner reusing a dark library doesn't silently get a wrong calibration.** `CalibrationMasters.validate`
  (`seestack/calibrate/apply.py`) only checks the master's *shape* against the frames — it never compares the
  dark's exposure to the lights'. A dark master carries dark-current that scales with integration time, so
  subtracting a 30 s dark from 10 s subs over-subtracts (crushed shadows / dark halos), and a 10 s dark from
  30 s subs under-subtracts (residual amp-glow / hot-pixel trails) — a *wrong image*, with no warning. The app
  already has the machinery to fix it: `scale_dark_to_light` + `_effective_dark` rescale the dark to the
  light's exposure **when a master bias is also present** (`dark = bias + (dark − bias)·t_light/t_dark`), but
  it's **off by default** and silent, so a beginner never discovers it. **Idea:** at stack setup (and in the
  auto-calibration bind path), when the chosen dark's `dark_exposure_s` and the reference light's `exposure_s`
  are both known and differ by more than a small tolerance (say >10%), surface one plain-language line — *"Your
  master dark is 30 s but these subs are 10 s. Mismatched darks can over- or under-correct. Best: shoot darks
  at 10 s. Or add a master bias and turn on 'scale dark to exposure' and the app will match them for you."* —
  and, when a bias **is** available, offer a one-click enable of `scale_dark_to_light` (or auto-enable it on
  the fully-unattended auto-stack path, since with a bias present the scaling is strictly more correct than a
  mismatched raw subtraction). **Beginner bar ✔:** plain language, actionable, a sane default (silent when
  exposures match — the common case, byte-for-byte unchanged), and it prevents a real data-integrity foot-gun
  a non-expert can't diagnose. **Grounded / upgrade-safe:** exposures are already loaded (`dark_exposure_s`,
  `info.exposure_s`); the warning is read-only; the auto-enable is gated on a bias being present (never
  double-subtracts) and only fires in `auto`/unattended mode so no stored default flips on a running install.
  Split for the Builder: (a) a pure `dark_exposure_mismatch(dark_s, light_s, *, tol=0.1) -> str | None` helper
  + tests; (b) surface it as a stack-setup / result advisory (reuse the existing advisory/notes surface); (c)
  optionally auto-enable `scale_dark_to_light` on the unattended path when a bias is bound. _(M, split as
  above; PRIORITY 2 autonomy / P4 image-quality — prevents a silently-wrong calibration; builds on the shipped
  `scale_dark_to_light` infra, so low-risk.)_
  _(Builder note 2026-07-21 — **slices (b) and (c) are already shipped; only (a) remains and is pure dedup —
  low value, do not build blindly.** While scoping this item I traced both surfaces and both already handle the
  mismatch: **(b) interactive stack setup** — `frontend/src/routes/Stack.tsx` already computes `darkExpMismatch`
  (>25% via `expMismatch`) and renders the plain-language warning *"This dark was shot at Xs but your subs are
  Ys — a mismatched dark leaves residual thermal signal or over-subtracts…"*, **plus a one-click "Scale this
  dark to your subs' exposure" button** that sets `scale_dark_to_light` (shown when a bias is selected), and a
  proactive nudge to add a bias when none is. **(c) unattended auto-bind** — `webapp/calibration.py::
  auto_bind_master_paths` already, when a dark's gain/temp confidently match but its *exposure* is off, binds
  `dark_path + bias_path + scale_dark_to_light=True` (the exposure-scaling recovery) if a confident bias exists,
  and otherwise **leaves the dark off** rather than risk an over/under-subtraction — i.e. the unattended path
  already never applies a mismatched raw dark. So the only unbuilt piece is **(a)** — extracting the duplicated
  threshold (frontend `expMismatch` 25% + backend `_AUTO_BIND_EXP_MISMATCH_FRAC` 0.25) into one shared pure
  `dark_exposure_mismatch()` helper. That's a **maintainability dedup**, not a new user capability, and the two
  copies don't currently disagree — so it doesn't clear the churn bar on its own. Left filed; a future run
  already touching these files could fold the helper in, but the beginner-facing value here is **already
  delivered**. Recommend closing this item as largely-shipped rather than treating it as ready feature work.)_
  **▶ CLOSED — slice (a) is shipped too; verified in the code, not assumed (Builder 2026-08-18,
  `claude/relaxed-franklin-i98kvb`). Do not re-pick this.** The "pure helper" the note above left open exists and
  goes further than the spec: `CalibrationMasters.calibration_warnings(light_exposure_s, light_temp_c)`
  (`seestack/calibrate/apply.py`) returns the plain-language sentences for an exposure mismatch **and** a
  temperature mismatch, plus a separate one for the case where exposure-scaling was asked for but a wrong-shaped
  bias silenced it. It is carried on `StackResult.calibration_warnings` (`stacker.py:1196`), stamped per run, and
  rendered on the **Jobs** card (`calibrationMismatchNote`), **History**, the **Stack** form and the **Editor**.
  Nothing in this item is open.
- **NEW IMPROVEMENT (Scout 2026-07-21) — when auto-reject resolves to min/max, also auto-scale the *number*
  of extremes it drops (`min_max_reject_count` k) to the frame count, so a long multi-night session with
  several trails crossing the same pixel is actually cleaned.** v0.143.0's `auto_reject` picks the *method*
  (min/max below the κ-effective frame count, κ-σ at/above it) but always leaves `min_max_reject_count=1` —
  the classic single min/max drop. That's correct for a *lone* trail, but the §1 owner routinely stacks
  **thousands of subs across many nights**, where 2–3 satellite/plane trails can cross the *same* output
  pixel over a session; a k=1 drop removes only the single brightest and leaves the rest as a residual
  streak. The engine already fully supports k>1 — `MinMaxRejectAccumulator(reject_count=k)` keeps k sorted
  min/max planes and degrades gracefully (`count≥2k+1` full k-trim → single drop → plain mean; verified
  clean in this run's audit) and the peak-memory guard already charges `2+2k` planes
  (`_min_max_reject_arrays`). **Idea:** inside `_resolve_auto_reject`, when it selects min/max, also set k
  from n on a gentle, conservative curve — e.g. `k=1` up to a few hundred frames, `k=2` into the low
  thousands, capped small (≤3) so a modest stack never over-trims (dropping 2k of n samples must stay a
  small fraction; keep k ≤ ~n/8). Purely a refinement of the already-opt-in `auto_reject` path — **off by
  default**, no effect unless the user turned auto-reject on and it resolved to min/max, so no default flip
  and byte-for-byte unchanged for everyone else. **Well-grounded / low-risk:** one small change to the
  existing `_resolve_auto_reject` (which already returns a `replace(options, …)` copy), the accumulator +
  memory guard already handle any k, and the resolved k is persisted in the run record like the method is.
  **Guardrails:** the k-vs-n curve must be conservative (never trim a meaningful fraction of a small stack —
  cap k so `2k ≤ n/4`); validate on a real long session that a genuine multi-trail pixel is cleaned while a
  clean stack is unchanged. Tests: extend `tests/test_stack_pipeline.py` — `_resolve_auto_reject` returns
  k=1 for small n and a capped k>1 for large n; a synthetic stack with two planted trails at one pixel and
  a high frame count clips both under the auto-scaled k (fail-before with k=1 one residual survives).
  _(S code / S–M validation; PRIORITY 2 autonomy + P4 image quality — extends the shipped auto_reject so the
  "just works" method-pick also gets the *strength* right for the owner's high-frame-count workflow.)_
  _(Builder note 2026-07-21 — **premise is self-defeating; do NOT build as specified.** `auto_reject` resolves
  to min/max only **below** `_auto_kappa_min_frames(κ)` — n<11 at the default κ=3 (`stacker.py::_resolve_auto_reject`);
  a "thousands of subs across many nights" session is n≫11, so it resolves to **κ-σ**, not min/max, and never
  reaches the k it wants to scale. Within the min/max regime (n<11) the idea's own conservative cap (`2k ≤ n/4`,
  i.e. `k ≤ n/8`) forces `k=1` for every n<11 (n/8 < 1.375), so the auto-scale curve would be a **no-op** exactly
  where it fires. To actually clean multi-trail pixels on a huge stack you'd need k>1 under **κ-σ** (a different
  change — κ-σ ignores min_max_reject_count entirely), or to raise the min/max→κ-σ crossover, both of which change
  the shipped v0.143.0 behaviour and need real-data justification. Left filed as a caution, not ready work.)_
- **Pre-flight "this batch looks like two targets" guard — catch mixed pointings *before* the
  walk-away stack wastes itself.** (S–M, autonomy/friendliness/trust) *(Scout-filed 2026-07-09, traced.)*
  **Interactive slice SHIPPED v0.101.0 (Target page) + v0.102.0 (Stack form):** the pre-flight detection +
  amber warning on both surfaces a user reaches before stacking. A new pure `detectMixedPointings(frames)`
  helper (`components/target/mixedPointings.ts`, mirroring `countQcUncheckable`/`countNewSubsSinceStack`)
  single-linkage-clusters the accepted+solved subs' RA/Dec at a 3° link distance (wrap/pole-safe via unit
  vectors; a contiguous mosaic stays one cluster, two well-separated targets split), and both the Target page
  (v0.101.0) and the Stack form itself (v0.102.0, right next to the Stack button) show an orange "This batch
  looks like N different targets" callout — with the majority/minority counts + their separation + guidance
  to reject the odd frames — *before* the user clicks Process/Stack. Frontend-only, read-only, additive (no
  backend/schema/default change). **Unattended slice SHIPPED v0.109.16** (Builder 2026-07-11; see Shipped): a new
  off-by-default `mixed_pointing_guard` setting makes the Process-target and watcher auto-stack chains cluster
  the pointings (Python mirror `seestack/stack/pointings.py::detect_mixed_pointings`) and **refuse-with-guidance**
  — skip the walk-away stack with a plain-language reason — on a clearly-bimodal batch, instead of burning the run
  combining one pointing. Chose refuse-with-guidance over auto-stacking just the majority to avoid touching the
  engine hot path (`run_stack` reads frames straight from the DB); the "auto-stack just the majority pointing"
  variant would need an engine frame-filter param and is left as a possible future refinement if refuse-only
  proves too blunt on real data. Off by default (§9). Original write-up kept below for provenance.
  _(~~Builder follow-up idea, spotted auditing the shipped v0.101–0.102 detection 2026-07-09: the warning
  currently only **tells** the user to "open the Frames table and reject the odd frames"…~~ —
  **shipped v0.103.0** (see Shipped). `detectMixedPointings` now also returns `minorityIds` — the ids of
  every accepted+solved sub outside the largest pointing (exactly what the stacker would silently drop) —
  and both surfaces that show the amber warning (Target page + Stack form) now carry a one-click **"Reject
  the N odd-target frames"** button that rejects just those subs via the existing `bulk` reject endpoint
  (`action:"reject"`, `reason:"user"`), leaving a clean single-target batch. Undoable like the auto-grade
  "Drop N" hint (the warning swaps to a teal "Rejected N — Undo — re-accept" confirmation), so a stray good
  frame is one click back; any lone strays outside the majority are rejected too (they'd be dropped anyway).
  Frontend-only, additive, no backend/schema/default change; the pure helper + button are unit-tested.)_
  The still-open *preventive* complement to the now-**shipped** post-hoc pair (v0.100.0: "Persist & surface
  honest per-run frame accounting" + "Proactively diagnose a large align-failure fraction", both in Shipped).
  Root cause (verified): in `stacker.py::_pass` a frame whose reprojected footprint doesn't intersect the
  reference canvas returns `None` from `align_one` and is dropped — v0.100.0 now *counts* those (NALIGNFL)
  and the History Info panel flags a large align-failure fraction after the fact, which closes the
  *visibility* gap. **What's still open is prevention:** for the "drop two targets in one batch" mistake, the
  unattended auto-stack still picks one pointing as reference and burns the whole walk-away run producing a
  half-complete stack the user only learns about *afterwards* from the amber count. Close the loop by acting
  **pre-stack**: in the Process / auto-stack chain, cluster the frames' already-stored
  `ra_center_deg`/`dec_center_deg`; if they split into two+ well-separated pointings that aren't a contiguous
  mosaic (gap ≫ the ~1° Seestar FoV between clusters), auto-stack just the majority pointing (flagging the
  rest) or refuse-with-guidance — instead of silently combining half the data. Purely local (RA/Dec are in
  the project DB), additive, off-nothing (only fires on a clearly-bimodal set), and testable on a synthetic
  two-pointing frame set. Distinct from the shipped diagnosis because it acts *before* the stack (no wasted
  run) and keys on the sky coordinates we already have, not on the post-hoc align-failure count. **Smallest
  safe first slice:** just the detection + an amber "your batch looks like 2 targets" pre-stack warning,
  leaving the actual split/auto-select for a follow-up.
- **NEW IDEA (Builder 2026-09-04, the generalisation of the v0.345.8 merge) — sweep the app for the other
  pairs of superlatives that can resolve to the same thing.** *(Pillar: friendliness / trust — PRIORITY 3;
  size XS per site once found; confidence: two instances fixed, the rest unchecked.)* v0.345.8 merged two
  such pairs — "biggest project" vs "most-imaged target", and "longest night" vs "sharpest night" — after a
  dogfood pass showed each printing one answer twice, side by side. **The identifying test:** two adjacent
  surfaces that each *rank* the same population by a different key, where the keys are correlated on this
  owner's data (fixed-length Seestar subs make exposure ≈ count; a short season's best night tends to be
  best at everything). **Unchecked candidates:** the Dashboard's "Your best night" card against the year
  page's sharpest night (different pages, so much weaker — probably leave it); `/best`'s ranking against the
  Library tile's "latest picture"; the Target page's "sharpest sub" against its "reference sub"; and the
  session-recap standouts. **Care:** the fix is a *merge that keeps both figures*, never a drop — and a pair
  that usually differs should stay two cards, because merging a coincidence would be as confusing as
  repeating one.

- **NEW IDEA (Builder 2026-09-04, the generalisation of the v0.345.3 export-panel fix) — sweep the app for
  the other trailing "what these buttons do" paragraphs, and check each against the per-control copy above
  it.** *(Pillar: friendliness — PRIORITY 3; size XS per site once found. Confidence: one confirmed instance,
  the rest unenumerated.)* The editor's Export panel ended with a four-sentence block recapping the three
  buttons four rows above it, of which the first sentence duplicated the line directly under the Export
  button. It survived every code-level read because each sentence is defensible alone — only the **rendered
  page** shows five grey paragraphs in a row, which is why `scripts/agent-dogfood.sh` found it and audits had
  not.
  **The identifying test, which is cheap and does not need a browser once you know the shape:** a
  `<Text size="xs" c="dimmed">` that is the *last* child of a panel and names two or more of the panel's own
  controls in quotes. **Named starting points, none checked:** the Stack form's foot, the Save/share menu's
  description block, the Calibration page's master-picker explainers, and the Storage page's cleanup copy.
  **Care — this is the owner's "nothing may be removed" constraint, so do it the way v0.345.3 did:** go
  clause by clause, move each sentence under the control it describes (the idiom several panels already use),
  and re-home any fact the paragraph carried that the per-control copy did not, rather than deleting the
  block wholesale. A paragraph whose every clause is genuinely new information is *not* a hit — leave it.

  **⚪ ALL FOUR NAMED STARTING POINTS ARE CLEAN — checked in the code, recorded so nobody re-walks them
  (Builder 2026-09-04).** The **Stack form's foot** ends in the sizing line and its conditional advisories,
  each of which sits with the control it is about and carries a number nothing else states. The
  **Save/share menu** (`Target.tsx` / `History.tsx`) has no trailing block at all — every item carries its
  own one-line `MENU_HINT` under its own label, which is the idiom the export-panel fix moved *towards*. The
  **Calibration page's** picker explainer is one sentence about the *source-folder input* beside it ("point
  at a server-side folder of raw dark/flat FITS…"), not a recap of the buttons. The **Storage page's** two
  closing paragraphs both carry facts stated nowhere else — what a cache is and that pruning is permanent,
  and the standing guarantee that nothing on the page touches `incoming/` (§10), which is the one paragraph
  on that screen that must never be trimmed for tidiness. **So the confirmed instance count stands at one
  (v0.345.3), and the remaining candidates are unenumerated rather than known.** If the sweep is ever
  reopened, look at panels *added since* v0.345.3 rather than re-reading these four.

- **NEW IDEA (Builder 2026-09-03, measured while sweeping the display-space statistics for A1's blindness) —
  Levels' "From your image" button silently leaves the black point at 0, and nothing says why.** *(Pillar:
  friendliness — PRIORITY 3; size XS; **copy, not arithmetic** — do NOT change the number, and read the
  swept-and-closed entry under "Image quality" before touching this.)* Measured on real `autostretch`
  output: the image entering Levels has **1.08 % of its pixels at exactly 0** (the STF's shadow clip), so
  `suggest_levels_points`' 1st percentile lands inside that spike and the button returns
  `black = 0.000, white = 0.892, gamma = 1.079`. That black **is the honest answer** — the function's job is
  "put black where 1 % of pixels fall below", and 1.08 % are already there, so the picture has the shadow
  clipping the button was asked for; excluding the zeros would clip roughly *twice* the intended share on the
  on-by-default path. But from the beginner's seat it reads as a half-broken button: two sliders move, one
  doesn't, and nothing accounts for it. **Shape:** one line beside the suggestion — *"your blacks are already
  where they should be, so only the white point moved"* — on the branch where the suggested black equals the
  current one. Not a banner; the other "From your image" buttons already name what they solved for
  (`gamma_target`, `target_bg`), so this is the same idiom rather than a new element. **Grep first:** the
  Levels control's existing suggestion copy in the editor, and check whether the button already renders
  anything on a no-change suggestion.

  **⚪ CLOSED AS MOSTLY-ALREADY-BUILT — CHECKED, NOT ASSUMED (Builder 2026-09-03, the same day it was filed).
  Do not build this as written.** The entry's own "grep first" was the whole answer: `OpParamPanel` already
  handles the no-change suggestion **generically**, for every op, not just Levels. When a param already sits
  at its suggested value (`matchesSuggestion`, which honours the field's own `step`) the button is
  **disabled**, is prefixed with a **✓**, and carries the tooltip *"Already set to the value measured from
  your data"*. So the premise — *"two sliders move, one doesn't, and nothing accounts for it"* — does not
  hold on the shipped UI: the black button never invited the click, and it already says why.
  **The measurement in the entry is still worth keeping** (1.08 % of an `autostretch` output's pixels sit at
  exactly 0, so the 1st percentile lands inside the STF's shadow clip and `black = 0` is the honest answer),
  and so is its warning that excluding those zeros would clip roughly *twice* the intended share on the
  on-by-default path — that half stands as a "do not fix the number" note. What is left is only the gap
  between the generic *"already set from your data"* and a Levels-specific *"because your blacks are already
  clipped there"*: one extra clause in a tooltip on a **disabled** button. That is below the bar, and adding
  it would be the already-shipped-item-re-filed churn AGENTS.md §1 warns about. **If a future run wants the
  specific wording anyway**, it is a conditional tooltip string on `OpParamPanel`'s existing `atSuggestion`
  branch — not a new element, and not a new branch.

- **NEW IDEA (Builder 2026-09-02, the other direction of the v0.326.8 "Edited from …" line) — the *original*
  stack says nothing about the edit made from it, so the pointer only works if you happen to look at the right
  row.** *(Pillar: understand — PRIORITY 3; size XS; **check the overlap with `unexported_edit` first, it may
  already be enough**.)* An export's card now names the run it came from and jumps to it. The source run's own
  card says nothing back — no "an edited version of this exists" — so a beginner scrolling History still meets
  the linear stack first and has no reason to think there is a finished picture two cards along. **The datum is
  already there:** `derived_from` is on every export's `options`, so the reverse index is one pass over the
  same list the page already holds (`derivedFromNote`'s neighbour, not a new query). **Why it is filed rather
  than built:** the source card is already the busiest one in the app (badges, two dates, notes, the noise
  delta), and `unexported_edit` already occupies exactly this slot for the *unfinished* case — so the honest
  question is whether a second edit-related label earns its place, or whether the right shape is to extend the
  existing badge's vocabulary rather than add a line. Decide that before writing code; if in doubt, leave it —
  one direction of a link is often enough.

> **⚠️ COLLISION — this was built twice in the same hour, and the version below (v0.323.0, branch
> `claude/zen-mccarthy-2rptmf`) is the one that ships.** *(Builder 2026-09-02, branch
> `claude/zen-mccarthy-v56oj1` — mine is dropped rather than re-litigated; theirs landed on `main` first.)*
> The two were indistinguishable in shape — same `hasAnythingToShow` name, same definition *against*
> `buildSlides`, same `["gallery"]` key shared with the show — which is itself evidence the entry's spec was
> unambiguous. **Theirs is strictly better on the one point the entry left open**, and it is worth carrying
> forward as the general rule: a **failed** query is *unknown*, not *empty*, so their gate keeps the button
> when the gallery errors. Mine treated a rejected query as "nothing to show" and would have hidden a working
> slideshow from anyone briefly offline — the exact failure mode the entry's own trap warns about, arrived at
> from the other direction. Nothing of mine is re-applied on top: their tests are a superset of mine (8 to my
> 6, including that error case).
> **What it cost, and the lesson:** I claimed nothing in the backlog before starting — the item was an XS
> dogfood finding and claiming felt like overhead. It is not: the claim is the only signal the other Builder
> could have seen, and this is now the **tenth** such collision. Claim even the XS ones, in the run's first
> commit, and push it immediately.

- **NEW IDEA (Builder 2026-09-01, the half the v0.322.5 label fix deliberately did not build) — tick the
  first-image solve step on frames that **actually got solved**, not only on ASTAP being installed.**
  *(Pillar: friendliness — PRIORITY 3; size S, but **read the cost note**; the label fix already removed the
  untruth, so this is polish, not a correction.)* The honest signal for *"your subs have sky coordinates"* is a
  count of frames with a WCS, and today nothing carries one: `library.campaign_stats` aggregates only the
  registry columns (`n_frames`, `n_frames_accepted`, `total_exposure_s`), and `wcs_json` lives in each
  **per-target** `project.sqlite`. **The cost is the reason this is filed rather than built:** `/api/stats` is
  the Dashboard's hot path, and its existing per-project work (`_rollup_stacks`) opens only targets that *have*
  stacks — a solved count would open **every** target, on every uncached stats call. **If it is built:** put
  the count behind the same `stats_cache` signature, and add it as an additive optional field that reads as
  "unknown" (never as zero) when an older backend omits it — the step must not un-tick itself on an upgrade.
  **Care:** don't let it *replace* the ASTAP check. Someone with pre-solved frames and no ASTAP still needs the
  setup before their own subs will solve, so the tick wants to stay the setup's, with the frame count as an
  extra reassurance line at most.

- **🟡 HALF (a) IS ALREADY BUILT — don't re-pick it (Builder 2026-09-02, checked in the code while sizing it).**
  The **"Save this map"** button exists on `routes/Sky.tsx` (top-right of the My-map panel, `href={api.myMapUrl()}`
  with a dated `download={myMapFilename()}` → `astrostack-my-map-YYYY-MM-DD.png`), exactly as this entry
  specifies, with its own exported filename helper and tests. **Only half (b) — the Dashboard preview card — is
  open**, and it is the half whose own Care note collides with the standing IA priority ("don't append one more
  always-on card"), so it needs a *grouping* to live inside rather than a slot at the top. Sized and left.

  *(Original spec follows.)* **NEW IDEA (Builder 2026-08-29, spotted finishing the v0.292.0 "My map") — let the
  owner *save* their
  universe map, and put it where they'd think to look for it.** *(Pillar: enjoy + share — PRIORITY 3.
  Size: S. Confidence: high — the picture already exists at a stable URL.)* "My map" is a pride object:
  the one image that says "here's everywhere I've pointed my scope this year". Right now it only exists
  inside the Sky page. Two cheap additions: (a) a **"Save this map"** button beside the mode switch —
  the PNG is already served whole at `/api/sky/my-map.png`, so this is a download link with a nice
  filename (`astrostack_my_sky_<date>.png`), not new rendering; and (b) a small **preview card on the
  Dashboard** ("Where you've been · N pictures") that links into the Sky page's My-map mode, so a
  beginner meets it instead of having to find a third segmented-control option. Careful with (b): the
  standing IA item says the Dashboard is already busy — put it *inside* an existing grouping rather than
  appending one more always-on card, and only show it once there are, say, three or more mapped pictures
  (below that the map is mostly empty sky and reads as a bug rather than a milestone).

- **NEW IDEA (Builder 2026-08-27, spotted while fixing the two "dataclass tolerates, Pydantic doesn't" list
  endpoints in v0.277.5) — a tiny test that pins the *rule* rather than the four instances: every list endpoint
  that reads a per-item file off disk degrades per item.** *(Pillar: trust / maintainability — PRIORITY 3.
  Size: S.)* v0.277.5 fixed the four boundaries that existed; nothing stops the fifth being written without a
  guard. The cheap version is not a clever meta-test but a documented convention plus one shared helper —
  e.g. a `degrade_per_item(items, build, what)` used by `/api/videos`, `/api/gallery` and the `stats.py`
  roll-ups alike, so the guard comes for free with the helper and a reviewer can see at a glance which loops
  have it. **Grep first:** the four fixed sites and the existing `stats.py` roll-ups are the population; if a
  shared helper would only ever have five callers, a comment in the house-style notes may be the better
  answer, and this idea should be closed rather than built. Explicitly *not* worth a framework.

- **NEW IDEA (Builder 2026-08-18, the pattern behind both v0.266.1 and the hints added in v0.267.0) — a Tooltip is
  invisible on the device the owner actually reads this app on, so every explanation that exists *only* as a
  tooltip is, on a phone, not written at all.** *(Friendliness — PRIORITY 3; size M; **measure first**.)* A phone
  has no hover: Mantine's `Tooltip` opens on hover or focus, and a tap on a button runs the button. v0.266.1 fixed
  the extreme case (the label itself was hidden behind a tooltip); v0.267.0's menu items each show their old
  tooltip sentence as a visible one-line hint, which is the same fix applied to a different surface — and both
  times the wording already existed and was simply unreachable. **Slice:** count the `<Tooltip label="…">` uses
  across the beginner-critical routes (Target, History, Stack, Editor, Dashboard) and split them into (a) the
  tooltip *is* the only explanation — promote it to visible text or a hint line; (b) it repeats what the control
  already says — leave it. **Care:** don't turn every tooltip into visible prose, or the pages get *taller*, which
  is the complaint this whole IA effort exists to fix; prefer the v0.267.0 shape, where the words become visible
  because the control moved somewhere that has room for them. Worth doing as a measured pass, not a sweep.
  **▶ FIRST SLICE SHIPPED — v0.270.0** (Builder 2026-08-19, branch `claude/relaxed-franklin-m1crsw`), taken as the
  entry asks: one surface, measured, not a sweep. **The frames table's column headings** were the clearest case in
  the app — `FWHM`, `Ecc.`, `Sky` and `Transp.` are four of the table's five numeric columns, each already carrying
  a good plain-language sentence, and each carrying it **only** as a `Tooltip`. A phone has no hover, and a tap on
  one of those headings *sorts the table*, so on the device the owner reads this app on there was no way at all to
  find out what they mean — on the page a beginner spends the most time on.
  **The shape is v0.267.0's, not a sweep's:** the tooltips are untouched for anyone with a mouse, and a
  `FrameColumnGuide` disclosure — *"What do these numbers mean? →"* — spells the same sentences out as text.
  **Same words, one array:** the columns moved out of `Target.tsx` into `components/target/frameColumns.ts`
  (`FRAME_COLUMNS`), which now feeds both the header tooltips and the guide, so the two cannot drift and a column
  added later gets an entry in both surfaces or in neither — pinned by a test that walks `FRAME_COLUMNS` rather
  than a hand-written list.
  **Measured, as the entry's "don't make the pages taller" caution demands:** the Target page at 420 px goes
  **2 939 px → 2 953 px (+14 px, +0.5 %)** closed, and **1 966 px → 1 966 px on desktop — no cost at all** (the
  guide sits in the left column beside a taller right one). Opening it adds 269 px, and only when asked. The body
  is mounted **only while open** (it is static text with nothing to refetch), which also keeps words like
  "trailed" off a page that is careful about when it says them — an existing `Target.test.tsx` assertion caught
  exactly that and passes unchanged.
  **Tests (+6):** `FrameColumnGuide.test.tsx` (**new, +5** — nothing on the page until asked for, every hinted
  column explained in one tap driven off `FRAME_COLUMNS` itself, the wording being the tooltips' own, open/close
  with its `aria-expanded`, and the toggle hugging its text rather than stretching) and `Target.test.tsx` (+1 —
  the real page's hints are readable without hover). The existing "gives the metric column headers plain-language
  hint tooltips" test passes unchanged, so the hover path was added to, not traded away.
  **▶ SECOND SLICE SHIPPED — v0.374.11**, and it turned out to be a **bug**, not only an unreachable
  explanation (Builder 2026-09-07, branch `claude/sweet-babbage-mg8isx`). Rather than pick one of the four
  remaining routes, the measurement pointed at the one component all of them share: `HintLabel`
  (`components/StackOptionControl.tsx`) is the *only* explanation surface for a descriptor-driven option, and
  it is used by the **Stack form**, **Settings**, the **editor's op parameter panel** (via `OpParamPanel`) and
  the editor's print-size control — i.e. every engine parameter the app offers, on the priority-1 surface
  included. Its `field.help` sentence lived on a hover `Tooltip` around a bare 14 px `<svg>`.
  **The bug, verified by probe before the fix:** `HintLabel` is passed as a `Switch`/`Select`/`NumberInput`'s
  `label`, which Mantine renders **inside a `<label>`** — so clicking the info icon activated the control.
  Driving the pre-change component directly, one click on the icon of a boolean option fired
  `onChange(true)`. On a phone that click is the *only* gesture available for "what does this do?", so the one
  way a beginner could ask changed their stacking option instead, and the answer never appeared.
  **Fix:** the icon is now a real control — `UnstyledButton component="span" role="button" tabIndex={0}` with
  a controlled tooltip opened by tap, hover *or* keyboard focus, and `preventDefault()` on the click so the
  surrounding `<label>` no longer forwards it. **A `<span>` and not a `<button>` is load-bearing:** a
  `<button>` inside that `<label>` is a *labelable* element, so the field's own label would name two controls
  at once — which broke seven `Settings.test.tsx` queries the moment it was tried, and would read the same way
  to a screen reader. Its `aria-label` is deliberately generic (*"What does this do?"*) for the same reason;
  the field's own label is announced immediately before it.
  **No page gets taller** — same 14 px icon, `lineHeight: 0`, no padding, no new visible prose — which is what
  the entry's own caution asks for, and hover is byte-for-byte what it was for anyone with a mouse. Keyboard
  users gain the hint for the first time. **Tests (+7, four fail-before):** `StackOptionControl.test.tsx` —
  the tap shows the hint *and* leaves the setting alone, tap-again dismisses, blur dismisses (there is no
  outside-click handler; losing focus is the dismissal, which is what a touch elsewhere does), hover and focus
  both open it, Enter and Space open it, a field with no help renders nothing at all, and the switch still
  toggles when you actually click the switch.

  **▶ THIRD SLICE SHIPPED — v0.402.0, the editor's preview toolbar** (Builder 2026-09-09, branch
  `claude/sweet-babbage-x2ai9f`). The route with by far the most hand-written tooltips is the editor (24, against
  Gallery's 9 and Target's 7), and the ones that matter are the eight-button row **directly under the picture** —
  the row that decides what the preview is showing. Four of them carried a good sentence each and carried it only
  as a `Tooltip`: `Coverage`, `Star mask`, `Drag to crop` and `Split`. A phone has no hover and a tap on one of
  those buttons *runs* it, so the one gesture available spends the question on the answer — and the answers are
  not guessable from what appears (a yellow-to-dark-blue heatmap, a white-on-black mask, a divider you are
  supposed to drag). Three more (`Compare`, `Refresh`, `Zoom`) had no explanation anywhere, of which `Compare` is
  the one that needed it: it is the twin of `Split` and its label never says what it compares *against*.
  **The shape is v0.270.0's `FrameColumnGuide`, deliberately** — a `PreviewToolGuide` disclosure
  (*"What do these buttons do? →"*) under the row, built from the same `PREVIEW_TOOLS` array the tooltips now take
  their labels from, so the two cannot drift and a tool added later gets an entry in both surfaces or in neither.
  `visiblePreviewTools({isMosaic, cropDrag})` takes the same two booleans the row itself renders from, so the guide
  can never explain a button that is not on the screen — the mosaic-only coverage heatmap and the crop handles are
  absent on an ordinary single-field stack, where naming them would send a beginner hunting for controls that do
  not exist. **Measured, as the entry's "don't make the pages taller" caution demands** (`agent-dogfood.sh
  --build --mosaic --editor`): the editor at 420 px goes **3,047 px → 3,072 px (+25 px, +0.8 %)** closed, desktop
  1,984 px; nothing overflowing, no console errors, and the mosaic trim still 7.9 %. The body is mounted only
  while open. Tooltips are byte-for-byte what they were for anyone with a mouse; nothing was removed.
  **Tests (+12):** `previewTools.test.ts` (+5 — the two conditional tools appear only under their own condition,
  the row order, every entry carrying a real sentence, and each entry keyed by its own name) and
  `PreviewToolGuide.test.tsx` (+5 — one line until asked for, every offered tool explained in one tap driven off
  the array itself, never explaining an absent button, open/close with its `aria-expanded`, and nothing at all for
  an empty row), plus 2 in `Editor.test.tsx` on the real page (the split hint readable without hover; the
  mosaic-only coverage hint absent on a single field) — both fail before.

  **▶ FOURTH SLICE SHIPPED — v0.402.1, and it is a *bug* rather than an unreachable explanation, exactly as the
  second slice was** (Builder 2026-09-09, same branch). v0.374.11 fixed the case where the hint icon sat inside a
  control's `<label>` and the tap activated the control. **The same defect exists one level up, wherever a
  `<Tooltip>` is wrapped around the control itself** — there the tap does not merely leak to the control, it *is*
  the control, and no icon exists to aim at. Enumerated rather than guessed at: exactly **five** sites in the
  whole frontend wrap a `Tooltip` around a `Switch`/`SegmentedControl`/input, and all five are now fixed —
  - the **editor's `Auto-crop edges` switch**, whose sentence is the only place the app says the library-wide
    default lives in Settings → Automation, and whose tap overrides that default for the picture in front of you;
  - the **Jobs page's `Notify me when done` switch**, where the tap also fires the browser's permission prompt —
    so reading what the control does was the same gesture as agreeing to it;
  - the **Gallery's three filters** (calibration, combine method, and the sort whose hint is the only place that
    page explains its σ) — on a segmented control the tap picks a segment, so asking the question re-sorted the
    page and never answered it.
  **The fix is the app's own affordance, not a new one.** `HintIcon` is the icon half of `HintLabel`, lifted into
  `components/HintIcon.tsx` (`HintLabel` now renders it, byte-for-byte the same behaviour — its own tests are
  untouched and pass). Beside a control rather than inside its `<label>`, it leaves the control's accessible name
  exactly as it was, so nothing that looks a switch up by its own name — a screen reader, or a test — has to know
  the hint exists. Hover and keyboard focus still open it; the hover target narrows from the control to the icon,
  which is the same trade v0.374.11 made. No page gets taller (14 px icon, `lineHeight: 0`, no padding).
  **Tests (+10):** `HintIcon.test.tsx` (+6 — tap opens, second tap and blur dismiss, hover and focus still open
  it, Enter/Space, it never operates the control beside it, and the control's own name is unchanged) and one
  fail-before regression at each of the three routes, each asserting the words appear *and* that the control did
  not move: `Editor.test.tsx` (the switch stays checked and `autoProcess` still gets `undefined`),
  `Jobs.test.tsx` (`requestPermission` not called), `Gallery.test.tsx` (still sorted by Newest).

  **▶ FIFTH SLICE SHIPPED — v0.413.0, the *other* half of the class: an anchor with no behaviour at all**
  (Builder 2026-09-10, branch `claude/sweet-babbage-w1qz43`). The four slices above are all about a tooltip on a
  **control** — where the tap does the wrong thing. **Enumerated rather than guessed at:** of the app's 105
  `<Tooltip>`s, **53 hang off an anchor that is not a control at all** — a `Badge`, a `Text`, a `Box` — where the
  tap does not do the wrong thing, it does *nothing*, and the sentence simply is not written on a phone.
  Mantine ships `events={{ hover: true, focus: false, touch: false }}`, so these open on `mouseenter` and on
  nothing else; **turning its `touch` on is not the fix** — floating-ui opens on `pointerenter` and closes again
  on the `pointerleave` a lifted finger fires, so the answer flashes and goes. New
  `components/HintAnchor.tsx` is the app's own controlled-tooltip affordance (`HintIcon`, v0.402.1) applied to
  an anchor with nothing of its own to collide with: it **clones the child** rather than wrapping it, so no row
  moves and no page gets taller, and it keeps the site's own handlers and role if it set any.
  **This slice is the verdict chips on a stack card** — the words a beginner meets in History and the Gallery
  whose whole meaning is the tooltip: `NoiseReadout` ("Noise 0.021"), `NoiseDelta`, `CleanestBadge`,
  `FocusChip` ×2 ("✨ sharpest yet" / "softer than usual"), `CalibrationBadge`, `HazyNightBadge`,
  `PanelSeamsBadge`, `RejectionBadge`, `FrameCountBadge`'s thin-stack warning, and History's own
  *"what's this?"* under Noise trend — which is the sharpest case of all, since those two words are an
  *invitation* and a hover-only reply to them is a dead link. Hover is byte-for-byte what it was; keyboard users
  gain the hints for the first time. **Tests (+9):** `HintAnchor.test.tsx` (+6 — tap opens, second tap and blur
  dismiss, hover still opens, Enter/Space, the anchor's own `onClick`/`role` survive, and no wrapper element is
  inserted) plus one fail-before regression each in `NoiseBadge.test.tsx`, `HazyNightBadge.test.tsx` and
  `History.test.tsx`.
  **▶ SIXTH SLICE SHIPPED — v0.413.1, the planning surfaces, which are the most phone-critical in the app**
  (same run, same branch). You read *Tonight* standing next to the scope, in the dark, on a phone — it is the
  one page whose *whole purpose* is answered away from a desk — and every verdict on it explained itself on
  hover and nowhere else: the score badge ("Higher = better placed tonight"), and the four per-target chips
  (`readyHint`, `difficultyRowBadge`, `framingRowBadge`, `recentreNudgeRowBadge`), each of which is a
  two-or-three-word verdict whose *reason* is the tooltip. Nine sites: `routes/Tonight.tsx` ×5,
  `SuggestTargetsCard` ×2 (the Dashboard's copy of the same two chips), `ContinueTonightCard`'s re-centre nudge,
  and `NextSessionCard`'s window line — whose hint is the honest **UTC** anchor behind the local wall-clock it
  prints, i.e. the same anchor its own `.ics` carries. Four now-wrong "shown on hover" comments in
  `components/nextSession.ts` refreshed with it. **Tests (+2, both fail before):** `Tonight.test.tsx` (a tap on
  "Needs mosaic" produces the sentence) and `NextSessionCard.test.tsx` (a tap on the window line produces its
  UTC).
  **▶ SEVENTH SLICE SHIPPED — v0.413.2, the two priority-1/2 pages, and it carries a *bug* like the second and
  fourth slices did** (same run, same branch). The Target page's header badges — `N integration`, **`N streaked`**
  and **`N trailed`** — each sit *beside a bulk-reject button*, and what a streak is (and that Auto outlier removal
  takes the trail out while **keeping** the frame) lived only in the badge's tooltip: on a phone the destructive
  button was the more reachable of the two. **The bug is in the editor:** `SlowPreviewChip` is a warning rendered
  *inside* the Add menu's `Menu.Item`, so the one gesture a touch user had for *"what does 'slower preview' mean?"*
  **added the very op it warns about** — the v0.402.1 defect one level out, and the same shape again in `OpList`'s
  three row chips (the edited dot, the heavy badge, the stage-conflict line), where the tap selected the op. That
  needed a new opt-in `stopPropagation` on `HintAnchor`, deliberately **off** by default: swallowing a click a page
  expects to receive is the worse failure of the two. Eight sites (`Target.tsx` ×3, `Editor.tsx` ×2, `OpList.tsx`
  ×3). **Left alone on purpose, with the reason:** the frames table's column headings (the tap *sorts*, which is
  the primary action, and v0.270.0 already gave those sentences a reachable home in `FrameColumnGuide`) and the
  per-frame `Rejected — …` badge (the tooltip repeats the badge's own text — category (b) of this entry).
  **Tests (+3, two fail before):** `HintAnchor.test.tsx` (the flag swallows the container's click and its absence
  does not), `Target.test.tsx` (a tap on "2 streaked" produces the sentence) and `Editor.test.tsx` (a tap on
  "slower preview" produces the sentence **and leaves the op list empty**).
  **Still open after all three:** the ~22 remaining non-control anchors — `NightsCard` ×3, `BestMonthsStrip`,
  `MosaicMapCard`, `BestPictures`/`Gallery`/`Calibration`/`LifeList`, and `ImageLightbox`'s bare-icon anchors.
  `HintAnchor` makes each a one-line swap; take them a coherent surface at a time, not as a sweep.

  **▶ EIGHTH SLICE SHIPPED — v0.414.0: the "still open" list above, and the guard that stops a ninth**
  (Builder 2026-09-10, branch `claude/sweet-babbage-bhkhl1`). **Read the collision note first
  ([`PROCESS-NOTES.md`](PROCESS-NOTES.md), 2026-09-10, collision #14):** two Builders swept this entry in the
  same hour, from opposite ends of the same measurement. `HintAnchor` and its 28 anchors landed on `main`
  first and are the record; my own component and its 33 anchors were **dropped rather than re-applied**, and
  what is here is only what theirs did not reach. On the one point where the two differed, theirs is better
  and is what ships: `stopPropagation` for an anchor inside something clickable, which mine did not have.
  **What this slice adds is the remainder of that list**, converted to `HintAnchor` one line each:
  `NightsCard` ×3 (a night's *"ended early"*, *"bright Moon"* and its verdict badge — the Target page's own
  per-night table), `Calibration` ×2 (the broken-pixel repair state and each master's defect note, the two
  sentences on that page that are not restatements of a control), `BestPictures` ×2 and `Gallery` ×1 (the
  *"why is this picture here"* and *"what is this count"* chips). `NightsCard`'s verdict badge **skips the
  anchor entirely when it has no sentence** rather than passing `disabled`: `HintAnchor` makes its child a
  tab stop with `role="button"`, and a verdict with nothing to say must not advertise itself as answerable.
  **And the guard, which is the durable half.** `components/hintAnchorDrift.test.ts` reads every non-test
  `.tsx` in the app through Vite's own `import.meta.glob` and fails if any `<Tooltip>`'s first child element
  is a `<Badge>`. Eight sweeps have each fixed the sites that existed on the day and nothing stopped the next
  one being written the old way — which is precisely how the badges survived the first four, since this
  entry lists its open work by *route* and they live in shared components no route owns. It is proven armed
  two ways rather than trusted: against a synthetic bad site, whose `file:line` it reports, and by asserting
  the sweep really walked the tree (>80 files, two named ones present) — an empty result is what a clean
  tree and a broken scanner both look like. It deliberately says nothing about a `Tooltip` on a *control*:
  that half is a judgement per site (a button that only previews something is a safe way to find out), which
  is not a guard's business. **It caught a non-defect on its first real run and the rule was narrowed
  honestly rather than quietly:** it flagged the frames table's `Rejected — …` badge, whose tooltip repeats
  the badge's own text — the site the seventh slice had already, correctly, left. So the rule is *a
  `<Tooltip>` around a `Badge` is a defect **when the tooltip says something the badge does not***, and the
  other case opts out with a `hint-anchor-exempt:` marker carrying its reason; a second test pins the
  exempt list **by file**, so a second exemption cannot be added silently.
  `frontend/tsconfig.json` gains `"vite/client"` to its `types` so
  `import.meta.glob` is typed; `vite` was already a devDependency and nothing new is installed.
  **▶ NINTH SLICE SHIPPED — v0.414.1, the one *interactive* site the same measurement said was worth
  doing** (same run, same branch). Stack's **"Save as defaults"** carried its sentence on a `<Tooltip>`
  wrapped around the button, and that sentence is the only statement anywhere that the button also decides
  what the *unattended* walk-away stack does for that target — a persistent effect, since the saved blob
  wins over `default_stack_options` in both readers (v0.372.0). So on a phone the one gesture available for
  "what does this do?" was the gesture that did it: the v0.402.1 defect on a button whose consequence
  outlives the page. (The explanation *does* exist — in the success notification, i.e. after the save.) Now
  a `HintIcon` **beside** the button inside a `Group gap={6}`, so its label, action and accessible name are
  untouched and the four existing assertions that find it by role and name pass unchanged. **The rest of the
  interactive half stays category (b), checked rather than assumed:** the editor's preview-tool row has had
  `PreviewToolGuide` since v0.402.0; `IncomingCalibrationCard`'s tip only names the file its own card
  describes; History's *"Reuse settings"* / *"Compare"* navigate, which is reversible, and would need one
  icon **per run card** — the "one more always-on element" the standing IA priority exists to prevent; and
  Stack's disabled *"Start stacking"* tip repeats, word for word, the yellow *"No plate-solved frames yet"*
  alert at the top of the same page (a disabled `<button>` receives no pointer events, so it was never
  reachable on a mouse either). Regression in `Stack.test.tsx`, failing before **by saving**.

  **▶ TENTH SLICE SHIPPED — v0.429.1, and it closes the named list** (Builder 2026-09-12, branch
  `claude/sweet-babbage-8i7zw0`). The four the ninth slice left were "a chart cell or an icon button, not a
  chip, so each wants its own judgement" — so each got one, and the answers differ.
  **Two are real, and both are the fifth slice's class (an anchor with no behaviour at all, where the tap does
  nothing and the sentence simply is not written on a phone):** `LifeList`'s **still-to-shoot tile**, whose
  `item.blurb` is the only sentence saying what the object *is* — the whole half of that page where a beginner
  decides what to point at next, ~108 tiles of it, and the star beside each is a *sibling* of the tile so the
  swap cannot swallow it; and `BestMonthsStrip`'s **twelve heat cells**, each carrying that month's own numbers
  ("up ~5.3 h in the dark, peaks 45°") — the strip's visible verdict says *which* months are good, and only the
  cells say *how* good. One `HintAnchor` line each.
  **Two are not, checked rather than assumed.** `ImageLightbox`'s bare-icon anchors are category (b): every one
  of the six (`Zoom in`, `Zoom out`, `Reset`, and the three downloads) carries a tooltip that is word-for-word
  its own `aria-label`, so there is no sentence being withheld — only an icon whose name a sighted phone user
  cannot read, which a `HintIcon` beside each would answer by putting six more elements in a toolbar, against
  the standing IA priority. And ~~**`MosaicMapCard` does not exist** — the name has been on this list since the
  seventh slice and there is no such component (the mosaic surfaces are `MosaicThinHoldNote` and the panel map,
  neither of which has a `Tooltip`).~~ — **THIS HALF IS WRONG; corrected the same day by the eleventh slice
  below.** `frontend/src/components/target/MosaicMapCard.tsx` has existed since 2026-09-09 (PR #804), it *is*
  the panel map, and every one of its cells was wrapped in a plain `Tooltip`. Don't re-derive a component's
  absence from recall — `git log --diff-filter=A -- <path>` settles it in a second.
  **No page got taller, measured rather than argued** (`agent-dogfood.sh --empty`, before and after):
  `/life-list` is **2,779 px on a phone and 1,224 px on desktop, identical to the digit** — `HintAnchor` clones
  its child instead of wrapping it, so there is no new element to take up room. Hover is byte-for-byte what it
  was; keyboard users reach both for the first time. **Tests +2, both verified red** by restoring the plain
  `Tooltip`.
  **Still open:** the interactive half of the class generally — a `Tooltip` on a control, which stays a
  judgement per site.

  **▶ ELEVENTH SLICE SHIPPED — v0.434.0, the app's two *maps*; and the tenth slice's closing claim was wrong**
  (Builder 2026-09-12, branch `agent/builder-2026-09-12`). Every slice so far has been about a **chip** — one
  anchor carrying one sentence. The two surfaces left are **grids**, where *every cell* carries its own number
  and the picture is useless without them, and neither was ever a one-line swap; that is why ten sweeps went
  past them.
  **`MosaicMapCard` does exist, and did when the tenth slice said it did not** —
  `frontend/src/components/target/MosaicMapCard.tsx`, added 2026-09-09 (PR #804), i.e. *before* the eighth
  slice that was meant to drain the list it had been sitting on since the seventh. So the card the owner —
  **a heavy mosaic user** — reaches to ask "which corner is behind?" answered on hover and nowhere else, and
  the record said it had been checked. It takes `HintAnchor` exactly as the chips
  did — `panelTooltip`'s sentence unchanged — but with the **roving `tabIndex`** described below rather than a
  tab stop per cell: `mosaicmap.MAX_GRID_SIDE` allows 24 panels a side and this owner shoots wide mosaics, so
  the chip precedent's one-stop-per-anchor would put dozens of them on the busiest page in the app. Arrow keys
  walk the panels in reading order (holes skipped), and the hint follows focus because `HintAnchor` already
  opens on it.
  **The Dashboard's imaging calendar was on no list at all**, and it is the harder half: up to ~370 cells, of
  which every imaged night carried its date, hours and targets on an 11 px square, on hover only.
  `HintAnchor` is the **wrong** tool there — it makes its child a tab stop, and one per night would put a
  hundred of them on the Dashboard ahead of the rest of the page. So the grid gets the pattern that scales: a
  **roving `tabIndex`** (exactly one night in the tab order — the picked one, else the most recent), arrow
  keys walking the nights through the new pure `activityCalendar.nightDates` / `stepNight`, and the answer in
  a **read-out that shares the legend's own row** rather than a tooltip over a square a finger cannot hit.
  Stops at either end rather than wrapping, so a held key gives the page back its scroll. The `Tooltip` is
  kept untouched for a mouse; the container's `role="grid"` — which it never earned, having no rows or cells —
  becomes `role="group"`.
  **No page gets taller:** the read-out occupies the slot "Less … More" already sat in, and before a night is
  picked it holds the prompt that makes the grid look answerable at all (`CALENDAR_PROMPT`).
  Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change.
  **Tests +10** — 6 pure (`nightDates` chronological and imaged-only; `stepNight` both directions, both ends,
  the no-selection start, and an unknown date) and 4 on the cards, **the two behavioural ones verified red** by
  restoring the plain `Tooltip` in a scratch copy.
  **The class is now clean, enumerated rather than claimed:** a scan of every non-test `.tsx` for a `Tooltip`
  whose first child is a non-control leaves five sites, each checked — the calendar cell (its own tap handler,
  above), `Gallery`/`BestPictures`' `<Image>` and `History`'s link-`Text` (the tap opens the thing the tooltip
  describes, so it already does the right thing), the frames-table column headings (the tap *sorts*;
  `FrameColumnGuide` has held those sentences since v0.270.0), and the written-down `Rejected — …` exemption.

- **IMPROVEMENT IDEA (Scout 2026-07-23) — surface calibration-master mismatches (and a *never-applied* wrong-shaped
  bias) at *bind time* in the calibration UI, not only buried in the stack log.** *(Friendliness + trust; size S–M;
  PRIORITY 3, adjacent to image-quality.)*
  **▶ PARTIAL — the two exposure/temperature mismatch advisories are now surfaced at pick-time on the Stack form.**
  The exposure-mismatch half shipped earlier as the inline `darkWarning`/`flatDarkWarning`/`darkScaledNote`/
  `biasIgnoredForLights` cautions the Stack form renders beside each master `Select` (with a one-click "scale this dark"
  fix). The **temperature-mismatch** half shipped **v0.208.1** (Builder 2026-07-25, branch `claude/pensive-faraday-jqlh52`;
  frontend-only, tested): a new inline `darkTempWarning` warns whenever the chosen light-dark's `sensor_temp_c` and the
  target's median sub temperature (`calibrationSuggestions().params.sensor_temp_c`) are both known and differ by ≥5°C —
  mirroring the engine's `CalibrationMasters.calibration_warnings` temperature advisory (`_TEMP_MISMATCH_TOL_C=5.0`),
  which until now reached only the stack log. It's independent of the exposure warning (a dark can match on exposure yet
  be temperature-mismatched — and, unlike an exposure gap, bias-scaling can't correct it), so it fires even on an
  exposure-matched dark. Regression: `frontend/src/routes/Stack.test.tsx` (+1 — an exposure-matched 30 s dark shot 15°C
  warmer warns on temperature with *no* exposure warning). Upgrade-safe: frontend-only, additive, reuses data already in
  the suggestions payload; no API/schema/default change.
  **▶ SLICE (c) — the wrong-camera/binning half SHIPPED v0.215.0** (Builder 2026-07-30, branch
  `claude/relaxed-turing-m9ayja`; tested). A master whose dimensions don't match the target's frames is not merely a
  poor match — `CalibrationMasters.validate` **refuses** it, so the whole stack job dies with an error a beginner
  can't decode (and, since v0.214.0, the walk-away auto-stack silently *skips* it, so "I added darks" quietly isn't
  true). Both now get said out loud at pick time. **Backend:** `GET /api/targets/{safe}/calibration-suggestions`
  gained `params.width_px` / `params.height_px` — the target's **modal** raw frame size via a new shared
  `webapp/calibration.py::modal_dim` (lifted out of `pipeline._confident_master_binding`, so one mis-ingested frame
  from another camera can't move the size every master is judged against). Additive keys; the masters payload already
  carried each master's own dims, so that's all the frontend needed. **Frontend:** a pure, unit-tested
  `frontend/src/calibrationFit.ts` (`masterFitsFrames` / `masterSizeWarning` / `masterOptionSuffix`) drives (i) a
  **red** inline alert under each of the four master selects naming both sizes and saying the stack would fail, and
  (ii) a "— wrong size for this target" suffix in the picker itself, so a mismatched master reads as unusable
  *before* it's chosen (and never carries the ★ recommended badge). Deliberately one-sided, mirroring the server-side
  gate: an older master that recorded no size, or a target whose frames never recorded one, can't be disproved and is
  never flagged. Tests: `calibrationFit.test.ts` (+7), `Stack.test.tsx` (+2 — a 1080×1920 dark on 480×320 subs warns
  *and* is marked in the picker; a matching dark stays silent), `tests/webapp/test_calibration.py` (+3 — the frame
  size is reported, is `None` when unrecorded, and `modal_dim` ignores strays/unknowns). Upgrade-safe: two additive
  response fields + display-only frontend; no config/DB-schema/on-disk/default change and no API-shape break (an
  older client ignores the new keys; a newer client against an older backend simply can't disprove anything and flags
  nothing). ~~**Still open:** the narrower *bias-shape-vs-dark* inert case (a bias whose shape doesn't match the
  **dark** it's paired with, rather than the frames) — same idea, different comparison.~~
  **▶ SLICE (d) — the bias-shape-vs-dark case SHIPPED v0.245.4** (Builder 2026-08-07, branch
  `claude/gallant-galileo-hyz6ug`), and chasing it turned up **a real engine bug** in the same predicate.
  `_dark_scaling_applies` correctly requires the bias to be the **dark's** shape (it holds the readout pedestal fixed
  while the dark current is rescaled), and falls back to subtracting the dark **unscaled** when it isn't — but two
  places tested only "a bias is loaded":
  **(1) the FITS provenance (the bug).** `_build_output_header_meta` (`seestack/stack/stacker.py`) stamped
  `DARKSCAL`/`DARKDEXP`/`DARKLEXP` on that looser test, so a run whose bias couldn't scale anything still told the
  owner *"Dark scaled to sub exposure · 30s → 10s"* in the run Info / History — about a dark the engine had
  subtracted untouched, at full 30 s pedestal, on every frame. The stamp now asks the bundle itself via a new
  `CalibrationMasters.dark_scaling_provenance(light_exposure_s)`, which returns non-`None` under exactly the
  condition `_effective_dark` scales under, so the claim and the pixels can't drift again. *(Regression test fails
  before / passes after.)*
  **(2) the Stack form.** It said *"Dark exposure-scaling is on — this 120s dark will be scaled to match your 30s
  subs"*, a promise the stack doesn't keep, and suppressed both the real exposure warning and the "your dark already
  contains the bias" note. `darkScalingActive` now also requires `darkScalingBlockedNote(dark, bias)` to be null, and
  a new yellow note names both sizes and says the dark goes in unscaled. The engine's own advisory got the same
  treatment: its exposure warning used to end *"or turn on dark exposure-scaling (needs a master bias)"* — advice
  the user has already taken — and now explains the shape clash instead.
  **Also fixed alongside:** the bias slot's red *"Stacking with it will fail"* size warning was simply untrue once a
  dark was chosen — `validate` only refuses a wrong-sized bias when it is the calibration (no dark), so the stack
  runs and quietly ignores it. `biasSizeWarning(bias, frames, dark)` now stays silent there and lets the scaling note
  say what the size actually decides. **Not affected:** the unattended auto-binder, which gates dark *and* bias
  against the subs' dimensions, so anything it binds already matches. Upgrade-safe: no config/DB/on-disk/API-shape
  change, no default flipped, and the stamp is only ever *withheld* where it was previously wrong. Tests:
  `tests/test_output_header_meta.py` (+1 fail-before, and its fixture now builds a **real** `CalibrationMasters`
  instead of a hand-rolled stand-in — the mock is how the stamp drifted from the pixel path in the first place),
  `tests/test_calibrate.py` (+2 — the warning names both sizes and stops asking for something already done;
  `dark_scaling_provenance` agrees with `_effective_dark` on all four outcomes), `calibrationFit.test.ts` (+6),
  `Stack.test.tsx` (+1 fail-before).
  **▶ THE AFTER-THE-FACT HALF SHIPPED TOO, v0.215.1** (Builder 2026-07-30, same branch; tested). Pick-time is only
  half the story: the walk-away user never opens the Stack form, so they meet the problem as an uncalibrated result
  in History next to a library that visibly *holds* a dark. `calibration.diagnose_uncalibrated` — the
  "why was my stack uncalibrated?" advice already rendered on the run's History card via
  `calibrationSummaryText(cards, calibration_advice)` — only recognised **one** signature (a gain/temp-matching dark
  at the wrong exposure with no bias to scale it) and fell back to the generic "build or pick a master" copy for
  everything else, which reads as a bug when a master is sitting right there. It now takes the target's
  `width_px`/`height_px` and detects the **wrong-camera/binning** signature first (`_wrong_size_advice`): *"Your
  master dark was built at 1080×1920, but this target's frames are 480×320 — a different camera or binning mode, so
  it can't be applied. Build a master dark from frames shot the same way as these subs."* (plural variant when
  several all conflict). Checked **before** the exposure signature, since advising "build a bias to scale it" is
  false while the dark can't be applied at all; and only when **every** master of that kind conflicts — with one
  usable master left, size isn't why the stack was uncalibrated. The three size gates (unattended auto-binder, saved-
  pick binder, this diagnosis) now share one `calibration.dims_conflict` rule so they can never disagree.
  `_uncalibrated_advice` (`webapp/routers/stack.py`) passes the modal frame dims. Tests:
  `tests/webapp/test_calibration.py` (+6 — the advice fires, outranks the exposure advice, needs *every* master to
  conflict, stays silent when either side's size is unknown, the plural flat wording, and `dims_conflict`'s
  one-sidedness), `tests/webapp/test_stack_render.py` (+1 endpoint — a wrong-size dark yields the new advice). One
  pre-existing endpoint test registered its "mismatched dark" as a **4×4** master against 480×320 frames — an
  unrealistic fixture that the new (correct) signature now pre-empts; it was re-registered at the target's real frame
  size so it still exercises the exposure signature it was written for. Upgrade-safe: additive keyword args with
  `None` defaults (an omitted size skips the new signature entirely), advisory string only, no
  config/DB/API-shape/default change.
  `CalibrationMasters.calibration_warnings()` already produces the right
  plain-language advisories ("Master dark is 30s but your subs are 10s — its pedestal will be over-subtracted on every
  frame…"; the temperature-mismatch line), and this run's fix keeps them honest. But they only reach the *stack log* —
  a beginner binding a dark/flat/bias to a target never sees them until (if ever) they read a log, so they ship a
  silently mis-calibrated stack. Idea: when a user binds masters (the calibration bind dialog / `POST` bind endpoint),
  compute and return these warnings against the target's representative sub exposure/temperature and show them inline
  ("this dark was shot at a different exposure — turn on exposure-scaling or use a matched dark"). Also flag a
  **loaded-but-inert** master: a bias whose shape doesn't match the dark (never applied — the case behind this run's
  bug) or a master whose dimensions don't match the target's frames, with a plain "this master won't be used because it
  doesn't match your camera/binning" note — so the user isn't misled into thinking calibration is happening when it
  isn't. Read-only/additive: reuses the existing `calibration_warnings` + `validate` logic at a new (bind-time) call
  site; sane default is simply *showing* what the engine already computes. Ship as a slice: (a) return warnings from the
  bind/preview endpoint; (b) render them in the bind dialog; (c) add the inert-master notice. Serves the OSC beginner
  who "added darks" and expects them to just work.
- Guided "getting started" / empty states that tell a first-timer exactly what to
  do next; audit every screen for jargon and add plain-language "why" tooltips;
  reduce visible option clutter (progressive disclosure). (M, friendliness)
  _(Progress: the **glossary** half shipped as **v0.423.0** — the term reference
  is now a page in the web app (`/glossary`) instead of a `docs/` file only the
  retired desktop GUI could open, with an anchor per term so a tooltip can link at
  the word it just used. ✅ **The linking half shipped as v0.461.0** — `GlossaryLink`
  off an additive `StackOptionField.glossary` / `OpSpec.glossary`, on the 20 stacking
  controls and 9 editor ops that name a term, with a slug sweep
  (`tests/test_glossary_links.py`) so a link can never be dead. What is left of this
  item is the *prose* audit — a sentence somewhere in the app that says a term without
  explaining it and has no descriptor to hang a slug on. Take those one surface at a
  time, link rather than grow a new tooltip, and make sure the sweep covers the new
  link.)_
  _(Progress: the **Jobs page** — the very first screen a beginner lands on after
  clicking "Scan incoming" — was the last route showing raw engine jargon; its
  snake_case job kinds (`pipeline`, `qc_solve`, `editor_png`…) are now translated
  to plain language and its empty state guides to "Scan incoming" — shipped
  v0.84.2. A Builder dogfood of the other five routes (Dashboard/Library/Target/
  History/Editor) found them already well-handled with icon+prose+next-step empty
  states, beginner tooltips, and translated reject/combine labels.)_
- Better long-job feedback and clearer error messages. (S, friendliness)
  _(~~Idea: map the handful of known fatal `job.error` messages to plain language~~ —
  **shipped v0.84.3** (see Shipped). A `friendlyJobError` helper now translates the
  memory-budget refusal, "nothing plate-solved to stack", empty-alignment, and
  missing-reference-WCS failures into a plain sentence + next step, falling back to the
  raw text verbatim for anything unrecognised. Remaining long-job-feedback ideas welcome.)_
  _(~~Follow-up idea, found while shipping v0.84.3: `friendlyJobError` matches on the raw
  exception *string*, which is brittle if an engine message is reworded. Stamp a stable
  canonical `error_kind` server-side and prefer it in the frontend.~~ — **shipped v0.84.4**
  (see Shipped). `JobManager` now classifies a fatal exception into a canonical `error_kind`
  (`memory_budget`/`no_solved_frames`/`no_alignment`/`no_reference_wcs`) at the catch point,
  persists it (additive `error_kind` column, in-place migration), and exposes it on the job;
  `friendlyJobError(raw, kind)` prefers it and falls back to the string matcher on an older
  backend.)_
  _(~~Follow-up, found while shipping v0.84.4: the calibration **Build-master** job raises a
  bare `FileNotFoundError: No FITS files found in {dir}` when pointed at an empty/wrong
  folder — a common beginner mistake in the darks/flats workflow that showed a raw Python
  exception on Jobs.~~ — **shipped v0.84.5** (see Shipped). Added a `no_fits_in_folder` kind +
  translation ("No FITS frames were found in that folder" + point-at-the-right-folder next
  step), matched on the specific phrase so internal FileNotFoundErrors aren't mis-dressed.)_

### Image quality — for the OSC Seestar workflow (PRIORITY 4)

- ~~**LEAD (Builder 2026-09-18, filed while shipping v0.464.0 — the third representative value, and the one the
  engine cannot see at all) — a gain-mismatched master dark is applied silently, and the run's own
  mismatch advisory is structurally unable to mention it.**~~ — **✅ SHIPPED v0.466.0** (Builder 2026-09-18, the
  same day). Entry cut to [`SHIPPED.md`](SHIPPED.md), one-liner under "Shipped". **The gate it was filed behind
  turned out to be the wrong question, and that is the part worth keeping:** the lead asked for a *gain
  tolerance* and rightly said no honest one exists in this repo — but a tolerance is what a *severity* verdict
  needs, and gain does not get one. An exposure has a correction (`scale_dark_to_light`) and a temperature is a
  continuous drift that earns a bar wide enough to cover a night; a gain is a **setting nothing anywhere
  corrects for**, and the app already treats it with zero tolerance in `_acquisition_reason`
  (*"it was shot at gain 200, your subs at gain 80"*, fired on `gain_d > 0`). So the advisory states both
  numbers instead of grading the gap, and `GAIN_MISMATCH_TOL` absorbs header round-trip noise and nothing else.
  Its shape (a) was built — `dark_gain` carried onto `CalibrationMasters` — and its (b) was built *with* it
  rather than instead of it, because the entry is right that (b) alone re-creates the form↔run split v0.464.1
  exists to close. The observer question it ends on is answered for free either way: the advisory is silent on a
  library shot at one gain, which is what a Seestar gives.

- **NEW IDEA (Builder 2026-09-04, the *behavioural* consequence of the v0.340.0 measurement — read the caution
  before touching this) — an unattended drizzle run could skip a rejection pass that provably clips nothing,
  and get 1.75× of its canvas memory back.** *(Pillar: autonomy + image quality — PRIORITY 2/4; size S to
  write, **L to be sure of**; the on-by-default hot path, so measure or leave it.)* v0.340.0 measured that the
  two-pass drizzle clip removes **nothing at all** below `kappa_min_frames` samples on a pixel — the block in
  the sweep came out at the naive average to a part in 1e-3 at every depth up to 10. `_afford_drizzle_reject`
  nonetheless takes the pass whenever `n >= 4` on the *target's* frame count, and the pass costs
  `_PEAK_CANVAS_ARRAYS_DRIZZLE_REJECT` (7) full-canvas RGB planes against the single pass's 4 — the 1.75×
  jump that `_guard_stack_memory` refuses on, and the exact reason the unattended path already forgives it
  when the budget is short. **So on a thin drizzled mosaic the app is paying its largest memory premium for a
  pass whose output is bit-identical to not running it** — and the owner's union mosaic canvas is the largest
  canvas this app builds. Declining it there would make some runs fit that today are stepped down to a smaller
  `drizzle_scale`, i.e. *better* pixels from a smaller footprint.
  **Why this is filed, not built.** "Bit-identical" is a claim about the sweep's fixture, not a theorem: the
  clip's own Bessel correction and the per-pixel `neff` gate mean the honest bound is per-*pixel*, and a
  mosaic has a deep centre and thin edges — a canvas whose peak coverage clears 11 must keep the pass even if
  its thinnest panel does not. So the gate would have to be the **coverage plane**, which is not known until
  the canvas is built, where `_afford_drizzle_reject` is priced. And the failure mode is silent: get it wrong
  and a satellite that *would* have been clipped is baked into the owner's picture with no note anywhere. Do
  it only with a before/after showing bit-identical output on a real mosaic at several depths, and with the
  skip stamped in the provenance the way `DRZREJSK` already stamps the memory case.

- **Let a mosaic choose its rejection method *per pixel*, not once for the whole canvas.** *(Pillar: image
  quality — PRIORITY 4; size L; opened by the A6 fix, v0.326.7.)* A6 fixed `auto_reject` reading the target's
  frame count where the honest number is a panel's depth, and it now sizes the method from the **thinnest
  substantial panel**. That is the right global answer, but it is still *one* answer: on a mosaic carrying a
  3-sub panel beside a 200-sub panel, the deep panel is stacked with min/max and loses κ-σ's multi-outlier
  reach and its quality weighting, purely because a thin neighbour exists. The coverage plane already knows
  each pixel's true sample count (`frame_coverage`), and both accumulators already degrade per-pixel, so the
  shape is "dispatch from the coverage plane" rather than "pick one and hope". **Why it's L and not M:** it
  touches the combine hot path and its memory bounds (two accumulators live at once, or one that switches
  rule per pixel), and the provenance card / `REJMODE` / `stackhealth` all currently assume a single method
  per run. Wants a measurement first: how often does the owner's real library actually have a mosaic whose
  panel depths straddle `kappa_min_frames`? If the answer is "rarely", the global choice is good enough and
  this should be closed rather than built.

- **Re-measure the panel floor against real mosaic data once there is any.** *(Pillar: image quality —
  PRIORITY 4; size S; opened by the A6 fix.)* `AUTO_REJECT_PANEL_MIN_FRAMES` is 3 because that is the smallest
  population *either* method can act on, which makes it un-arbitrary — but it also decides when a stray
  mis-solved sub counts as a panel. It has only ever been exercised on synthetic pointings. When a real
  mosaic's per-panel counts are to hand (the Scout has pulled the owner's folder listing before), check that
  the clustering separates his panels the way the synthetic fixture does, and that no panel of his lands on
  the wrong side of the floor.

- **NEW IDEA (Builder 2026-08-31, the anchoring question the v0.320.1 per-panel patches deliberately left
  measured-but-unaddressed) — chain each mosaic panel's refine reference to a neighbour it overlaps, so the
  whole mosaic keys off *one* plate solve instead of one per panel.** *(Pillar: image quality — PRIORITY 4;
  size M; **do not start this without a measurement that says it is needed** — see below.)* Every panel now
  cuts its reference patch from its own central sub, and every patch is aligned to the same canvas WCS, so the
  panels are tied together only as tightly as their two reference frames' *plate solves* agree. In principle a
  panel can therefore sit a fraction of a pixel off its neighbour where before it sat wherever its solve put
  it. **The measurement says this is not currently costing anything:** on the four-panel fixture the finished
  seam step went **down**, 0.052 → 0.039 sky sigma, because individually-sharper panels beat the notional
  drift. So this is filed as a *lead*, not a defect.
  **The shape if a real mosaic ever shows it:** mosaics overlap by design (a Seestar steps ~0.8 of a field, and
  the 512² patch is wider than a 480 px panel — measured overlap ~116 px, well over the 64 px correlation
  floor), so a panel's reference frame can itself be refined against an already-built neighbouring patch
  *before* its own patch is cut, walking one anchor outward from the reference panel. **What would justify it:**
  `SEAMRES` measured on a real multi-panel Seestar mosaic with `subpixel_refine` on, compared against the same
  subs stacked with refine off. If the seam is not worse, leave this alone — it adds an ordering dependency
  between panels for no measured gain.

- **IDEA / GPU-ONLY HARDENING (Scout QA audit 2026-08-27 #18, traced — NOT a verified bug; unreproducible
  without cupy, nil-impact on fully-NaN tiles) — `per_frame._subtract_background_gpu` (`seestack/bg/per_frame.py`
  ~line 604) fills a *fully-masked* background tile with the global **luminance** median (`luma_med`) rather than
  with neighbouring-tile values as the adjacent comment claims. For a low-sky channel (e.g. blue) that is the
  wrong per-channel scale, and the bicubic tile-grid interpolation could bleed it into coverage-edge tiles,
  faintly tinting a mosaic panel's edge.** *(Pillar: image quality — PRIORITY 4; size S; GPU path only.)*
  **Why it's not filed as a bug.** The direct effect on a *fully-NaN* tile is nil (`NaN − x` stays `NaN`, so the
  gap survives); the concern is only the interpolated bleed into *adjacent partially-covered* tiles, and it could
  not be executed/measured (no cupy in the audit env). The **CPU path is clean** (the bg audit reproduced it).
  So this is a hardening lead for a GPU-capable follow-up, not a known-wrong result. **Fix direction (when a GPU
  box is available to test on):** fill a fully-masked tile from its nearest covered neighbours in the *same
  channel's* tile grid (or leave it NaN and let the existing coverage-edge handling own it), matching what the
  comment says and the CPU path does — then verify on a real mosaic sub with a low-signal channel that no panel
  edge picks up a tint. Confidence: traced (single read; GPU path not executed). Do NOT blind-flip this on the
  hot path without a GPU repro.

- **NEW IDEA (Builder 2026-08-30, the one limitation deliberately accepted by the v0.304.1 panel-levelling fix (main's))
  — tell "this panel is sparse" from "this panel was hazy" using the panel's own *history*.** *(Pillar: image
  quality / trust — PRIORITY 4; size M; do NOT start it without deciding the cross-night comparability question
  below.)* `session_recap._level_panels` levels a mosaic's panels against each other **within one session**,
  which is the only signal available there — so a sky that closes in exactly at a panel boundary of a strictly
  sequential single-pass mosaic is levelled away with the panel step. It costs nothing on the common case (a
  Seestar revisits its panels, so real haze shows up *inside* each panel and survives), which is why the fix
  shipped as-is. The disambiguator is each panel's **own median over the target's whole history**: a panel
  scoring well below what that same panel usually scores was hazy, not sparse. `_compute_transparency_ratio`
  already does exactly this per panel, so the machinery exists. **The question to settle first:** the raw
  `transparency_score` is not comparable across gain/exposure changes, and a target's history can span a
  settings change — so a historical baseline needs either a gain/exposure guard or a fallback to today's
  within-session levelling. Fail back to the current behaviour whenever it can't be established; never guess.

- **LEAD (Builder 2026-09-08, filed with v0.387.0 because it is the one thing that shipped unmeasured) — how
  long does the overlap gain pre-pass actually add to the owner's mosaic stack?** *(Pillar: performance —
  size XS to measure, and **do not "optimise" it before measuring**.)* `overlapgain` runs up to
  `MAX_FRAMES_PER_PANEL = 5` subs per panel through `align.align_one` **sequentially** at stack setup — nine
  panels is 45 loads, each paying a debayer plus the per-frame `Background2D` fit, which is the expensive
  half. On this repo's fixtures it is seconds; on the owner's 1080×1920 subs it is plausibly 1–3 minutes,
  against a mosaic stack that runs for hours. That is very likely fine, which is exactly why it should be
  *measured* rather than pre-emptively parallelised: the obvious change (feed it the stacker's own
  `max_workers` pool) multiplies the pass's peak memory by the worker count on the one path §6 calls out for
  its OOM history. If a measurement ever says it matters, the cheaper lever is `MAX_FRAMES_PER_PANEL` — the
  ratio is a median over thousands of coarse cells, so 3 subs a panel would cost little accuracy — not
  threads. **Measure on real subs; the synthetic ones are 480×320 and prove nothing about this.**

- **NOTE for the "bisect the v0.158→v0.220 colour chain on a synthetic mosaic" follow-up above (Builder
  2026-08-05).** That entry asks a future run to measure "the visible plateau/edge structure" across a panel
  boundary with SCNR / the per-frame flatten / `remove_final_gradient` individually disabled — and warns that the
  raw seam step is dominated by the injected offsets, so a bespoke measurement is needed. `measure_seam_residual`
  (v0.233.0) **is** that measurement, already calibrated and tested: one unit-free number per configuration,
  measured on the finished image with the grain as its yardstick. Whoever picks that bisect up should run it
  rather than build a fresh harness.

- **IMPROVEMENT IDEA (Scout 2026-07-23) — a small (3-frame) default stack gets *no* outlier rejection at all, so a lone
  satellite/plane trail or cosmic-ray/hot pixel in any one of those 3 subs lands straight in the final picture.**
  *(Image-quality + autonomy pillar, PRIORITY 2/4; size S; **default-behaviour change — flag for care/owner judgement,
  see caveat**.)* **What's happening (traced this run):** the stack dispatcher gates κ-σ on `n >= 4`
  (`stacker.py:1177`) and min-max on `n >= 3` (`stacker.py:1144`); below those it silently runs plain **mean** with no
  rejection pass. With the *default* options (`sigma_clip=True`, `min_max_reject=False`, `auto_reject` off), a **3-frame
  stack** therefore falls through to plain mean — κ-σ genuinely can't bite at n=3 — and any transient outlier in one
  sub survives into the result. The owner's target user often stacks small first-light sessions; a single passing
  satellite is exactly the kind of thing they'd expect the stacker to remove. **Idea:** when the resolved method would
  fall to plain mean *purely because the frame count is below the κ-σ threshold* but `n >= 3`, auto-substitute a single
  **min-max reject** pass (drop the lone per-pixel extreme, mean the survivors) — the one rejection method that *does*
  work at n=3. This is what `auto_reject` already does deliberately for small stacks (`_resolve_auto_reject`); the
  proposal is to extend that safety to the *default* small stack too, so a beginner who never touched the Stack form
  still gets trail/hot-pixel protection on a 3–4 frame night. **Caveat (why it's an idea, not a fix):** this **changes
  the pixels** of an existing 3-frame default stack (mean → min-max-mean), i.e. a default-behaviour change on a live
  install (§9). It is arguably strictly *better* (min-max of 3 = the median-ish middle sample, robust to a single
  outlier, only marginally noisier than the 3-sample mean), but a default change wants a deliberate call. Ship it
  behind the existing `auto_reject`-style resolution rather than an unconditional flip if that keeps it opt-in-safe, or
  file for owner sign-off if it must change the bare default. **Tests:** a synthetic 3-frame stack with a bright
  trail/hot pixel in one sub → assert the trail is gone from the result and `STACKER`/`REJMODE` reflect min-max (pairs
  cleanly with the STACKER-label fix shipped v0.179.2). Confidence: traced.
  **▶ LARGELY OVERTAKEN BY EVENTS — re-check before spending a run on it (Builder 2026-08-17, verified in the
  code, not assumed).** This was filed in July, and the two paths a beginner actually reaches have both been
  given `auto_reject` since: **(1)** the *manual* Stack form seeds `auto_reject=True` for a never-configured
  target (`webapp/routers/stack.py::get_stack_defaults`, v0.149.0), and **(2)** the *walk-away* auto-stack injects
  `auto_reject=True` whenever the merged options carry no explicit rejection key
  (`webapp/pipeline.py::_stack_target`, ~L2101). `_resolve_auto_reject` then picks order-statistic min/max below
  `kappa_min_frames`, which is exactly the protection this entry asks for. **What is genuinely left is only the
  case the entry's own caveat says needs care:** a user who has *explicitly saved* `sigma_clip` defaults and then
  stacks 3 frames — i.e. someone who took control of the setting. Changing the pixels for them would be a default
  flip on a live install (§9) to override a choice they made, which is the wrong trade. **So: don't re-pick this
  as filed.** If anything is worth building here it is *advisory* — say on the Stack form that κ-σ can't remove a
  lone trail at this sub count and offer the one-click switch, the same shape as the shipped photometric-
  normalization nudge — not a silent change to their combine.

  **✅ THE ADVISORY HALF SHIPPED (Builder, v0.323.1, branch `claude/zen-mccarthy-v56oj1`) — and building it found
  that the form was giving the *opposite* advice, not merely no advice.** Nothing about anyone's combine changed;
  no threshold moved; no default flipped.

  **What was actually wrong.** The Stack form's low-frame caution fired below a hard-coded `SIGMA_CLIP_MIN_FRAMES
  = 5`, said sigma clipping *"can reject real signal as an outlier"*, and offered one button: **"Turn off sigma
  clipping."** At the default κ=3 every count it fired at (1–4) is a count at which κ-σ **cannot clip anything at
  all** — a lone point's z-score against statistics that still include it maxes out at `(n−1)/√n`, which does not
  reach κ=3 until `kappa_min_frames(3.0)` = **11 frames**, and below 4 the dispatcher does not even run the pass.
  So the app was telling a beginner with a 3-sub first light that their rejection was too aggressive, and offering
  to swap no rejection for no rejection — while `seestack.stackhealth` told the *same user* on the *finished
  picture* that sigma clipping "couldn't drop anything" and to re-stack with Auto outlier removal on. Two shipped
  surfaces, one fact, opposite answers.

  **The fix is a shared answer, not a second opinion** — the shape this project keeps converging on.
  `rejection_reach(options, n)` (`seestack/stack/stacker.py`) resolves `auto_reject`, asks the new public
  `combine_method` which combine the dispatcher will *actually* run, and reads the same `kappa_min_frames`
  `stackhealth` reads. A test asserts the two agree at every frame count: the form's pre-run warning and the note
  on the finished picture are now mathematically incapable of disagreeing. `combine_method` also replaced the
  fourth copy of the dispatcher's gates, in `_build_output_header_meta` — so the `STACKER` card and the form's
  warning can't name different methods either.

  **The copy now says what will happen and points at what helps**, in three shapes decided by the engine, not by
  the browser: κ-σ on but blind (*"…can't actually drop a passing satellite… a lone outlier only stands out far
  enough from the average to be clipped from about 11 frames up"*), the sub-4-frame fall-through (*"will combine
  as a plain average"*), and below min/max's own 3-frame floor, where the honest answer is that **no setting can
  help** and the button is withheld. The action is **"Turn on Auto outlier removal"** — `stackhealth`'s own
  advice, verified by a test to actually reach a lone outlier at every count from 3 up. It fires only when the
  user *asked* for rejection, so it is never a nag at someone who opted out, and it stands down while the
  streak-specific `minMaxRejectHint` is up rather than stacking a second yellow alert.

  **The old caution is kept, not deleted** — narrowed to the counts where its sentence is true (the clip really
  will bite), which at the default κ is the empty set and at a user-loosened κ=1 is frames 4. Its "Turn off sigma
  clipping" button is untouched there.

  **Upgrade-safe (§9):** one additive query param on `stack-estimate` defaulting to `StackOptions`' own
  `sigma_clip=True` (so an older frontend sees byte-identical answers), one additive response field, and the
  param provably cannot move `peak_bytes` — the only plane it gates needs `record_rejection_map`, which this dry
  run never sets, and a test pins the three peaks equal. No config, schema, on-disk, default or engine-behaviour
  change.

  **Tests: +17 engine (`tests/test_rejection_reach.py`), +2 endpoint (`tests/webapp/test_stack_estimate.py`),
  +10 unit and +4 rendered frontend.** The two existing tests that pinned the *wrong* advice were rewritten to
  pin the corrected advice on the same paths. One unrelated print-plan test was matching "2 accepted, solved
  frames" from the sigma-clip caution rather than the sizing line it was written for; it now asserts the sizing
  line's own text.
- **VALIDATION FOLLOW-UP (Scout 2026-07-23) — confirm on real nebula data that the now-live SExtractor skew
  guard (`abs(mean − median) > 0.3·σ → revert to median`) doesn't over-revert on heavy diffuse nebulosity.**
  *(Image-quality / correctness; PRIORITY 4; size S — one real-data check, no blind code change.)* The
  formerly-dead skew fallback in the four sky-mode estimators (`bg/per_frame.py` CPU L378 + GPU L469,
  `bg/final_gradient.py` L231, `bg/coverage_leveling.py` L178) is now **live** with the `0.3·σ` criterion (see the
  struck bug in "Bugs"). An earlier Builder audit flagged that a heavy diffuse nebula reads `|mean−median|/σ ≈
  0.32` on a *raw* region and could trip the 0.3 rail — but every site measures the guard on the **object-masked +
  3σ-clipped sky sample**, where the in-code note says the skew stays well inside the band, and the suite is
  green. **What's left is a confidence check, not a fix:** on a real heavy-nebulosity OSC stack (e.g. North
  America / Rosette), log per-site how often the guard fires and confirm (a) it does **not** fire on genuine
  diffuse-sky tiles (so the intended mode is kept where `final_gradient` deliberately wants it), and (b) it still
  reverts on a truly pathological skew. If it does over-revert on real nebula, raise the site-specific threshold
  (or gate it on `sc_std` magnitude). No change unless (a) fails on real data — same real-data-gating as the
  SCNR / `sky_sigma` items below.
- **NEW (Builder audit 2026-07-16) — engine-audit residue: two low-confidence, NOT-currently-reachable
  notes to keep a future audit from re-flagging them.** (XS each, image-quality/correctness — PRIORITY 4.)
  *(From two independent adversarial stacking-engine audits this run — both otherwise verified the core
  reduction/rejection/mosaic/drizzle/calibrate math correct, backed by numerical repros; the one provable bug
  they found, the non-finite dark/bias poisoning, shipped v0.135.1.)* **(1) GPU vs CPU reproject `cval`
  asymmetry** — `align.py` uses `cval=0.0` on the GPU reproject and `cval=nan` on the CPU one (~L498 vs L523).
  Confirmed *not reachable for real data*: `FRAME_EDGE_INSET_PX=3` guarantees the bilinear stencil never
  touches out-of-bounds within the valid mask for any frame ≥13 px, so GPU and CPU agree; it could only differ
  on ≤12 px synthetic frames, GPU-only. Harmless, but making both `nan` would remove the latent divergence and
  a foot-gun for future edits. **(2) `level_by_coverage` docstring imprecision** — `stacker.py` (~L1175) runs
  it unconditionally and its docstring calls the single-coverage-level case "effectively a no-op", but it
  actually subtracts a per-level sky-mode *constant* (a pedestal shift, brightness-relative-preserving, which
  is intended) — so the wording is misleading, not the behaviour. A one-line docstring correction only; judging
  whether the sky estimate itself is *good* needs real data (see the SExtractor-skew and `sky_sigma` items).
  Neither cleared the churn bar to change this run; recorded so they aren't mistaken for new findings later.
- **"How's my stack?" highlight-clip cue — needs REAL-data threshold tuning before shipping (NOT a blind
  change).** (M, image-quality/trust — PRIORITY 4) *(Builder-filed 2026-07-14, deferred slice-(b) part of the
  "How's my stack?" health check; slices (a) v0.120.0 + actionable/History (b) v0.121.0 shipped.)* The original
  health-check idea listed a "bright core is clipping — the editor's highlight rolloff will recover it" cue that
  reads the **stacked pixels** (the other cues read only stamped run fields + the frames table, so `stack_health`
  stayed pure/offline). Deferred deliberately: (1) it needs loading `master.fits` pixels, so it can't live in the
  pure `stack_health(run, frames)` helper — it must be computed webapp-side (where the master is loaded) and
  passed in as an optional pre-computed cue, and gated so it doesn't load pixels on every Target-page render;
  and (2) **detecting genuine clipping in a *linear, background-subtracted* master needs a real-data-validated
  threshold** — a saturated core shows as a flat plateau of near-max pixels, but the master's max/scale varies
  per target and the background subtraction shifts values, so any "fraction of pixels within ε of max" rule
  risks false-positives (or misses) without validating on real Seestar stacks of both a clipped bright-core
  target (e.g. M42's trapezium / M31's core) and an unclipped faint target. Same real-data gating the SCNR /
  `sky_sigma` / streak-detector items carry. When built: a conservative plateau detector (many finite pixels at
  the exact global max with ~zero local spread = saturation), a `HealthNote(kind="highlight_clip")` that is
  reassuring not alarming (the editor's v0.119.1 rolloff already recovers it in the display), and a webapp-side
  computation behind the existing endpoint. Additive; the note only ever *adds* guidance, never gates.
- **Scout to vet on REAL data: does the STF `_highlight_rolloff` (v0.119.1) mildly *desaturate* bright
  coloured highlights?** (S, image-quality — PRIORITY 4) *(Builder-audit-noted 2026-07-14, from an
  adversarial numeric audit of the v0.119.1/.2 highlight-rolloff fix — which otherwise verified clean:
  monotonic, bounded <1, C¹ at the knee, neutral saturated stars stay neutral, background bit-for-bit
  unchanged.)* The rolloff soft-shoulders each channel **independently** in that channel's own
  shadow-normalized space, so on a bright *coloured* region where some channels sit above the knee (0.7) and
  one below, only the above-knee channels are compressed while the below-knee one is untouched — which mildly
  **desaturates** the highlight. Measured on a synthetic warm core at r≈14 px: old `[0.923, 0.865, 0.806]` →
  new `[0.867, 0.846, 0.806]` (R u8 235→221, B unchanged). It only touches already-bright (>0.8) pixels, is
  a large net improvement over the old hard-clip (which blew the core to featureless white), and doesn't
  violate the code's invariant (below-knee pixels are exactly unchanged) — so it's **not** a regression to
  fix blind. But whether a **luminance-coupled** rolloff (scale all three channels by the *luminance*'s
  shoulder factor, preserving hue/sat while still taming the peak) reads better on a real bright galaxy core
  (M31/M42) is worth a real-data A/B before any change — synthetic can't judge "looks better". Testable on
  `_highlight_rolloff`/`autostretch` in isolation; additive; changing it touches the default view + Auto, so
  real-data-gated like the SCNR / `sky_sigma` items below.
  ~~**Scout to vet on REAL data: does the Auto denoise↔sharpen crossfade over-read a *sky gradient* as
  noise?**~~ — **CLOSED BY MEASUREMENT, v0.382.1** (Builder 2026-09-07). Deferred three times as
  real-data-gated; the v0.225.0 *local* `sky_sigma` estimator had already closed it by construction, and
  running the entry's own gradient ladder says so: at σ=0.003, gradient 0.00→0.05→0.10→0.20 now moves
  `sky_sigma` **0.0042→0.0039→0.0035→0.0030** (it drifts *down*, not up), `_noise_fraction` stays 0
  throughout, and Auto keeps the same sharpening with no denoise pass added — against the entry's recorded
  pre-fix 0.015→0.028→0.054→0.098, which flipped Auto to *sharpen 0.0 / full denoise* by a gradient of
  0.05. Pinned by `test_a_strong_gradient_never_costs_a_clean_stack_its_sharpening`. Entry, numbers and
  the original trace in [`SHIPPED.md`](SHIPPED.md).
- **Scout to vet on REAL data: does Auto's SCNR tint an already-neutral *background* magenta?**
  (S–M, image-quality) `tone.scnr` (`seestack/edit/ops/tone.py::_scnr`) is a one-sided clip — it
  can only ever pull green *down* toward the `0.5·(R+B)` neutral, never up. On data that already
  carries a real green cast (light pollution, OSC green bias) that's exactly right and wanted. But
  on a background that is already colour-balanced and noisy, the clip is asymmetric on the green
  *noise*: positive green excursions get clipped, negative ones are kept, so it **rectifies the
  noise and biases the background median magenta**. Auto applies it at `amount=0.8` after
  `tone.color_calibrate` (gray-star, which has already neutralised the background), so the residual
  it clips is largely noise. **Verified numerically (Builder dogfood 2026-07-08, no change shipped):**
  on a perfectly neutral background (R=G=B=0.30, independent σ=0.03 per-channel noise), `_scnr(amount=0.8)`
  shifts the green median −0.010 and the mean −0.012 (≈0.34σ) — R/B untouched — i.e. a faint magenta
  cast. In the full stack→Auto→export dogfood (realistic 1920×1080 12-sub dithered stack) the export's
  background medians came out R/G/B **0.243 / 0.209 / 0.243** (green ~14% low); a prior audit note
  recorded the same signature (0.196 / 0.174 / 0.196) and read it as "balanced", so this has been live
  and accepted for a while. **Why it's a Scout/real-data item, not a headless Builder change:** it
  touches the most-used one-click Auto path, and whether the clip is a net win depends entirely on how
  much *real* green cast a genuine Seestar background carries (which a headless synthetic can't stand in
  for) — same reasoning as the `sky_sigma` item above. If it reproduces on real neutral-background OSC
  stacks, candidate mitigations to weigh: lower Auto's SCNR `amount`; or protect the background (only apply
  SCNR where signal is above a sky-relative threshold, so the noise floor isn't rectified); or run SCNR
  on the post-denoise image only. Each must be validated so a real green-cast stack still gets its cast
  removed. Testable on `_scnr` / `auto_recipe` in isolation; additive.
  _(Builder dogfood 2026-07-09, v0.99.2 baseline — re-confirmed the artifact and, more usefully, gathered
  a new data point that leans the disposition toward "leave Auto's SCNR as-is." Two synthetic runs through
  the real `auto_recipe`→`apply_recipe` chain: **(1) truly-neutral noisy sky** (R=G=B=0.168 after STF
  stretch, no cast) → `_scnr(amount=0.7)` drops the sky green median 0.168→0.145 (**−14%, a visible magenta
  tint**) while leaving R/B untouched — the pure one-sided-clip-rectifies-noise mechanism, exactly as filed.
  **(2) A green-cast sky** (OSC green bias + gradient), full Auto chain **with vs. without** the SCNR op,
  measured on the background population: *without* SCNR the sky keeps a residual **green excess** (G 0.145 vs
  R/B ~0.127, i.e. +0.017 green) — i.e. `tone.color_calibrate` (gray-star) balances on the *stars* and
  leaves the *diffuse background* green cast **in place**; *with* SCNR the background lands near-neutral
  (G 0.168 vs the 0.172 R/B neutral, only −0.004 magenta). So on a background that carries any real residual
  cast — which post-gray-star OSC backgrounds typically do — SCNR is a **net win** (removes a +0.017 green
  excess for a −0.004 magenta overshoot), and the −14% magenta failure mode needs a background that is
  *already truly neutral*, which gray-star does **not** produce on cast data. This strengthens the existing
  "net value depends on real cast magnitude" reasoning with direct evidence that the common case is
  net-positive, so the safest read is still: **don't blind-change the most-used Auto path**; if a future
  agent does touch it, prefer a **noise-symmetric** mitigation (a soft-clip whose transition width tracks
  the measured background green-noise σ — removes a genuine cast ≫σ as fully as the hard clip while not
  rectifying within-noise excursions) over uniformly lowering `amount` (which would under-remove real
  casts), and gate on a real neutral-vs-cast OSC background sample. No change shipped — the deferral holds.)_
  **▶ THE SAMPLE THIS IS GATED ON IS ALREADY BEING COLLECTED — read it before deferring again (Builder
  2026-09-07).** Every unattended auto-edit stamps the finished picture's residual background cast
  (`editor_auto_skycast:{run_id}`), and `GET /api/auto-cast-summary` reports the neutral/cast split, the
  counts **by dominant tint** and the median deviation across the owner's real runs. That is precisely the
  neutral-vs-cast OSC background sample the deferral asks for: a magenta-dominated `by_cast` on real data is
  the evidence for this entry, and a green-dominated or neutral one is the evidence against it. So the next
  run to pick this up should **read that endpoint's answer on the live install first** rather than measuring
  another synthetic — and still not blind-change the most-used Auto path.
- First-class session/night dimension in the project schema (frames only have
  `timestamp_utc`): per-session sky levelling before combine, per-session
  calibration binding, per-night QC roll-ups. Coverage-levelling's docstring
  already names "between sessions" as motivation but keys on coverage count.
  Large but high value for the multi-night Seestar workflow. (L, correctness)
- **Root-cause fix for the streak/edge-on-galaxy false positive: make the streak detector distinguish a
  trail from a stationary object *per frame* (needs REAL data to tune — NOT a blind change).** (M,
  image-quality/autonomy — PRIORITY 4) *(Builder-filed 2026-07-10, follow-up to the v0.106.2 population
  guardrail.)* v0.106.2 stopped the *catastrophic* case (a bright edge-on galaxy / elongated nebula flagged as a
  "streak" on a majority of subs → whole-target auto-reject) with a safe population rail
  (`qc/runner.py::reconcile_streak_rejections`: re-accept when >½ the target is auto:streak). That's a symptom
  guard: a bright galaxy that flags on only a *minority* of subs (the best-seeing ones) still gets those subs
  wrongly rejected, under the rail. The real fix is to teach `qc/streaks.py::detect_streaks` to tell a transient
  trail from a stationary extended object *on a single frame*. Candidate signals: **absolute minor-axis
  thinness** (a satellite/plane trail is ~1–3 px wide near the PSF; a galaxy core is many px thick, so require a
  small `axis_minor_length` in addition to the elongation ratio); **straightness/fill** (a trail is a near-perfect
  straight ridge — a high Hough-line-length ÷ component-length ratio — while a galaxy's disk is fatter and
  curved); or **cross-frame persistence** (a component at the same sky position across subs is stationary, i.e.
  the target, not a trail — the strongest discriminator but needs the frames' WCS/registration, so it's a bigger
  change). **Why real-data-gated:** any threshold that excludes galaxies risks also missing genuine (thin, faint)
  trails, so it must be tuned/validated on **real** Seestar subs of both an edge-on galaxy *and* a real satellite
  trail before shipping — a synthetic can't stand in for the true width/brightness/straightness distributions.
  Additive, testable on `detect_streaks` in isolation; keep the v0.106.2 rail as the belt-and-braces backstop
  even after the detector improves.

### Features that serve real workflows

- ~~**🌟 NEW BEGINNER FEATURE (Scout 2026-09-25) — "Was the moon out?": a retrospective moon note on a
  session.**~~ — **⚪ CLOSED: ALREADY BUILT, END TO END. Do not pick it up** *(Builder 2026-09-25, grepped and
  read before starting it — it was the freshest entry in this section and the run's first candidate).* The
  premise ("the app's moon machinery is all forward-looking; nothing explains a night already shot") is not the
  live behaviour, and has not been since `SessionMoon` shipped. **What exists, in the entry's own terms:**
  `seestack/nightplan.py::session_moon` / `session_moons` — a *retrospective* verdict at the session's
  midpoint, graded through the same `_moon_verdict` the forward-looking readout uses, with
  `_session_moon_text` writing the finished sentence (*"A bright 96 %-lit Moon was only ~21° from this target
  while you were shooting… That's the sky, not your setup"*); `webapp/routers/targets.py::_session_moon_note`
  puts it on the "Last night" card as `SessionRecapOut.moon_note`
  (`frontend/src/components/SessionRecapCard.tsx`), and `_night_moons` → `NightSummaryOut.moon` puts it on
  **every** night of the Nights card (`NightsCard.tsx::moonTooltip`). Offline, self-hiding, one ephemeris pass
  for the whole table, and covered by `tests/test_session_moon.py`, `tests/webapp/test_target_nights.py`,
  `tests/webapp/test_target_session_recap.py`, `NightsCard.test.tsx` and `SessionRecapCard.test.tsx`.
  **It is also *better* than the entry's shape on the one point that matters, so do not "improve" it back:**
  the entry proposes firing on illumination + altitude, and the shipped verdict also requires the Moon to be
  **close to the target** — a 90 %-lit Moon 150° away across the sky is not why that night was bright.
  **The one piece of the entry that is genuinely not built is its shape note (2), the two-stage degrade on a
  site-less install ("you can still say the Moon was 87 % lit"), and it is DECLINED on the shipped design's own
  reasoning:** without a site you know neither *up* nor *close*, so the only sentence you could write is one
  that may be describing a Moon that never rose — which is exactly the nag `SessionMoon`'s "quiet by design"
  contract exists to prevent. Re-open only with a shape that does not guess at the two missing facts.
  **The gap.** `seestack/nightplan.py` already computes the Moon fully **offline** — `moon_illumination(when_utc)`,
  `moon_is_waxing`, `_moon_altitudes(stamps, location)`, `moon_window` — but only for **tonight/future** planning
  ("shoot this near new moon"). A beginner staring at a grainy stack has no way to learn that the sky was bright
  *because the Moon was 87 % lit and 40° up that night*. The app's own session-recap even lists "Cloud, haze or
  **moonlight**" as a reject cause (`webapp/rejection_summary`, `session_recap`) — but it is a guess from star
  counts; it never actually checks where the Moon was, because it can't per-session today.
  **The feature.** For each capture **session/night** of a target, take the session's median `timestamp_utc`
  (frames already carry it) and the install's site (`Settings.site_lat`/`site_lon`), and compute the Moon's
  illuminated fraction and altitude at that time with the *existing* nightplan helpers. Surface a one-line,
  self-hiding note where a beginner already looks at a night — the session recap / Nights card / the frames
  table's per-night group — e.g. *"A bright night: the Moon was 87 % lit and 40° up. That lifts the sky and
  adds noise — this target will come out cleaner shot within a few days of new moon."* Say nothing when the
  Moon was **down or near-new** at that session (the common good case), so it is signal, not clutter.
  **Why it clears the bar and the guardrails.** Offline (no network, §1 standing policy; no new dependency —
  the ephemeris is already in the tree), additive (one computed response field + one card, everything else
  unchanged), upgrade-safe (§9: no config/schema/on-disk/default change; a site-less install simply omits the
  note, exactly as Tonight already degrades — see the v0.436.1 dogfood note about the empty-site state), and
  testable in isolation on the pure nightplan functions plus a session-grouping helper. It also **closes the
  loop on the rejection-cause guess**: where `session_recap` says "likely moonlight", this can confirm or deny
  it from geometry rather than star counts.
  **Shape notes for the Builder.** (1) Per-*session* grouping is the one new primitive — reuse whatever the
  Nights card / `session_recap` / `stacktime.py` already use to split a target's frames by night, don't invent a
  second definition. (2) Altitude needs the site; illumination does **not** (`moon_illumination` is
  location-independent), so on a site-less install you can still say "the Moon was 87 % lit" and just drop the
  "and 40° up" clause — a graceful two-stage degrade rather than all-or-nothing. (3) Keep the threshold for
  "worth mentioning" honest: mention only when illumination **and** altitude were both high enough to matter
  (a 90 %-lit Moon that never rose is not why the night was bright); pick the bar against the owner's own nights
  if a later run has the observer's distribution, else a conservative default (e.g. illum ≥ 0.5 and median
  altitude ≥ 20°) that a comment marks as provisional. (4) It is a **note, never an action** — like
  `new-subs-waiting` it explains and links, it never re-stacks.

*(The Scout's 2026-09-09 "shareable labelled picture" entry shipped as v0.407.0 and was cut to
[`SHIPPED.md`](SHIPPED.md) — the engine render and the endpoint flag already existed; only the download was
missing. Don't re-file it.)*

*(The Scout's 2026-09-12 "draw the full Moon to scale" entry shipped as v0.432.0 and was cut to
[`SHIPPED.md`](SHIPPED.md) — `ScaleBar.moon_fraction` + `skymarks._moon_disc_box` + `frontend/src/moonDisc.ts`,
off by default. Don't re-file it.)*

- ~~**🌟 NEW BEGINNER FEATURE (Scout 2026-09-17) — a ready-to-paste, copy-to-clipboard caption for a shared
  picture.**~~ — **✅ MOSTLY ALREADY BUILT; the one genuinely missing half shipped as v0.451.0. Entry cut to
  [`SHIPPED.md`](SHIPPED.md); do not re-pick it.** *(Builder 2026-09-17, grepped before building.)* "Copy
  caption" has existed since **v0.385.0** (`frontend/src/components/postCaption.ts`, in `SavePictureMenu` on the
  Target hero and every History run card), already carrying identity, subs, integration, capture window, nights
  and scale bar, degrading exactly as the entry asks; the entry's grep had landed on `sharePictureText`, the OS
  share sheet's title/filename helper. What was missing was the entry's middle term — *what the object is* — and
  v0.451.0 tells the catalogue's own sentence (`ObjectInfo.blurb`, 157/157 bundled objects) in place of the bare
  type word. One piece is still open: the lead below.

- ~~**LEAD (Builder 2026-09-17, the one piece of the caption entry above that is still open) — the Gallery
  lightbox shares a picture with the thin `sharePictureText` caption, not the ready-to-post one.**~~ —
  **✅ SHIPPED v0.453.0** (Builder 2026-09-17), built as the lead's own shape **(a)**. Entry cut to
  [`SHIPPED.md`](SHIPPED.md), one-liner under "Shipped" below. Two things the lead had not checked and the
  build did: the viewer **already** fetches the annotations when a picture opens (for the North-up offer), so
  the scale datum was in hand all along and the gate was only ever the run's *geometry*; and the three fields
  are now served by one shared `preview_orient.preview_geometry_out` that the run listing uses too, so the
  page that draws the picture and the page that captions it cannot describe it differently.

- **NEXT SLICES of the "finished / not stretched / thin" card signal — the Library wall shipped as v0.448.0;
  three pieces are left.** *(Scout 2026-09-16, first slice built by the Builder the same day. Pillar:
  understand + trust — PRIORITY 3; each S. Beginner bar: yes — the shipped half is proof.)*
  **What shipped:** `GET /api/unstretched-pictures` (`webapp/routers/unstretched.py`) names every target whose
  *displayed* picture is a flat linear stack, and `Library.tsx` badges those cards "Not stretched yet" with a
  plain-language `title`. "Finished" is one shared definition, `webapp/finishedpicture.py`
  (`displayed_picture_run` + `run_is_a_finished_picture`), the same two functions v0.447.2's reprocess warning
  counts with; a test asserts the two partition a library exactly. **One deliberate change of shape from the
  idea as filed: it chips only the cards that need something, never "Finished"** — a chip on the nine in ten
  that are fine is a wall of badges saying nothing, and clutter is the owner's standing complaint (AGENTS.md
  §1). Don't re-file that half. Full entry in [`SHIPPED.md`](SHIPPED.md).
  (a) ~~**The same chip on Gallery cards**~~ — **✅ SHIPPED v0.448.2, and NOT off the same query.** The slice as
  filed said "`Gallery.tsx` reading the same query", and that would have been wrong: `/api/unstretched-pictures`
  answers per **target**, about the one run it displays, while the Gallery lists **every run of every target** —
  so it would have badged each target's displayed run and said nothing at all about the older linear runs beside
  it, on the page whose whole job is looking at pictures. It is instead a per-run `GalleryItem.finished`, off a
  new `finishedpicture.run_is_a_finished_picture_from` that takes the recipe row `_gallery_item` had already read
  for `unexported_edit` (so the field costs no extra DB read on the one endpoint whose meta reads are counted);
  the `proj`-taking form is now a wrapper over it, and a test asserts the two can never answer differently.
  Shared copy moved to `frontend/src/unstretched.ts` + `components/UnstretchedBadge.tsx`.
  (b) ~~**The idea's optional "Thin — keep shooting" state.**~~ — **✅ SHIPPED v0.450.0**, and its "check what
  the Target page already says" is what decided the shape: the sentence is not new copy at all, it is
  `thinStackWarning`'s own — the function the Gallery card's orange frame badge already asks — given the two
  numbers it names on a mosaic (`n_frames_used` + `field_fulls`, off `derived_light.stacking_field_fulls` so a
  finished picture's crop cannot read as depth). Depth takes the card's one chip slot when a card is both,
  because "press Auto" cannot make a one-sub stack anything but a stretched one-sub stack. Entry in
  [`SHIPPED.md`](SHIPPED.md).
  (c) ~~**A one-click deep link from the chip to that run's Auto**~~ — **✅ BOTH HALVES NOW DONE: answered on the
  Gallery (v0.448.2) without building it, and shipped on the Library card as v0.471.0.** On a Gallery card the one
  click already existed: an **Edit image** button straight to `/targets/<safe>/edit/<run_id>`, which since v0.390.0
  opens *on* Auto rather than on a nudge to press it. So that chip's hint names that button instead, and a second
  link to the same place was declined as exactly the duplicate surface the owner's standing clutter complaint is
  about. **The Library half's two stated blockers turned out to be one, and it was already solved:** the run id is
  indeed not on `TargetOut`, but the wall does not read the chip off `TargetOut` — it reads
  `/api/unstretched-pictures`, whose `UnstretchedItem.run_id` has carried exactly the run
  `displayed_picture_run` picked since v0.448.0, so nothing new travels on the wire. And the card did not need
  restructuring: the chip is a `<button>` inside the card's `<Link>` that stops its own click, the shape
  `WishlistStar` already uses for a control sitting on a picture tile — so the chip goes to the editor and every
  other part of the card still goes to the target. Entry in [`SHIPPED.md`](SHIPPED.md).

- **NEW IDEA (Builder 2026-08-29, the two halves deliberately left out of "See what stacking removed"
  v0.299.0) — put the overlay where people actually *look* at a picture, and count what it removed.**
  *(Pillar: trust + understand — PRIORITY 3; both small, both purely additive on machinery that now exists.)*
  (a) ~~**The Gallery lightbox and the Target hero.**~~ — **✅ SHIPPED v0.312.0** (Builder 2026-08-30, branch
  `claude/compassionate-galileo-6jgh4j`), on both surfaces, with the entry's "ship the gate before the feature"
  taken seriously and then found to be **unnecessary** — which is the design call worth carrying forward.

  **The stand-down the entry demanded doesn't apply here, and checking that first is what kept this small.**
  The History card has to withdraw the tint because *its* picture can become something else: opening **Adjust**
  swaps in a live render of the linear master at full canvas, which the tint was never measured against. Neither
  of these two surfaces has such a state — both show the **stored preview bytes** and nothing else, and the one
  variation they do offer (the v0.308.0 North-up *view*) is a turn the overlay endpoint already composes, since
  v0.308.2, from the same `preview_north_up_remainder_deg` the picture itself goes through. So the tint follows
  the picture instead of standing aside, and a test on each surface pins that both URLs pick up `north_up=true`
  together. The share JPEG and the full-res PNG the entry worried about are **downloads**, not what the viewer
  draws.

  **The one real piece of work was the geometry, and it is a CSS trap worth recording.** `ImageLightbox` fits its
  picture with `max-width/max-height: 100%` inside a flex-centred surface and then applies the zoom/pan transform
  to the `<img>` itself. Wrapping the picture and the overlay in a shared positioned box — the obvious way to
  make two images move together — makes the picture's `max-height: 100%` resolve against an **auto-height**
  ancestor, i.e. indefinite, i.e. no cap, and a tall picture then overflows the viewer. The overlay is therefore
  a **sibling**, absolutely positioned with `inset: 0` + `margin: auto` (which centres a replaced element on
  exactly the box `align-items/justify-content: center` puts the picture in), sharing one `imgFit` object and one
  `transform` string with the picture so the two cannot be fitted or moved differently. A test asserts the fitted
  style *and* the transform are byte-identical on both elements, **after a zoom** — the case a separately-computed
  transform would silently get wrong.

  **The gate, and what it cost.** The Target hero needed no new request: `StackRun.has_rejection_map` is already
  on the run it draws. The Gallery drew its cards from `/api/gallery`, which didn't carry the fact — so
  `GalleryItem` gained `has_rejection_map`, computed by the *same* one-line stat beside the
  `has_fits`/`has_preview`/`has_tiff` sweep the item already does (additive, `False` default), rather than a
  per-picture run-info fetch on every lightbox open. That matters because `record_rejection_map` is **off by
  default**: on an ordinary library the control is simply absent, and opening a picture costs nothing extra. The
  run-info fetch that supplies the caption's measured fraction happens only once the tint is actually switched
  on, and the caption's lead sentence never depends on it — an uncaptioned cyan speckle reads as damage, so it is
  captioned even when the number can't be read.

  `removedOverlayCaption` moved out of `routes/History.tsx` into a shared `frontend/src/removed.ts` (the
  `fullres.ts` pattern: one place owns the wording so three surfaces can't drift into three claims about one
  picture), re-exported from History so its existing readers are untouched. The toggle itself is a shared
  `ShowRemovedToggle`, so the two lightboxes offer the identical control.

  **Upgrade-safe (§9):** one additive, defaulted response field; no config, schema, on-disk or default change;
  an older frontend ignores the field and an older backend omitting it reads as "no overlay for this one", which
  is the right answer for every run that never recorded a map.

  **Tests (+12):** 5 in `ImageLightbox.test.tsx` (no overlay unless given; decorative — `aria-hidden`, empty
  `alt`, `pointer-events: none` so it can't eat a drag; identical fit *and* transform at 100 % and after a zoom;
  the caption shown, and not shown when there are no marks), 4 in `LatestPictureCard.test.tsx` and 2 in
  `Gallery.test.tsx` (nothing offered and nothing fetched on a run with no map; the tint and the measured caption
  on request; the tint turning with the picture; and — hero — the caption still appearing when the run-info
  fetch fails), and 1 in `tests/webapp/test_rejection_overlay.py` asserting the Gallery listing's answer both
  ways *and* that it agrees with the run listing's on the same run.
  (b) **"N spots", instead of a percentage (S–M, engine + one response field).** The caption today reuses the
  run's `REJFRAC` — *"that was about 0.4% of your samples"* — because that number already exists. What the
  Scout's entry actually asked for is more human: *"stacking removed 14 streaks and hot spots"*. That needs a
  connected-component pass over the `_rejected.fits` map (scipy's `ndimage.label`, already a dependency), with
  a minimum blob size so the noise-tail speckle isn't counted as 8,000 "spots" — which is the whole difficulty,
  and the reason it was left out rather than guessed at. Compute it **once, at write time**, into a header card
  beside `REJMAP` (not per-request over a canvas-sized file), and surface it on the run-info the caption already
  reads. Measure the threshold against a real map before picking it.

  **⚠️ MEASURED AND STOOD DOWN (Builder 2026-08-30, branch `claude/compassionate-galileo-6jgh4j`) — do NOT
  build this from the summed map; the threshold this entry asks for does not exist.** I did exactly what it
  demanded — measured against real `run_stack` output before picking anything — and the measurement closes the
  idea rather than sizing it.

  **What a blob count actually reads on real maps.** Connected components (8-connectivity) over the planted
  satellite-trail scene at 16 subs: **1,296 blobs**, of which the trail is one (1,453 px). The *same scene with
  no trail at all*: **1,323 blobs**. So counting blobs would tell a user with a perfectly clean night that
  stacking removed 1,323 things. A minimum area does separate them at 16 subs — the largest pure-noise blob was
  4 px against the trail's 1,453, and area ≥ 5 px gives **1 blob on the trail scene and 0 on the clean one**.

  **And that separation dies with the sub count, which is the killer.** A pixel is marked if it lost a sample in
  *any* frame, so the map densifies: non-empty share **1.9 % at 16 subs → 11.5 % at 32 → 31.2 % at 64**, and
  blobs of ≥ 5 px go **1 → 532 → 2,013**, all noise, with the trail starting to percolate into the speckle
  (largest blob 1,453 → 2,762 px). Extrapolated to the owner's 500–800-sub stacks the map is effectively
  saturated and the honest count is a five-figure number. **No minimum area works across the sub counts this app
  is for**, because the discriminator the entry assumes — a mark is dense, noise is sparse — is a property of the
  *per-frame* rejection, and the summed map has thrown it away: a satellite crossing one sub contributes a drop
  count of **1** along its path, pointwise indistinguishable from a noise-tail clip.

  **If anyone ever wants this, the only honest shape is to count it where the information still exists** — at
  combine time, per frame, before the counts are summed — which is a change inside the memory-bounded hot path,
  not "a connected-component pass over the sibling". That is an L with real OOM risk, for a caption tweak. **The
  percentage stays.**

  **The measurement was not wasted:** applied to the *tint* rather than to a count it found a real bug — the
  overlay washed the whole picture cyan on exactly these dense maps — fixed as **v0.312.1**, at the top of
  "Bugs (fix these first)".

- **NEW IDEA (Builder 2026-08-29, the follow-ups deliberately left out of "Your universe" v0.296.0) — "fly to
  it", and tell the reader what they're looking at.** *(Pillar: enjoy + understand — PRIORITY 3; size S each;
  frontend-only, no new data.)* Three cheap taps on the shipped page, in value order:
  (a) ~~**Fly to this object.**~~ — **✅ SHIPPED v0.302.0** (Builder 2026-08-30, branch
  `claude/compassionate-galileo-lcagow`), with the filed caution honoured exactly: OrbitControls' target stays
  at the origin and only the camera position moves. The trick that makes those two compatible is that the
  destination sits on the object's **own radial line**, just outside it (`flyToCameraPosition` in
  `sky/universe.ts`) — with the object *between* camera and origin, looking at the origin frames it dead
  centre anyway. A `<FlyTo>` component eases the camera there (a fixed fraction of the remaining gap per
  second, `delta` clamped so a backgrounded tab doesn't teleport on its first frame back) and stands down the
  instant someone grabs the controls. The controls' own `update()` runs at frame priority **-1**, i.e. before
  this write, so they follow the camera rather than fight it; the destination is clamped to their own
  `min`/`maxDistance` so the arrival can't visibly snap.
  **Tests (5, in `sky/universe.test.ts`):** the destination is on the object's line and outside it; the
  camera-past-object property on an off-axis object (a unit-dot check, not just an axis case); every placed
  depth **and** both extremes land inside the orbit limits; a degenerate/non-finite position declines with
  `null` rather than flying to NaN; and a further object really does end up further out. The `<FlyTo>`
  component itself is untested, like the rest of the WebGL scene — the maths it runs on is not.
  (b) ~~**The blurb is already there.**~~ — **✅ SHIPPED v0.302.0** (Builder 2026-08-30, branch
  `claude/compassionate-galileo-lcagow`), exactly as filed and at the filed size. `UniverseObject` gained a
  `blurb: str = ""` carried straight off `identify_object`'s `ObjectInfo.blurb` (grepped first — the lookup
  already loads it), `UniverseObjectOut` an additive field defaulting to `""`, and the object card one
  `<Text>` rendered only when the sentence is non-empty. So the read-out is now *about the object* rather
  than two numbers about something the reader may not recognise. **Tests:** three in
  `tests/test_universemap.py` (the blurb travels; a catalog entry without one yields `""`, never `None`, so
  no read site needs a guard; and — the measurement, not an assumption — the **real bundled catalog** does
  carry blurbs for the popular targets), one in `tests/webapp/test_sky_universe.py` pinning the field on the
  response, and two in `Universe.test.tsx` (shown when present; nothing at all for `""` *and* for a missing
  field, so an older backend degrades cleanly).
    *(Original spec: `CatalogObject.blurb` — the plain-language "what am I looking at?" one-liner the object
    card on the Target page already shows — is loaded by `identify_object` and simply not carried onto
    `UniverseObjectOut`. One additive field and one `<Text>`. **Grep first**, don't re-derive the lookup.)*
  (c) **Constellation lines at the backdrop radius.** The star backdrop is a bare point cloud at r=420; the
  offline Sky viewer's recognisable-star labelling is the precedent. Only worth it if a constellation-line
  dataset is already bundled — check before scoping, and do **not** add one as a dependency for this.

- **NEW IDEA (Builder 2026-08-06, same run) — a beginner can crop the Moon, but there is no way to crop anything
  else.** *(Friendliness — PRIORITY 3; size M; **think before building**.)* The framing crop is disk-shaped by
  design (`measure_framing` finds "the one bright thing"), which is right for the Moon and Sun and useless for a
  deep-sky stack — where the framing problem is different anyway (ragged dithered borders, already handled by
  `auto_crop_border`). Filing it only so a future run doesn't read "crop" as a generic gap and build a manual
  crop tool for the editor: that would be pro tooling by the §1 bar unless it answers a beginner question the app
  doesn't already answer. Probably **not** worth building; recorded so it can be declined once rather than
  re-litigated.
  **⚠ Read this alongside v0.379.0, which is NOT what this entry declined (added 2026-09-07 by the run that
  shipped it).** v0.379.0 added no crop *tool*: `geometry.crop` was already in the registry and already in the
  Add menu, and all that shipped was a way to *aim* it — a draggable rectangle over the preview, replacing four
  typed fractions. That is the "make the controls obvious" half of priority 1, not new surface. **What this entry
  still declines stands:** a *disk-shaped* / subject-finding crop for deep-sky, and any new expert framing
  tooling. Don't build either; and don't read v0.379.0 as re-opening this.

- **NEW IDEA (Builder 2026-08-04, follow-on to the v0.229.0 `.zip` upload) — unpack a big archive as a *job*
  rather than inside the request.** *(Autonomy/friendliness — PRIORITY 2–3; size M.)* The zip upload streams to
  disk and then unpacks **synchronously inside the POST**, so a multi-GB night is a long silent wait after the
  browser's progress bar has already hit 100 % (the card does say "Uploaded — processing on the server…", which is
  honest, but it's a blind wait) — and on a slow NAS it could out-live a reverse proxy's request timeout, which
  would read to the user as a failed upload even though every sub landed. **Slice:** keep the streaming-to-`.part`
  half in the request (that's the part the progress bar measures), then hand the temp archive to the existing
  single-worker `JobManager` and return `{job_id}` immediately; the job unpacks, reports per-member outcomes as
  job text, deletes the archive, and kicks the usual scan. The Jobs page then shows real progress instead of a
  stalled bar. **Care:** the temp `.part` must be cleaned up by the job on *every* path (including cancel), and the
  response shape must stay backward-compatible — an older frontend reads `saved`/`skipped`/`rejected`, so either
  keep unpacking inline below a size threshold or return an empty-but-valid summary plus the job id. Worth doing
  only once someone actually uploads a big archive; a few hundred MB unpacks in seconds today.

- ~~**NEW IDEA (Builder 2026-07-25) — plateaued target nudges "shoot something fresh".**~~ **✅ SHIPPED
  v0.425.0** — full body cut to the Shipped one-liner below (three-file rule); `IntegrationTrendBadge` now
  names the planner's best fresh pick under the plateau verdict.

- ~~**Data-driven target difficulty** (optional `mag`/surface-brightness in the catalog instead of the curated
  table).~~ **⚪ CLOSED — measured at zero, do not build** (Builder 2026-09-07; full write-up moved to
  [`SHIPPED.md`](SHIPPED.md), search "data-driven target difficulty"). The gap it fills is empty: 157/157 bundled
  objects already get a verdict from `_CURATED` + the cluster type-rule, pinned by
  `tests/test_target_difficulty.py::test_the_bundled_catalog_is_covered_end_to_end_today`. Reopen only with a real
  magnitude source, never from recall.
- **NEW (Builder 2026-07-21, follow-up to shipped "Set as cover" v0.145.0) — let the cover also be an *edited*
  export, not only a raw stack run.** v0.145.0 pins a **`stack_runs` row** as the target's cover (`cover_stack_run_id`
  resolved through the run's `preview_path`). But the #7 spec's motivating case — "a beginner who *edited* a stack
  into a lovely picture" — isn't fully served: an editor export is **not** a `stack_runs` row, so an edited picture
  can't be pinned yet. **Idea:** extend the cover to accept an edited result. Two shapes to weigh: (a) when the
  editor exports/saves, record the edited render as its own light-weight "result" the cover can point at (a new
  nullable `cover_preview_path` alongside `cover_stack_run_id`, set directly to the edited PNG — the thumbnail
  resolver already falls back gracefully if the file is gone); or (b) have the editor "Save as preview" flow (which
  already re-renders a run's `preview_path`) offer a "★ Set as cover" in the same step, so the *edited* pixels
  become the pinned run's preview and the existing run-id cover just works. (b) reuses everything already shipped and
  needs no new column — likely the smaller, safer slice. Beginner bar ✔ (same one-button affordance, extended to the
  place a beginner most wants it — their finished edit). Additive/upgrade-safe (nullable/new surface, off by default).
  _(S–M; PRIORITY 3 friendliness / enjoy-share — completes the "pin my favourite picture" story for edited results.)_
  **⚠ Builder note (2026-08-05, `claude/relaxed-turing-iv0w1h`) — MOSTLY MOOT; verify before starting.** The
  editor's **Apply & save** path (`submit_editor_export` → `_apply_editor_to_run`) does not produce a loose PNG: it
  records the edited result as a **real `stack_runs` row** of its own (`notes="edited"`, its own `preview_path`), so
  an edited picture *can* already be pinned with the existing v0.145.0 "Set as cover" button on that run's History
  card. What is left is only the narrower case of an editor **download/share** export (PNG/JPEG, no run recorded) —
  shape (a) — and the shortcut of offering "★ Set as cover" inside the export step rather than one click later on
  History. Both are marginal against the shipped path, so this is **deprioritised**; don't rebuild the covered part.
- **NEW (Builder 2026-07-21, follow-up to "Your sky, so far" v0.142.0) — add the "clearest night" stat + a
  compose-to-one-image share button.** The v0.142.0 first slice is registry-only, so it omits two nice-to-haves from
  the original idea: **(a)** a "your clearest night" tally (best median FWHM / lowest sky background) — needs a
  per-target frame read (open each `project.sqlite`), so add it as a *separately-cached* enrichment behind the same
  endpoint (or a sibling `?deep=1`), guarded so it never opens every project on a hot render; **(b)** a single
  **"Share this summary"** button that composes the tallies + hero grid into one social-ready PNG, reusing the
  existing share-card/PNG export path (`seestack/sharecard.py`) so the whole "year in review" can go out as one
  image. Both additive/read-only. *(S–M each, friendliness/enjoy-share — PRIORITY 3.)*
  **▶ BOTH SLICES ARE NOW DONE — (b) was already shipped, (a) SHIPPED v0.268.2** (Builder 2026-08-18, branch
  `claude/relaxed-franklin-i98kvb`).
  **(b), verified in the code rather than assumed:** `GET /api/recap.jpg` (`webapp/routers/stats.py`) already
  rendered exactly the filed idea — the recap's own figures drawn over the user's best picture by
  `seestack.recap.draw_recap_poster`, downloaded as `my-sky-so-far.jpg`, with `GET /api/recap` serving the same
  numbers plus a copy-paste caption, and nothing written to the library.
  **(a) "your best night", shipped — and the entry's own caution ("needs a per-target frame read… guard it so it
  never opens every project on a hot render") is answered by not adding a walk at all.** The trick is that
  `/api/activity-calendar` **already** opens every project and reads every accepted frame row for the Dashboard
  heatmap, behind an app-level cache. So the star size rides along as an **optional 4th element** of the tuples
  the webapp already streams into `accumulate_nights` — same walk, same cache, no second pass and no new
  endpoint. Every existing 3-tuple caller folds byte-for-byte as before.
  **What it says.** A new self-hiding card on "Your sky, so far": *"Your best night · 12 Jan 2026 — 2.4 px
  stars — Your steadiest sky yet on M 42 — 1.5 h captured, 180 subs measured."* It is the first thing on that
  page that **ranks** a night rather than adding it up, which is the question a beginner actually asks after a
  few sessions. It ranks by **median star size in pixels** — the same measure the session recap's sharp/soft
  verdict and the Target page's Nights card already use, so the app speaks in one voice rather than inventing a
  second definition of "a good night". (Sky background, the entry's other suggestion, was deliberately left out:
  it tracks the Moon and light pollution as much as the night, so "lowest sky" would rank a new-Moon night above
  a genuinely steadier one.)
  **Honest by construction, silent rather than wrong** (`seestack/activity_calendar.py::sharpest_night`): a night
  needs `SHARPEST_MIN_MEASURED` (5) measured subs to qualify — a one-frame median describes the frame, not the
  night — and at least `SHARPEST_MIN_NIGHTS` (2) nights must qualify, because naming the best of one is not a
  fact about the sky. A failed measurement stored as 0, a negative or a NaN is not counted as a measurement (a
  fabricated 0 px would win every comparison). Ties break on the earlier date. Only nights inside the window are
  considered, so a brilliant night two years ago isn't "your best night" on a 12-month page.
  **Upgrade-safe:** additive optional response fields (`median_fwhm_px`, `n_measured`, `sharpest_night`) on an
  existing endpoint; the frontend types them optional and the card renders **nothing** against a backend that
  doesn't send them, so old/new mix in either direction. No config, DB-schema, on-disk or default change, and no
  new endpoint. **Verified in a real browser as well as jsdom** (`scripts/agent-dogfood.sh` + a probe that serves
  the card a sharpest night): it renders inside the viewport at 1440 px **and** 420 px with no console errors.
  **Tests (+21):** `tests/test_activity_calendar.py` (+8 — the sharpest night is the smallest-star one, a thinly
  measured night can't win, silence on one qualifying night, silence with nothing measured, unmeasurable values
  aren't counted, 3-tuple callers fold exactly as before, ties break earlier, and the window is respected),
  `tests/webapp/test_activity_calendar.py` (+3 — per-night medians on the wire, silence without measurements,
  and the sharpest night serialised whole), `bestNight.test.ts` (+5) and `BestNightCard.test.tsx` (+4 — named,
  silent on null, silent against an older backend, silent on a failed fetch), plus `SkySoFar.test.tsx` (+1 —
  the card is on the page).

### UX & polish
- Mobile layout polish across the newer pages (Calibration, Combine). (S)
- Better empty-states and error messages on long-running jobs. (S)

### Performance (only with a measurement)

- **LEAD, MEASURED (Builder 2026-09-07, the residue v0.374.8 deliberately left) — `/stack-estimate` and
  `/rejection-outlook` are still **~4.7 s** on the owner's 5,477-sub target, and it is now *all*
  `wcs_from_text`.** *(Pillar: friendliness / performance — PRIORITY 3; size M; **do not blind-pick either
  option below**.)*

  **▶ SHAPE (a) IS SHIPPED — v0.374.9, `wcs_io._wcs_from_plain_tan_text`. Shapes (b), (c) and (d) are still
  open; read their care notes below before picking one.** Measured on this entry's own shape (a 9-panel
  mosaic of **5,477** synthetic solved subs, this box): `compute_mosaic_canvas` **6.02 s → 0.89 s** (6.8×) and
  `estimate_stack` — what `/stack-estimate` spends its time in — **6.04 s → 1.06 s** (5.7×), i.e.
  **0.94 ms a sub** removed, the whole `wcs_from_text` share this entry identified. The fast path is
  a hand-rolled 80-column card scan plus assignment onto a bare `WCS(naxis=2)`: **0.85 ms → 0.07 ms** a
  header, 12×. Both halves of the entry's diagnosis were confirmed on the way — `Header.fromstring` is
  **0.047 ms**, and the expensive half is `astropy.wcs.WCS()` *plus* every subsequent `key in header` lookup
  (a `Header` re-verifies cards on each one, which is why an "astropy `Header` + fast assignment" hybrid
  measured 0.47 ms and the raw card scan measures 0.07 ms). **It is a pure optimisation, and the tests are
  what say so:** the fast WCS must re-serialise **byte-identically** through `to_header(relax=True)`, record
  the same `pixel_shape` and transform a pixel grid to **bit-identical** RA/Dec, across ten header shapes
  (our own CDELT and CD serialisations, an ASTAP sidecar carrying CD *beside* CDELT+CROTA, the legacy
  CDELT+CROTA2 convention, half-written CD/PC matrices, a seam frame, a near-pole frame); and
  `test_mosaic.py` pins that the union canvas is identical with the fast path disabled. `CROTA` is **not**
  re-implemented — it is handed to wcslib via `wcs.crota`, exactly as the header path does. Anything the
  scan does not fully understand (SIP, `PV`, a non-TAN or galactic projection, a third axis, non-degree
  units, a duplicated keyword, a length that is not a whole number of cards) returns `None` and falls
  through to astropy's own read, so an unrecognised keyword can never be silently dropped.

  v0.374.8 took `mosaic.compute_mosaic_canvas` from 13.87 s to 4.75 s by vectorising the
  footprint transform. What is left is measured and is one thing: `wcs_from_text` costs **0.755 ms** a frame
  and is called once per sub, so **5,477 × 0.755 ms ≈ 4.1 s** of the remaining 4.75 s. It is not the parsing
  — `Header.fromstring` alone is **0.042 ms** — it is `astropy.wcs.WCS()` construction, which re-serialises
  and verifies the header (257,434 `Card._verify` calls across one canvas computation). `WCS(..., fix=False)`
  buys 4 %; `relax=False` buys 20 % and changes what keywords are accepted, so neither is the answer.
  **This matters because of where it runs:** the Stack page fires `/stack-estimate` **twice** and both queries
  carry the drizzle and canvas-mode options in their query key, so every toggle of those controls re-pays it,
  and `/rejection-outlook` runs on every Target-page load.
  **Four shapes — (a) and (b) touch the engine and need care; (c) and (d) are frontend-side and smaller:**
  ~~(a) *Fast construction.* Build the WCS by assigning `ctype`/`crval`/`crpix`/`cd` onto a bare `WCS(naxis=2)`
  — which is exactly what `mosaic.compute_mosaic_canvas` already does for the output canvas — for the headers
  **we ourselves wrote** (`wcs_to_text`), falling back to the full parse for anything carrying SIP, `PV`
  distortion, a non-TAN projection or extra axes. Needs the fallback to be conservative and a test that both
  paths agree on a real ASTAP sidecar, not only on a synthetic. Measure it before committing: if a bare
  `WCS(naxis=2)` plus assignment is not markedly cheaper than `WCS(header)`, this shape is worthless.~~ —
  **SHIPPED v0.374.9; the numbers are in the ▶ block above. One correction for the record: the entry framed
  it as "for the headers we ourselves wrote", but the gate that matters is the header's *shape*, not its
  author — an ASTAP sidecar is a plain TAN header too, and it is the one the owner's 5,477 subs actually
  carry, so gating on provenance would have bought nothing on real data.**
  **Read (b)–(d) with the new number, not the old one: the problem they were sized against is now ~1 s, not
  ~4.7 s.** A Stack-page load costs ~2.1 s of canvas work rather than ~9.3 s, and a κ-slider nudge ~1 s rather
  than ~4.7 s. None of them is wrong, but none is worth the staleness or API risk it carries at that size —
  **profile before picking one**, and expect to conclude that (b) in particular is no longer worth its trade.
  ~~(b) *Memoise the canvas per target*, keyed on a frame-set fingerprint (count + max rowid + accept/solve
  state). Cheapest by far, but it is the staleness trade **v0.374.6 explicitly warned about** for the Library
  page — a stale canvas estimate after a scan is its own bug — so it needs the fingerprint to be genuinely
  complete, not "good enough".~~ — **SHIPPED v0.424.1, and its own caution is what shaped it.** The
  fingerprint this line proposes is the "good enough" one it warns against: a re-solve that rewrites a
  frame's `wcs_json` to the same length leaves count, max rowid and accept/solve state untouched, and the
  memo would then serve a canvas built from where the subs used to be. What shipped hashes **every column of
  every frame row** (`Project.frames_fingerprint`), so completeness is a property of the query rather than of
  a column list somebody has to keep in step — 129 ms against the 1,007 ms it skips. See (d) below.
  ~~**(c) is the smallest and was checked rather than guessed** — `Stack.tsx` runs two queries and they
  *do* legitimately differ (`stack-estimate` uses the user's current options; `stack-estimate-drizzle` asks a
  fixed `drizzle: true, scale 1.5` feasibility question, enabled only when drizzle is off and ≥200 frames are
  accepted). For the owner — thousands of subs, drizzle off by default — **both fire**, so the Stack page
  pays ~9.3 s on load. Folding them into one request that answers both sizings from **one** canvas
  computation halves that without touching the engine.~~ — **SHIPPED v0.376.1**
  (`stacker.StackCanvasBasis` + `estimate_stack_basis` / `estimate_stack_from_basis`, and
  `/stack-estimate`'s additive `drizzle_probe`). It *did* touch the engine, and that turned out to be the
  right place: the split makes "the canvas depends on `mosaic_canvas` alone" a thing the code states and a
  test enforces, rather than a fact a router has to remember. Measured on the entry's own shape (9-panel,
  **5,477** synthetic solved subs, this box): a Stack-page load's sizing work **2.18 s → 1.13 s**, and a
  second sizing off a held basis costs **44 µs**. Entry in [`SHIPPED.md`](SHIPPED.md).
  ~~**(d), and the sharpest of the four:** the first query's key carries `sigma_kappa`, `sigma_clip`,
  `min_max_reject`, `min_max_reject_count` and `auto_reject` — **none of which affect the canvas**; only
  `drizzle*` and `mosaic_canvas` do. They are in the key because the same endpoint also answers
  `rejection_reach`. So nudging the κ slider re-pays a 4.7 s canvas computation purely to refresh a rejection
  note. Splitting the *rejection* answer out of `/stack-estimate` (or memoising the canvas half on the
  canvas-affecting options alone) would make those toggles instant and is independent of (a) and (b).~~ —
  **SHIPPED v0.424.1** as the *second* of its two shapes, `webapp.estimate_cache`. The split the entry leads
  with turns out not to be available: `min_max_reject`, `min_max_reject_count` and (through
  `_resolve_auto_reject`) `auto_reject` and `sigma_kappa` all move the **peak**, so they cannot be lifted out
  of the sizing key — only the *canvas* is option-independent, and `drizzle*` does not move that either, so
  the memo makes the drizzle controls instant as well. Measured on the entry's own shape (9-panel, 5,477
  synthetic solved subs, this box): a warm lookup is **129 ms** against the **1,007 ms** the
uncached path costs every time (a cold one pays both, 1,116 ms), the 129 ms being
  `Project.frames_fingerprint` — `SELECT *` over the whole frames table, hashed — which is what makes the
  staleness trade (b) was warned off *not apply here*: the basis is revalidated against the frames it was
  built from on every single lookup, not trusted for a while. **(b) is closed with it** — a
  count/rowid/length fingerprint is exactly the "good enough, not genuinely complete" shape the warning was
  about, and the complete one measures cheaply enough that there is no reason to want it. Entry in
  [`SHIPPED.md`](SHIPPED.md).

- **NEW IDEA (Builder 2026-08-06, MEASURED while auditing the stack path) — `detect_mixed_pointings` is a pure-Python
  O(n²) pair loop with no cap, so the mixed-pointing preflight grows quadratically with a target's sub count.**
  *(Performance — size S; **off-by-default setting, so this is a latency note, not a live problem**.)*
  `seestack/stack/pointings.py::detect_mixed_pointings` single-linkage-clusters every accepted+solved sub against
  every other one. The inner loop never short-circuits (a single tight target means *every* pair links), and
  `webapp/pipeline.py::_detect_mixed_pointings` passes the full frame list with **no cap** — unlike the frontend
  mirror (`frontend/src/components/target/mixedPointings.ts`), whose comment notes it is "bounded by the 2000-frame
  list cap". **Measured** (one tight cluster, the ordinary single-target case): 0.17 s at 1 000 subs, 0.70 s at
  2 000, 2.7 s at 4 000, **10.8 s at 8 000** — and 4× again per doubling, so the §1 owner's "thousands of subs"
  target is a tens-of-seconds stall inside a stack job. **Only reachable with `mixed_pointing_guard` on** (it is
  **off** by default), and it runs in a background job rather than an HTTP request, which is why this is filed as
  perf rather than a bug. **Care:** any speed-up must be **exactly** verdict-preserving (a grid/KD-tree prefilter
  is only exact if the neighbour radius is the chord `2·sin(d/2)`; naive cell-representative merging is *not*).
  Cheapest honest option is simply to vectorise the pair test in NumPy in blocks (same O(n²), ~100× the constant)
  or cap the input with a deterministic subsample — a cap changes the verdict, so it needs its own argument.
  **Gate:** only worth doing if the owner turns the guard on.
- Profile the stack hot path on a large synthetic target; find a safe win that
  doesn't touch memory bounds or correctness. (M)

### Infra / maintainability

- ~~**LEAD (Builder 2026-09-17) — no dogfood pass has ever held the owner's *scale*, and the probe measures
  the one dimension that hides it.**~~ — **✅ SHIPPED v0.455.3** the same run, as
  `scripts/agent-dogfood.sh --deep` + `scripts/dogfood_deep.mjs`. Entry cut to [`SHIPPED.md`](SHIPPED.md),
  one-liner under "Shipped". Its cost question was answered by measuring rather than guessing (per-frame QC is
  ~0.09 s at 160×120 against ~0.41 s at the field sample's 480×320, so 1,200 subs is ~2 minutes and the sensor
  is small for that reason and no other), and the drive was verified in **both** directions — it reported the
  windowed table on the fix and fired its own "ONE ROW PER SUB" detector on the window reverted. **The one
  thing it deliberately did not do, and the reason:** the entry's note about `AutoGradeModal`'s recommendation
  table (one row per flagged frame under a 25 % cap — ~1,369 rows on the owner's biggest target, ~6 nodes each,
  and only while the modal is open) stays a note. It is two orders of magnitude cheaper than the defect that
  prompted this, it is behind a deliberate click rather than on every page load, and `Stack.tsx` — the only
  other reader of the same complete frame list — renders none of it. So the frontend has **no** unbounded
  per-sub render left on a hot path; fix that one only if a `--deep` pass ever measures it as a problem.
- ~~**LEAD (Builder 2026-09-14, filed with v0.445.2/v0.445.3 — the fifth instance of the same hole, and the
  first one that hides a whole *subsystem* rather than one card) — every dogfood sample fits inside the
  preview proxy, so the editor's entire decimated-proxy surface has never been rendered in a browser.**~~
  — **✅ SHIPPED v0.446.0** (Builder 2026-09-14) as the lead's own named lever, a third opt-in
  `load_sample(shape="big")` + `scripts/agent-dogfood.sh --big`; entry cut to [`SHIPPED.md`](SHIPPED.md),
  one-liner under "Shipped" below. **Its "measure before scoping" was carried out first and is what set the
  size:** 900×600 panels give a 1694×1150 union canvas and `proxy_scale` exactly **2** — the smallest canvas
  that reaches the surface at all — measured at **61.5 s** of stack (vs 19.0 s for the small mosaic), so the
  flag costs about a minute rather than the twenty the lead worried about. The two existing samples are
  pinned **byte-identical** by digest, not by argument. Original reasoning kept below.
  *(Pillar: maintainability in service of not missing bugs — size M; **measure before scoping**. Confidence:
  arithmetic, checked this run against `sample_data._WIDTH` and `PROXY_MAX_PX`; not yet reproduced by
  building a bigger sample.)*
  `seestack/edit/proxy.py` decimates above **1500 px**. The field sample is `_WIDTH = 480`; the `--mosaic`
  sample's union canvas is ~907×615. Both give `proxy_scale == 1.0` — i.e. **`get_proxy` never strides on
  either sample**, and everything gated on a strided proxy is structurally unreachable by
  `scripts/agent-dogfood.sh`, including `--editor`, which clicks every op in the Add menu: the five
  preview↔export advisories (`sharpen_preview_understates`, `deconv_…`, `denoise_…`,
  `hot_pixels_preview_skipped`, `star_reduce_preview_overstates`), **and the whole of `FullSizeCheck`** — its
  button, its modal, its navigator, its `X-Loupe-Window` marker and its split comparison, ~250 lines of the
  priority-1 screen, none of which any pass has ever drawn. The owner's mosaics are ~3494×2470 and up, so
  this is his everyday state and the tooling's permanent blind spot. Both fixes shipped this run were found by
  *reading* for that reason, and both are pinned only by jsdom.
  **The lever, and the cost that has to be measured first:** `load_sample(shape=…)` already takes a shape, so
  a third opt-in shape (or a `--big` flag scaling `_WIDTH`/the panel step) is the shape of the fix — the
  `--mosaic` (v0.386.0) and `--incoming-lag` (v0.442.1) precedents both did exactly this. It must stay
  **opt-in and leave the two existing samples bit-identical**: the field sample's generated pixels are pinned,
  and the page-height baselines in `PROCESS-NOTES.md` are measured on it. What is *not* known is the stacking
  cost — a canvas over 1500 px on its short side means panels ≥ ~4× today's pixel count, and a dogfood pass
  that takes twenty minutes will stop being run. Measure one stack at the smallest canvas that strides
  (≈1600 px wide, `proxy_scale` 2 — the `tests/webapp/test_editor_loupe.py` fixture uses exactly 1600×900 for
  this reason) before scoping anything larger.

- **LEAD (Builder 2026-09-14, filed with v0.445.0/v0.445.1 because it is the one thing that fix could not be
  photographed doing) — the season-closing card is the next self-hiding surface no dogfood pass can reach, and
  the reason is the sample's fixed coordinates.** *(Pillar: maintainability in service of not missing bugs —
  size S–M; **check the arithmetic below before building anything**. Confidence: reproduced this run — the
  `--mosaic` pass printed the new `TONIGHT_PRESCRIPTIVE` block with **only** `plan-week` speaking.)*
  v0.445.1 teaches the probe to read `/tonight`'s prescribing column as one paragraph. Three of the four cards
  in it were silent on the pass that verified it, and `closing-season` is the one that matters: v0.445.0's whole
  point is the sentence that appears *between* it and `plan-week`, so the fix is pinned by jsdom and a
  fail-before revert but has **never been rendered in a browser**. This is the missing-observing-site (v0.436.1),
  click-only-Compare (v0.440.2) and empty-`incoming/` (v0.442.1) hole a fourth time.
  **Why the obvious lever does not work, so nobody spends a slot on it:** a season closes as a function of the
  target's **RA against the date**, not of where you stand — so no `DOGFOOD_SITE` makes the bundled sample
  close. Both samples sit at M 42's coordinates (RA ≈ 5h35m), whose season in September is *opening*. A closing
  target in September wants RA ≈ 16–18 h. So the only honest levers are (a) let the sample writer place a target
  at caller-chosen coordinates — `sample_data._write_sample_fits` already takes a `star_shift`, and
  `--incoming-lag` is the precedent for a dogfood flag reaching into it by name — seeded as a **third, opt-in
  shape** so the field sample's generated pixels stay bit-identical (pinned since v0.386.0) and the default
  pass's page-height baselines do not move; or (b) accept that this card is verifiable only in jsdom and say so
  in AGENTS.md §7 rather than leaving a future run to rediscover it. **Prefer (a) only if a second finding turns
  up in that column** — one un-photographable card is a thin reason to grow the sample surface, and (b) costs a
  sentence. **Care if (a) is built:** a seeded target must be recognisably a demo, and it must not teach the
  planner to plan a real owner's night from coordinates nobody chose — the same line v0.436.1 drew when it put
  the observing site in *Settings* rather than in the sample's FITS headers.

  **↳ THE SECOND FINDING THIS ENTRY ASKED FOR HAS TURNED UP — v0.476.0** *(Builder 2026-09-26)*. It was found
  by reading the code, not by a browser, so it does not *itself* prove a browser was needed — but it is a
  finding in this column, it was in `closing-season` specifically, and it is the kind a rendered card makes
  obvious: the endpoint scanned only the forty targets with the **most** integration on them, so on a
  104-target library it reported 7 of the 18 targets that were leaving and every row it did show had
  12.7–19.1 h on it. A pass that could render this card with a real spread of depths would have shown a list
  of finished projects under a headline about what you are about to lose. **So (a) is now the preferred
  shape** by this entry's own test; its Care note is unchanged, and a seeded closing target should carry a
  *range* of `total_exposure_s` (one barely-started, one deep) or it cannot exercise what was just fixed.

  **✅ SHIPPED AS SHAPE (a), v0.477.0** *(Builder 2026-09-26)* — entry closed; the write-up is in
  [`SHIPPED.md`](SHIPPED.md) (search **"season-closing dogfood"**). In one line: `--closing` asks the planner
  itself where such a target would have to sit (`nightplan.closing_sky_position` probes an RA/Dec grid
  *through* `season_closing`, so the demo and the card cannot disagree about what "closing" means), then loads
  a fifth `POST /api/sample` shape at that position — a **pair** of targets on one patch of sky with 1 min and
  1.5 h kept, which is this entry's own "range of `total_exposure_s`" requirement and isolates depth as the
  only variable. The Care note is honoured: the coordinates are a *target's*, never an observing site's, the
  caller chooses them, and every other shape now **refuses** a centre rather than ignoring one, so the
  bit-identical pixels of the field and mosaic samples cannot move by accident.

- ~~**LEAD (Builder 2026-09-12, filed with v0.435.0 because it is what that fix could not reach) — the
  bundled sample cannot light up the whole "PLAN A NIGHT" half of the app, so no dogfood pass has ever
  seen those screens with data.**~~ — **✅ SHIPPED v0.436.1** as the entry's own shape (a), and it found
  two things on its first pass; entry cut to [`SHIPPED.md`](SHIPPED.md). Original text kept below for the
  reasoning, which stands: *(Pillar: maintainability in service of not missing bugs — size S to
  measure, and **read the caution before building anything**. Confidence: reproduced in a browser this
  run.)*
  `tests/synth.write_seestar_fits` writes no `SITELAT`/`SITELONG` unless asked, and `webapp/sample_data`
  never asks — so with both samples loaded and stacked, `_resolve_observer` reports `"none"` and
  **Tonight, the Sky Map's placement, the life list's "Up tonight" chip, the wishlist's "the Tonight page
  will tell you when", `/api/plan/closing`, `/api/plan/week` and `/api/life-list/nearly-there` are all in
  their empty state**. Every "dogfood CLEAN" ever recorded was therefore a statement about the half of the
  app that does not need a site. That is a real coverage hole — v0.433.0, v0.430.0 and v0.426.0 all shipped
  into that half in the last week.
  **⚠ The obvious fix is the wrong one: do NOT write a site into the sample's headers.** A location in a
  frame header is not decoration — `_resolve_observer` *plans from it*, so a sample claiming to have been
  shot from Greenwich would silently tell an owner in Sydney which targets are up, computed for the wrong
  hemisphere, with only `location_source: "fits"` anywhere on the wire to say so. The sample is a demo, not
  a measurement, and the app has no way to mark a location as "pretend".
  **Shapes that might be honest, none of them checked:** (a) make it a *dogfood-only* step — the script
  `PUT`s a site into Settings on its own scratch install before probing, which is what a real owner's
  library supplies and touches no shipped data; (b) have `POST /api/sample` take an optional explicit
  location the caller chooses, defaulting to none, so the demo only ever plans from a site somebody asked
  for. (a) is nearly free and closes the coverage hole; (b) is a product decision and probably not worth
  it. Either way the sample's generated pixels must stay bit-identical (pinned since v0.386.0).


- ~~**LEAD (Builder 2026-09-15, filed with v0.447.0 because it is the axis that fix sits on rather than the fix
  itself) — `seam_residual` was one stored measurement whose estimator moved under it; nothing has asked which
  of the others did.**~~ — **✅ SWEPT AND CLOSED 2026-09-17 (Builder). One finding, shipped as v0.454.0
  (`transparency_ratio`); the other eight columns are non-findings or already dated. Read the two ↳ blocks
  below before re-opening — the whole point of this entry was to ask the question once.** *(Pillar: trust — PRIORITY 3/4; size S to *ask*, unknown to fix; **do not start by
  writing code**. Confidence: the axis is demonstrated — v0.313.1 is one confirmed instance, measured on the
  owner's library at 25 of 38 controlled pairs changing verdict; ~~whether there is a second is **not**
  checked~~ — there was exactly one, and it is fixed.)*
  A `stack_runs` row carries a dozen numbers measured **at stack time** and read, years later, through
  thresholds that live in today's code: `noise_sigma`, `stack_fwhm_px`, `transparency_ratio`,
  `rejection_fraction`, `grain_ratio`, `coverage_thin_frac`, `uncovered_frac`, `coverage_median_depth`,
  `duration_s`. Each is a *number with an estimator behind it*, and the estimator is in the repo while the
  number is in the owner's database — so any change to one silently re-scales every stored row, and every
  surface that compares two runs ("your cleanest stack", the Compare verdicts, the History chips) is comparing
  two quantities. The app already knows this in two places and neither generalises: `coverage_shares_version`
  versions the coverage shares and **re-derives** a stale one, and `seam_scale` (v0.447.0) dates the seam
  figure and heals it. Everything else is undated.
  **The work is a question before it is a change.** For each column: has its estimator moved since rows were
  written, and if so in which direction? `docs/SHIPPED.md` is the usable record — the repo clone an agent gets
  is **shallow**, so `git log -L` on the estimator will not answer it (that is what stopped this run going
  further). Two known leads to check first: `noise_sigma` goes through `seestack.edit.noise.estimate_noise_sigma`,
  which the editor's own noise measurement also feeds, and v0.225.0 changed how sky noise is measured on the
  *proxy* (MAD of adjacent-pixel differences, because the old form counted a mosaic's panel offsets as grain) —
  **check whether that change reached the estimator the stacker stamps, because `noise_sigma` is the number
  History ranks "cleanest" by and the walk-away degradation report was read off it**; and `grain_ratio`, whose
  own docstring argues its σ was *chosen* to survive a decimated read, i.e. somebody has already thought about
  its estimator once. **Only file a bug for a column where the change is actually found**, with the direction
  measured the way v0.447.0 measured the seam's (`se >= 0` on both ends, so one-sided) — a one-sided change can
  be *read* around, a two-sided one needs the heal. Do not add a version column to a measurement nobody has
  shown moved: that is nine migrations for a hypothesis.
  **↳ THE FIRST NAMED LEAD IS ANSWERED, AND IT IS A NON-FINDING — don't re-trace `noise_sigma` (Builder
  2026-09-17, read in the code and in this repo's own shipped record, which is what the lead says to use
  because the clone is shallow).** v0.225.0 did **not** change `edit.noise.estimate_noise_sigma`; it changed
  `presets.analyze_proxy`'s `sky_sigma` to *start calling* it. Its own entry says so in as many words — *"the
  same estimator already behind the editor's 'From your image' denoise suggestion, so the two halves of the
  crossfade finally measure the same thing"* — and the old form it replaced (`1.4826·MAD` of the sky's
  **levels**) has no other caller. `stacker._compute_noise_sigma` has gone straight to
  `estimate_noise_sigma` all along, so the column the History "cleanest" ranking and the walk-away degradation
  report are read off is stamped by an estimator whose formula has never moved. Two near-misses checked and
  cleared with it: `analyze_proxy` applies `_SKY_HALF_MAD_SCALE = 0.593` and `_compute_noise_sigma` does not,
  which is two scales for two consumers rather than drift in one; and the v0.354.1/v0.354.2 rounding fix is on
  the float→uint *pack*, downstream of the float array this σ is measured on. **`grain_ratio` and the other
  seven columns are still unchecked**, so the entry stays open — just not on this lead.
  **↳ LEAD TWO IS A FINDING, AND IT SHIPPED AS v0.454.0 (Builder 2026-09-17): `transparency_ratio`.** Its
  estimator moved in **v0.304.2** — `stacker._compute_transparency_ratio` stopped dividing a mosaic run's
  median by one target-wide `p90` and started comparing each panel against its own
  (`_panel_transparency_ratios`) — and, exactly as this entry predicts, the fix re-measured nothing and dated
  nothing while `HAZY_RATIO = 0.6` went on living in today's code. Reproduced on the fixture the fix itself
  ships: a steady-sky 3-panel mosaic stores **0.5001** and measures **0.9996** today. Direction measured the
  way this entry asks: **two-sided** (300 randomised mosaics, today's figure higher on 251 to +0.72, lower on
  49 to −0.27), so unlike the seam there is no half to read around and the rule is silence. Entry in
  [`SHIPPED.md`](SHIPPED.md).
  **✅ AND THE REST OF THE COLUMN LIST IS SWEPT, ALL NON-FINDINGS — the entry is CLOSED; do not re-trace it
  (same run, read in the code and in this repo's own shipped record, which is what the entry says to use
  because the clone is shallow).** Nine columns, one finding:
  - `noise_sigma` — cleared above (lead one).
  - `grain_ratio` + `grain_thin_frames` / `grain_deep_frames` / `grain_thin_share` — shipped **with**
    `measure_coverage_grain` itself in v0.406.0, and nothing has touched the estimator since. The later grain
    work (v0.406.2 and the shortfall gate) changed the *sentence* `stack_health` writes, never the σ; the
    `_robust_stats` it borrows last moved in v0.313.1, i.e. before the column existed.
  - `stack_fwhm_px` — `_compute_stack_fwhm` goes through `qc.metrics.detect_stars` / `median_fwhm` /
    `estimate_sky`, and the only post-v0.194.0 change to any of them is v0.345.4's `sigma_clipped_stats_finite`,
    whose own entry pins that the masked call returns **bit-identical** `(mean, median, std)` — "silence, not a
    new number". The `median_eccentricity` / `green_channel` fixes are v0.109.10, before the column.
  - `rejection_fraction` — not an estimate at all, but a tally of what the combine that ran actually rejected.
    Two runs differing here differ in their *pixels*, which is the honest reading.
  - `duration_s` — a wall clock.
  - `coverage_thin_frac` / `coverage_median_depth` / `uncovered_frac` — the one family that **was** already
    dated, and correctly: `coverage_shares_version` (v0.389.2) versions the thin reference and
    `coverage_backfill.backfill_coverage_shares` re-derives a stale run from the map still beside its master,
    dropping the share in memory when the map has gone. `uncovered_fraction` has not moved since v0.377.0.
  So the axis this entry named is real — it produced `seam_residual` and now `transparency_ratio` — and it is
  **exhausted against today's column list**. Re-open it only when a *new* estimator change ships against a
  stored column, which is the moment to stamp a generation beside the figure rather than the audit to repeat.

- **NEW IDEA (Builder 2026-09-04, after losing three separate slots to it in one run) — when an entry ships,
  strike the "the half X deliberately did NOT build" follow-ons the same commit closed, not just the entry
  itself.** *(Pillar: maintainability in service of not wasting runs — size XS per sweep, and it is a **Scout**
  job. Confidence: measured on this run.)* Three entries this run were picked as open work, greped, and turned
  out to be fully on `main`: the loupe's **preview-space marker** (filed 09-03 as "the half v0.329.5
  deliberately did NOT build", shipped v0.329.6 *an hour later by the same run*), the Target page's
  **early-stop night marker** (filed 09-04, shipped v0.342.0), and **"the other two exports still made out of
  the 1024 px preview"** (both halves shipped — `SHARE_JPEG_MAX_LONG_EDGE` and `wallpaper_source_long_edge`).
  Two of the three were already correctly *indented* under their shipped parents and cost only a read; the
  third was a live top-level bullet and cost a full trace. **The pattern is specific enough to act on:** an
  entry of the form *"the half N deliberately did NOT build"* is the single likeliest thing the **next** run
  builds, and the run that builds it strikes the parent it was working from — not the follow-on it never
  read. **Shape:** when curating, for each newly-Shipped entry, grep the file for the sibling phrases
  ("deliberately left out", "deliberately did NOT build", "the half", "the other two") naming the same
  version, and strike or indent what that commit closed. **Do NOT** turn this into a code check: the
  relationship is editorial, and the existing "keep a shipped item's spec *indented*" convention already
  makes the answer visible by shape once someone applies it.

- ~~**NEW IDEA (Builder 2026-09-03, spotted while adding the sibling channel in v0.328.2) — `EditContext.op_notes`
  is keyed by op **id** where its new sibling `fitted` is keyed by op **uid**.**~~ — **✅ SHIPPED v0.475.2.**
  Entry cut to [`SHIPPED.md`](SHIPPED.md), one-liner under "Shipped". Two things the entry asked for and the
  build answered, kept here only because they change how the *next* entry of this shape should be read:
  **its "check first" was the whole size of it** — a double-op recipe *is* reachable (`Editor.tsx::addOp` has
  no duplicate guard, so two **Color calibration** ops is two clicks), which turns "an XS tidy-up" into a
  priority-1 parity fix; and the defect is **one field, not the note** — reporting the *last* instance's
  `mode_used` is right (a second calibration runs on top of the first), while `proxy_fallback` is a
  preview-vs-export warning that has to be **any** instance's, or the advisory silently disappears when the
  *first* op is the one that fell back. The entry's claim that `seestack/edit/ops/detail.py` writes `op_notes`
  too is **stale** — its advisories moved to `fitted` before this; `tone.color_calibrate` was the only writer.

- **NEW IDEA (Builder 2026-08-30, the shape the v0.311.1 bug had, and the reason it existed) — there are now
  **two** answers to "render this run's picture at size N, exactly as it is shown", and the bug was the gap
  between them.** *(Pillar: correctness by construction / maintainability — PRIORITY 3; size S; pure
  consolidation, no behaviour change intended.)* `stack._native_picture_source` (v0.310.0) knows the full list
  of ways a stored preview can differ from a fresh FITS render — a baked North-up turn, a display-space
  "Process target" edit, an auto-crop trim, a missing master — and **declines** when it can't reproduce the
  picture faithfully. `download_full_res_png` answers the same question independently: it handles the recipe
  and the saved `stretch`/`black`, silently didn't handle the baked turn (that was v0.311.1), and does not
  consider the crop at all. Two implementations of one question is exactly how the rotation went missing from
  one of them. **Shape:** one function — `run_picture_png(run, recipe_json, *, max_long_edge)` — that returns
  the render *and* what it could not reproduce, with `_native_picture_source` becoming "call it, and decline
  when it reports anything unreproduced" and the full-res endpoint becoming "call it, and serve what comes
  back". **Do it as a pure refactor with the existing tests as the gate** (`test_full_res_png.py`,
  `test_share_native_resolution.py`, `test_wallpaper.py` between them pin every branch), and check the **crop**
  case explicitly while there: a plain run should never carry a `preview_crop_json` (only the auto-edit writes
  one, and it sets `preview_display_space` too), but nothing asserts that, and if it can happen the full-res
  download is showing a differently-*framed* picture the same way it was showing a differently-rotated one.
  **↳ THE CROP HALF IS ANSWERED — a non-finding; don't re-trace it (Builder 2026-09-06).** Both writers of
  `preview_crop_json` set the display-space marker in the same block (`pipeline.py:3199` → `:3208`), and the
  North-up "Adjust → Save" endpoint refuses a non-display-space run with a 400 *before* it writes either — so
  the crop is fenced off where it could be created, unlike the rotation, which was simply forgotten in one of
  the two renderers. The remaining consolidation is a **pure refactor with no known defect behind it**; it was
  sized and deliberately not taken. Full working in [`PROCESS-NOTES.md`](PROCESS-NOTES.md), 2026-09-06.

- **PERF WATCH ITEM (Builder 2026-08-30, introduced knowingly by v0.310.0 / v0.311.0) — the wallpaper and the
  share JPEG are now real renders, and nothing caches them.** *(Size S if it ever bites; **do not build it on
  spec** — AGENTS.md §6 says optimise a *measured* hot spot.)* Both were a file read plus a re-encode; each is
  now a decimated FITS load and stretch (≤ 2560 px for a share, ≤ the device size for a wallpaper) on every
  request, and the browser has no way to revalidate — the responses carry no `ETag` or `Last-Modified`. A
  beginner tapping Share three times pays for three renders. The cheap fix if it is ever felt is a validator
  keyed on the master's `(mtime_ns, size)` plus the request's own parameters, exactly as
  `_zoom_clip_signature` already keys its cache; the expensive one is a stored derivative, which is what the
  "Process target" half of the same feature would need anyway. **Measure first:** on the owner's box the
  interesting number is a share tap on their largest mosaic, not a synthetic frame.

- **QA LEAD (Builder 2026-08-27, generalised from three fixes of the same bug in one run) — sweep every
  consumer of a run's *stored preview bytes* that derives geometry from the FITS.** *(Pillar: image quality /
  correctness — PRIORITY 4; size S to audit, unknown to fix; a good Scout run.)* Three separate surfaces shipped
  the identical mistake and each was found only because the previous fix made it obvious: the Sky-map overlay
  (alpha + tile placement, v0.288.1), History's object pins and scale bar (v0.289.2), and the share JPEG /
  wallpaper (filed as a verified bug at the top of "Bugs"). The shape is always the same — **the stored preview
  PNG is not necessarily the un-rotated FITS grid**, because History's "Adjust → North up → Save" can bake a
  rotation into it, and until v0.288.1 nothing recorded that. Anything that draws on those bytes, re-orients
  them, or builds a WCS/pixel coordinate for them from the master FITS is suspect. **The fact now exists**
  (`stack_runs.preview_north_up_deg`, exposed on `StackRunOut`), so the audit is mechanical: grep for readers of
  `run.preview_path` and for `celestial_wcs_from_fits`/`wcs_dict_rescaled_to_preview`/`stack_coverage_mask`/
  `wallpaper_target_pixel`/`objects_in_field`/`_scale_bar_from_wcs` used *alongside* a preview, and decide each
  site explicitly (follow the rotation, or refuse). A structural answer worth considering while sweeping: one
  helper that hands a caller "the geometry of the bytes you are about to draw on" (angle + size), so a future
  consumer can't silently assume the FITS grid again.

- **IDEA (Scout 2026-08-27 #21) — extract the shared "resolve frames → build mosaic canvas → drop
  gross-outlier subs" prologue that `estimate_stack` and `run_stack` each re-implement, so the two can't drift
  apart again.** *(Pillar: trust — the pre-run estimate should match the run; size S–M; pure refactor, no
  behaviour change.)* The cosmetic `estimate_stack` bug filed at the top of "Bugs" this run (the estimate not
  dropping `canvas.excluded_frame_ids` before counting frames) is a *symptom*: both functions independently
  pick the reference, call `compute_mosaic_canvas`, and decide the canvas — but only `run_stack` also removes
  the outliers, because the prologue is copy-pasted rather than shared. Factor the common prologue into one
  helper (`(frames, dst_shape, is_mosaic, ref_shape)` after outlier exclusion) that both call, so a future
  change to canvas/frame resolution lands in both by construction. Keep it a **pure refactor** with the
  existing tests as the guard, plus one new test asserting `estimate_stack` and `run_stack` agree on the frame
  count for a target with a gross-outlier sub (which also closes the filed bug). Do this only when already in
  `stacker.py` for something else — not worth a dedicated slot, but it retires a whole drift class.

- **NEW IDEA (Builder 2026-08-15, filed the moment after a wall-clock test cost this run its first task) — a guard
  that no test may read the real clock, so a date-bomb can't quietly go red on a future date.**
  *(Pillar: infra / trust — PRIORITY 3 in effect, because a red baseline outranks everything an hour later; size S;
  test-only.)* This run opened on a **red frontend suite**: `Tonight.test.tsx` had hard-coded `"2026-08-15"` as
  "a future night", and 2026-08-15 arrived (fixed in v0.258.1). It was green in CI for weeks and would have gone
  red on a day nobody was looking — and it burns a whole Builder run's first task every time. **The class matters
  more than the instance:** a test that mixes a literal date with the *real* clock is deterministic today and
  broken later, and no amount of care at review time catches it. **Slice:** a meta-test that reads every
  `*.test.ts(x)` (and, on the Python side, every `tests/**/*.py`) and fails on an unannotated wall-clock read —
  `new Date()` with no argument, `Date.now()`, `datetime.now()`, `date.today()`, `utcnow()` — with an explicit
  opt-out comment (`// wall-clock: <why>`) for the handful of tests that legitimately need one (`futureNight()` in
  `Tonight.test.tsx` is exactly that case, and would carry the marker). Today the frontend has **one** such file
  and the Python date tests all inject `today=`/`now=`, so the guard lands green with a single annotation — which
  is the right time to add it. **Care:** grep-based guards rot into noise if they over-fire; scope it to test files
  only, keep the message explanatory ("a literal date + the real clock is a test that fails on a future date"), and
  prove it fires by mutation (add a wall-clock read, watch it fail) exactly as the `incoming/` guard does.
  **⚠ MEASURED — do NOT build the loose version; its own Care note is the thing that bites (Builder
  2026-09-12, sized against the tree rather than from this description).** The entry's premise — "today the
  frontend has **one** such file… so the guard lands green with a single annotation" — was true in August and
  is not now. **12 Python test files and 3 frontend ones read the real clock today**, and narrowing to the
  entry's actual bug class (a literal date *and* a clock read in the same file) still leaves **6 Python + 2
  frontend**. Every one inspected is correct as written: `tests/webapp/test_plan.py` carries both, and all six
  of its clock reads are `now ± timedelta` — which is exactly how those tests *should* be written — while its
  date literals (`_date(2026, 7, 15)`, `"2026-13-40"`) never meet the clock; the `time.time()` cases are
  job-wait deadlines, i.e. durations, which cannot be date bombs at all. So the guard as filed would demand
  **eight to fifteen opt-out annotations on correct tests** to catch a class with zero live instances, and a
  grep guard that is all false positives is one nobody reads. The precise rule — *a literal date compared
  against a value derived from the real clock* — is not greppable, which is why this entry reached for the
  loose one. **Left filed, not closed**: the risk it names is real and cost a run once. But if it is ever
  taken, it wants a **mechanism** (run a suite at a faked future date) rather than a grep. Full working in
  [`PROCESS-NOTES.md`](PROCESS-NOTES.md), 2026-09-12.

- **NOTE / WATCH ITEM (Builder 2026-08-13, left deliberately undone while shipping v0.254.0) — `routers/stats.py`
  still holds three hand-rolled `{sig, at, data}` caches now that a fourth moved to the shared
  `webapp/registry_cache.py`.** *(Infra — PRIORITY 3; size S; **do not do this on a hunch**.)* The library-progress
  roll-up now goes through `cached_for_registry`, but the "Your sky, so far" summary and two others still inline the
  same six lines. They were left alone on purpose: each keys on a **different** signature (the summary folds in each
  target's latest preview `stat`, which the shared `registry_signature` deliberately doesn't), so folding them in
  would mean either widening the shared signature for everyone or growing a parameterised key-builder — more
  machinery than three copies of six lines justify today. **Revisit if a fifth cache appears, or if one of the
  existing ones grows an invalidation rule** (the shared helper's `invalidate_registry_cache` is where that belongs).

- **NEW IDEA (Builder 2026-08-13, the sibling of the tooltip shipped in v0.254.0) — the Dashboard's "~2 more
  nights" badge has no hover explanation, unlike the planner's now does.** *(Friendliness — PRIORITY 3; size XS;
  frontend-only.)* `LibraryProgressCard`'s `ProgressRow` renders `nightsToGoLabel(r)` as a bare chip. The planner's
  equivalent now explains itself on hover (the readiness verdict plus the sentence naming the measured pace it
  divided by), and the same two sentences are already computable here — `r.readiness.verdict` is in hand and
  `clearNightsFromPace` returns the `text` alongside the count that `rankLibraryProgress` currently discards.
  **Lower value than it was on the planner, which is why it wasn't done in the same pass:** this card already prints
  "2.0 h of ~6h" inline on the row *and* the `finishFirstHint` sentence above it, so the chip is far better
  contextualised than a lone chip in a dense plan table. Worth one line if someone is in the file; not worth a trip.

- **NEW (Scout 2026-07-23) — remove or parity-pin the caller-less non-windowed `reproject_rgb` in `align.py` (latent
  CPU/GPU `cval` divergence).** *(Maintainability / latent-correctness; size S; from this run's align audit.)* The
  2026-07-23 adversarial align audit re-confirmed that the production stack uses only the **windowed** reproject path,
  where the CPU (`cval=NaN`) vs GPU (`cval=0`) boundary-fill difference is proven un-reachable by the
  `FRAME_EDGE_INSET_PX=3` interior-stencil argument. The **non-windowed** `reproject_rgb` is the one site that carries
  the exact-integer-boundary `valid` edge (`src_x <= w_src-1`, no inset) — and it has **no production caller**: the hot
  path uses `reproject_rgb_windowed` (`align.py:158`); the only user of the full-frame `reproject_rgb` (`align.py:286`)
  is `tests/test_windowed_stack.py:95`, purely as an *oracle* to prove the windowed path matches a full-frame
  reproject. Mild foot-gun: a future change that wired the full-frame version into production would bypass the windowed
  path's interior-stencil safety and lean on the edge boundary instead. **Fix directions (pick one — do NOT just delete
  it, the parity test depends on it):** (a) keep it but harden the two branches to identical fill semantics (both
  `cval=NaN` + valid-mask, mirroring the windowed path) and extend a CPU-vs-GPU parity assertion to this wrapper (the
  existing `tests/test_align_gpu_parity.py` covers the `_cpu`/`_gpu` kernels but not this wrapper's boundary handling);
  or (b) mark it explicitly test-only (underscore/rename + a docstring note) so nobody wires it into production by
  mistake. Either way documents intent and removes the latent divergence. Additive/safe (tightening an off-hot-path
  function + a test); no config/DB/API/on-disk/default change. Confidence: traced (no production caller +
  parity-hazard, not a live bug — the hot path never reaches it).
- **NEW (Scout 2026-07-21 #2) — `wcs_io.wcs_from_text` returns a *default* WCS instead of `None` for non-FITS
  garbage — a docstring/contract mismatch (cosmetic, unreachable with real data).** `io/wcs_io.py::wcs_from_text`
  (~L34) documents "Returns None on failure", but `astropy.io.fits.Header.fromstring` tolerates arbitrary garbage
  and yields a *valid-object* WCS with empty `ctype` / `crval [0, 0]`, so the None path never fires for malformed
  input. Harmless in practice — stored `wcs_json` is always machine-generated valid FITS (the garbage path is
  unreachable), and downstream `footprint_radec_deg` returns `None` for such an empty WCS anyway — so this is a
  contract/robustness tidy, not a live bug. **Fix (small):** after parsing, treat a WCS with no celestial ctype
  (or all-zero crval + no CD/CDELT) as a failure and return `None`, so the function honours its own docstring;
  add a unit test that non-FITS text → `None`. (XS, infra/robustness — very low priority; file only if a run is
  already in `wcs_io.py`.) Traced, unverified-as-user-impacting (correct-by-luck today).
- **NEW (Builder 2026-07-14) — consolidate the Dashboard's three per-project roll-ups into one cached pass
  (only with a measurement).** *(spotted shipping the v0.119.0 "Target progress" card.)* The Dashboard now
  triggers up to **three** independent passes that each open *every* project once: `/api/stats`'s stack
  roll-up (`_rollup_stacks` → `iter_stack_runs`), `/api/last-night` (`_collect_last_night` → `iter_frames`),
  and the new `/api/library-progress` (`_collect_progress` → the goal meta read). Each is separately cached
  (registry-signature + TTL), so steady-state a warm Dashboard is cheap — but a cold load (or a fresh scan
  that invalidates all three signatures at once) opens each project three times. A single combined roll-up
  that opens each project **once** and returns stacks + last-night + progress together would cut that to 1×.
  Gate on a real measurement (§3 / Performance) — on a small library the cost is negligible and the current
  separation keeps each endpoint independently cacheable and testable, so this is only worth it if a large
  library shows a real cold-load cost. Additive refactor, no behaviour change. (M, infra/perf — low priority.)
- **Low-priority (editor/consistency, spotted shipping v0.93.1): the bulk "Set all suggested
  values" button still uses the *raw-proxy* denoise strength.** Now that the per-op denoise
  "From your image" button is recipe-aware (v0.93.1), the bulk apply (`dataDrivenDefaults`, driven
  by the eager recipe-independent `denoise` query) can set a denoise strength that differs from what
  the per-op button suggests once a linear gradient/colour op precedes denoise. Defensible as-is —
  bulk apply is a from-scratch "quick start from your data" convenience and the raw stack noise is a
  reasonable seed there — so this is a consistency nicety, not a bug. Only worth aligning if a future
  run is already in that button's wiring. (S, editor/consistency)
- Chip away at the ~127 pre-existing `ruff check .` findings (don't add new ones);
  consider wiring ruff into CI once the count is low. (L, correctness/maintainability)
- **Scout to vet: two latent (not-yet-active) robustness traps flagged by the 2026-07-10 engine audit
  that shipped the v0.103.2 drizzle-reject fix — filed, not blind-fixed, because neither is traceable
  to a concrete wrong result *today*.** (S each, correctness/robustness)
  ~~(1) `seestack/edit/ops/background.py` `_subtract`/`_final_gradient` re-raise a `RuntimeError` when their
  errors collector is non-empty … the *per-frame* `bg/per_frame.py::_subtract_background_cpu` path uses a fixed
  `exclude_percentile=80` with **no** ladder.~~ — **FIXED v0.103.3** (Builder 2026-07-10; reproduced
  end-to-end before fixing, then vetted per the note). Trap (1) *is* reachable: a **sparse mosaic proxy** —
  a covered strip that's <20% of its bounding canvas, the rest uncovered NaN — makes the object mask
  (`| ~finite`) cover >80% of every box, so the strict `exclude_percentile=80` fit raises and the editor's
  `background.subtract` op **hard-failed** ("background fit failed: All boxes contain <= … unmasked or finite
  pixels") while its sibling `final_gradient` (which got the ladder in v0.89.2) degraded fine — a real
  editor inconsistency, not just the dense-field case. (The per-frame **box clamp** already prevents the
  *too-few-boxes* failure on any real ≥1080 px frame; it does **not** prevent this *too-much-masked* one.)
  `_subtract_background_cpu` now fits through the same `exclude_percentile` ladder (80 → 95 → 100, then a
  half-size box) via a new `_fit_bg2d_ladder` helper mirroring `final_gradient._fit_background_2d`. The
  strict 80 stays the first rung, so a normal frame's result is byte-for-byte unchanged (covers per-channel
  *and* luminance mode, and the stack path — which merely stopped silently skipping every channel). Regression
  tests `tests/test_bg_modes.py::test_sparse_mosaic_canvas_degrades_instead_of_failing` (asserts the strict-80
  fit really raises, then that the op surfaces no error and flattens the covered strip while preserving NaN)
  + `test_ladder_first_rung_matches_strict_fit` (byte-for-byte parity on a normal frame). Additive,
  upgrade-safe (no config/DB/API/on-disk change).
  ~~**(2)** `seestack/calibrate/apply.py::apply_raw` returns the
  *caller's own* float32 array when `is_empty` (no masters apply) — `asarray(...).astype(copy=False)` is a
  no-op, so the documented "returns a new array" contract is violated by aliasing.~~ — **FIXED v0.121.5**
  (Builder 2026-07-14, branch `claude/pensive-faraday-irqhx4`; regression-tested). `apply_raw` now copies at
  the return **only when the result would alias `raw`** (`if result is raw: result = result.copy()`) — the
  otherwise-aliasing empty-bundle-on-float32 path. Any applied master already yields a fresh array (subtraction/
  division), so `result is raw` is False on every real calibration path and no hot-path double-copy is taken;
  the stacker also sets `calibration = None` when `is_empty` so the empty branch is off the stack hot path
  entirely. Closes the latent contract violation so a future in-place consumer can never corrupt a shared source
  frame. Regression tests `tests/test_calibrate.py::test_apply_raw_empty_bundle_returns_a_fresh_array`
  (fails-before: `out is raw`; passes-after: distinct buffer, mutating the result leaves the input untouched)
  and `test_apply_raw_with_masters_does_not_double_copy` (a master path still returns a fresh, correct array).
  Additive, upgrade-safe (no config/DB/API/on-disk change).
- **Scout to vet: four low-severity latent gaps flagged by a fresh three-front stacking-engine audit
  (Builder 2026-07-16) — filed, not blind-fixed, because none is triggerable by real inputs today.** The audit
  swept `stack/stacker.py` + `stack/align.py`, `stack/drizzle_path.py` + `stack/mosaic.py`, and
  `calibrate/apply.py` + `calibrate/masters.py`; the hot paths (weighted-sum / Welford / min-max accumulation,
  σ-clip keep-mask polarity + NaN-widened tolerance, photometric multiply, reproject valid-mask insetting,
  drizzle super-res WCS scaling + two-pass clip statistics, dark/bias pedestal selection + exposure scaling,
  flat normalization + floor, sigma-clip master combine) all verified **correct and NaN/coverage-aware** — no
  pixel- or coverage-corrupting bug found. The four latent observations, each low-confidence-of-reachability:
  (S each, correctness/robustness — focus #1)
  - ~~**(1)** `calibrate/masters.py:203-205` — the `median` and `mean` master-combine methods use plain
    `np.median`/`np.mean`, **not** NaN-aware, unlike the `sigma_mean` sibling (`nanmedian`) and the flat path.
    A single NaN/inf pixel in an input frame would silently propagate into the master (and thence every
    calibrated light at that pixel).~~ — **FIXED v0.134.2** (Builder 2026-07-16, branch
    `claude/pensive-faraday-h477bm`; regression-tested). Judged **more than churn**: the combine sits on the
    calibration data-integrity path (focus #1) and the input is a *user-supplied* file, so it is not strictly
    "not triggerable" — a float FITS calibration frame carrying a NaN/inf pixel (an exported master re-used as
    an input, a partially-corrupt file) does reach `np.stack` and, for `mean`, a single NaN at a pixel poisons
    that pixel in the master → every calibrated light. **Fix:** mask any non-finite sample to NaN once
    (`finite_stack = np.where(np.isfinite(stack), stack, np.nan)` — handles inf too, which `nanmean` alone does
    not) and run all three methods over it (`nanmedian`/`nanmean`; `_sigma_clip_mean` now also gets the masked
    stack and its `full_med` fallback uses `nanmedian`), so a non-finite sample is ignored and the finite ones
    still combine, matching the engine's "NaN = no data" invariant. An all-non-finite pixel stays NaN =
    genuinely no data. **Byte-for-byte identical on every real integer-readout calibration set** (`np.isfinite`
    is all-True there, so the mask is a no-op). Additive, upgrade-safe (no config/DB/API/on-disk change).
    Regressions in `tests/test_calibrate.py`: `test_build_master_is_nan_aware` (parametrised over
    median/mean/sigma_mean — a NaN + an inf pixel in one input frame no longer poison the master;
    fail-before under mean/median) and `test_build_master_all_nan_pixel_stays_nan` (an all-non-finite pixel
    stays NaN, not folded to 0). Severity: data-integrity on a non-finite user input (low reachability).
  - **(2)** `stack/drizzle_path.py:300-303` — `frame_coverage` (`self._count`) is derived from **channel-0's**
    `out_wht` only, while the finite-mask and clip-reject masks are computed per channel; a pixel kept in
    channels 1/2 but NaN/clip-rejected in channel 0 is undercounted. **Diagnostic-only** (`coverage_min`/
    `coverage_max` "frames per pixel"), never the image or the weight maps — and consistent with
    `WeightedSumAccumulator`'s own `valid[..., 0]` count. Same disposition as the accumulator's documented
    channel-0 count.
    **⚠ Justification is now STALE (Builder 2026-08-04, spotted in a stacking-engine read):** the
    "consistent with `WeightedSumAccumulator`" half no longer holds — that accumulator was since changed to count a
    frame when it contributed to **any** channel (`valid.any(axis=2)`, `accumulator.py`), precisely so per-channel
    κ-σ rejection can't understate coverage. `drizzle_path.py`'s `frame_coverage` still reads channel 0 only, so
    the drizzle and standard paths now report "frames per pixel" by **different rules**. Still diagnostic-only
    (never the image or the weight maps), so the severity is unchanged and this is not worth a run on its own —
    but if anyone is already in `drizzle_path.py`, make it `any`-channel in the same commit and the two paths agree
    again. Confidence: traced (both call sites read).
    **⚠ STRIKE — already done (Builder 2026-08-06, re-read of `drizzle_path.py`).** `add_frame` now ORs each
    channel's strict post-add `out_wht` increase into one `deposited` plane (`deposited |= ...` over `c in
    range(3)`) before `self._count += deposited`, and the `frame_coverage` docstring says so. The two paths
    already agree on the `any`-channel rule; nothing left to do here.
  - ~~**(3)** `stack/align.py:407,466,161` — `_apply_subpixel_shift_windowed` shifts a window padded only `pad=2`
    px while the sub-pixel correction is capped at ±5 px, so a frame legitimately needing a 3–5 px shift can
    lose a thin strip of real edge data (coverage reduction at frame edges, **not** wrong pixel values).~~
    — **FIXED v0.135.3** (Builder 2026-07-16, branch `claude/pensive-faraday-5rsa35`; regression-tested).
    Took the filed remedy ("widen the window pad to ≥ the shift cap"). The ±5 px cap is now a named module
    constant `SUBPIXEL_SHIFT_CAP_PX = 5` (used by both `_apply_subpixel_shift` and `_apply_subpixel_shift_windowed`
    in place of the two magic `5.0` literals), and `reproject_rgb_windowed` gained a `pad` parameter (default 2,
    threaded to `_footprint_bbox_on_canvas`). `align_one` computes `will_refine` once and, when a sub-pixel
    refine will actually run (`subpixel_refine` **and** a ref patch is present), reprojects the window with
    `pad=SUBPIXEL_SHIFT_CAP_PX` instead of 2 — so a shift up to the cap only *translates* the footprint inside
    the (uncovered/NaN) pad border rather than pushing its trailing rows off the window edge. When refinement
    won't run, the pad stays 2, so the default install (`subpixel_refine` off) is **byte-for-byte unchanged**
    (window size, origin, and pixels identical). Additive, upgrade-safe: no config/DB/API-shape/default change,
    off the memory-bounded concern (a 3-px-wider window is a handful of NaN pixels). Regressions in
    `tests/test_subpixel_align.py`: `test_reproject_windowed_honours_pad` (the pad param widens the window +6 px
    each dim, moves the origin out 3 px, and the extra border is NaN), `test_align_one_widens_the_window_when_refining`
    (drives the real `align_one` end-to-end: refine-active window is +6 px each dim vs the plain window —
    fail-before both were pad=2 so identical), and `test_windowed_refine_pad_preserves_trailing_edge_coverage`
    (a ~4 px shift clips the footprint's trailing bright band off a 2-px-padded window but preserves it on a
    5-px-padded one). Severity: coverage loss at frame edges (image-quality/data-integrity), only with the
    off-by-default refine on and near-cap shifts, well-mitigated in a dithered stack. Confidence: reproduced
    (via the windowed-shift repro) + fixed. Latent gap (4) (test-only CPU↔GPU `cval` at `inset=0`) left as
    informational — the production windowed path never samples out-of-bounds inside the valid region.
  - **(4)** `stack/align.py:261` / non-windowed `reproject_rgb` — a CPU(`cval=nan`)↔GPU(`cval=0.0`) boundary-pixel
    discrepancy at `inset=0`. **Test-only path** (`reproject_rgb`/`_apply_subpixel_shift` are exercised only by
    `tests/`); the production windowed path uses `inset=3` and never samples out-of-bounds inside the valid
    region. Informational.
- Expand `docs/` (webapp.md) to cover calibration, mono/LRGB, auth. (S)
- `npm audit` still reports `esbuild`≤0.24.2/`vite`≤6.4.2/`vitest`≤3.2.5
  (moderate — dev server only, not the production build) after this run's
  `react-router`/`form-data` fix. `npm audit fix --force` wants `vite@8`,
  a real major-version bump across the toolchain (config changes, full
  suite re-verification) — needs a deliberate dedicated pass per
  `AGENTS.md`'s major-dependency-bump sign-off rule, not a blind
  `--force`. (M)

---

## Deprioritised — do NOT invest further (niche for an OSC Seestar owner)
Leave what exists working; don't extend or add to it. Only touch these to fix an
outright bug in existing behaviour, never to add capability.
- Mono / LRGB / **channel combine** (incl. cross-canvas reprojection), narrowband,
  and other filtered/pro-astro features. The owner shoots OSC and gets no value
  from these; they've already absorbed too much effort.

---

## Needs owner sign-off (do NOT start autonomously)
### The owner's one-sitting list (consolidated 2026-09-08 — every gate in this file, in one place)

> ## ✅ OWNER ANSWERED FOUR OF THESE — 2026-09-08. Read before picking anything from the list below.
>
> **Q1 — Auto-edit the walk-away picture too? → YES, _with a condition_.** The owner's words:
> *"yes, but should be easy to override with manual settings."* So `auto_edit_on_autostack` may default
> **on** once its prerequisites have shipped — **but the override is part of the feature, not a follow-up.**
> Do not ship the default flip without it. Concretely, before it goes on: a plainly-labelled Settings switch
> that turns it off; a per-target way to opt out that survives the next night (the walk-away chain must
> honour a target's saved preference, the way `_stack_target` already honours saved stack options); and a
> saved/edited recipe must **never** be overwritten by the unattended pass. The owner has been bitten by
> an on-by-default reframing before (the v0.226.0 auto-crop), so the switch must be findable **before** the
> first surprise, not after — name it in the Settings copy alongside Auto-stack's three guards.
>
> **Q3 — "Do you still see a multicolour grid?" → CANNOT ANSWER YET: he has not deployed.** He is running a
> build older than the mosaic/colour fixes. **Do not treat silence as "clean" and do not close the colour-chain
> bisect** — it stays gated, and the question gets re-asked after he next deploys. Anything that claims the
> colour chain is verified on his real data is claiming something nobody has checked.
>
> **Q4 (list item 15) — Dependencies and network → RESOLVED, PERMANENTLY: the app stays LOCAL.** Owner:
> *"let's stick with it being local."* **This is now a standing rule in `AGENTS.md` §1 Owner Facts, not a
> gate** — stop asking. Declined outright: outbound weather for Tonight, SIMBAD identification from the
> webapp, satellite-pass forecasts, a StarNet-class model, and anything needing a periodic data refresh.
> **Strike those entries rather than leaving them gated** — a gated entry invites a future run to re-ask a
> settled question. Bundled offline data remains fine. **Not settled by this:** `astroalign` for the
> WCS-free fallback, which is an offline *dependency* question and still needs its own sign-off per §10.
>
> **Q5 (list item 9) — Skip folders named `batch_stack_tmp` at scan time? → YES, skip.** This is the stray
> folder from the owner's real `\\TRUENAS\astro` listing — another program's scratch directory, confirmed
> not created by this app. Implement it as the **name-pattern skip the earlier entry deliberately did not
> blind-add** (`classify_seestar_junk_target` already grew a `temp_folder` verdict in v0.319.6 for the
> *cleanup* side; this is the *scan-time* half). Keep it conservative and evidence-based: skip the folder,
> say so in the scan's skipped-folders report (v0.381.0 already surfaces those on the Library page with a
> one-click "bring it in"), and make it recoverable — the owner must be able to ingest it anyway if a future
> folder happens to share the name.
>
> **Still unanswered and still worth asking** (unchanged below): the Settings → Maintenance screenshot,
> which alone unblocks three image-quality gates (list item 5) — it was asked in a way the owner found
> unclear, so **re-ask it plainly: "open Settings → Maintenance and screenshot the two self-check lines"**,
> and note it only carries information after a week or so of Process runs.

> Everything below is waiting on **one** thing only the owner can supply: a decision, a screenshot, a
> command's output, or a folder name. He has answered every gate put to him so far (a folder listing, an
> `ffprobe`, two decisions); the constraint was that they were scattered. Answer in any order; each answer
> unblocks the named entry. Ranked by what the answer is worth. *(Curated by the backlog-readiness run; a
> Scout keeps this list current — when a gate is answered, move the answer into the entry and strike the row.)*

1. ~~**Auto-edit the walk-away picture too?**~~ — **ANSWERED YES 2026-09-08 and SHIPPED in v0.395.0,
   with the condition, not after it.** `auto_edit_on_autostack` defaults **on** for fresh installs (an
   existing `config.json` keeps its stored value, per §9 — so this is item 2's sibling: the owner flips his
   own switch). The condition ships in the same commit: a per-target override stored in `project_meta`
   (`webapp/auto_edit_pref`) that the unattended pass honours and that survives the night, offered as a link
   under any picture the app finished; a guard that never writes over a saved recipe; and Settings copy that
   names every way out. Nothing left to ask.
2. **Flip Auto-stack on yourself — the default flip has now shipped (v0.391.0), and as of v0.404.0 the app
   *asks* you to.** The Dashboard's notice board now carries "Your subs came in, but nothing was stacked"
   with a one-click **Turn on auto-stack** button, on any night it captured and stacked nothing — so this no
   longer depends on the owner reading this list. It is still his click to make; the row stays until he makes
   it. Settings → "Auto-stack".
   A *new* install gets it on; yours cannot, because `state/config.json` carries an explicit
   `"auto_stack": false` that no upgrade may overwrite (the file cannot tell a value you set from a value the
   app dumped, so flipping it would be the AGENTS.md §9 breach). This is a one-click job and nothing else is
   waiting on it. Worth: the whole walk-away path. *(The one item under "REQUIRES MANUAL OWNER ACTION".)*
3. **Do you still see a multicolour grid on any mosaic on a current build?** The v0.225.0 fix rated its own
   root cause "medium confidence as the *sole* contributor". **Answer:** yes/no, and the target's name.
   Unblocks: "bisect the rest of the v0.158→v0.220 colour chain" under "Bugs". Worth: closes or reopens the
   oldest mosaic complaint.
4. **One real solved sub's `.wcs` sidecar, or the `wcs_json` of any solved frame.** Unblocks the sky-atlas
   `CROTA2 → CD` sign check under "Bugs" (fallback path only; low impact). **Command:** on the NAS,
   `sqlite3 <library>/targets/<any target>/project.sqlite "select wcs_json from frames where wcs_json is not
   null limit 1"`, or paste one ASTAP `.wcs` file. Worth: one sign flip, or one entry closed.
5. **Settings → Maintenance: a screenshot of the two self-check lines** (the Auto colour self-check,
   v0.36x, and the highlight line, v0.382.0) after a week of Process runs. Unblocks *three* real-data gates
   at once: "does Auto's SCNR tint a neutral background magenta?", "Hold back highlights is near a no-op
   on the frames that need it", and the "How's my stack?" highlight-clip cue — all under "Image quality".
   Worth: the three oldest image-quality deferrals, answered from numbers the app already collects.
6. **Your M42 (or M31) stack, or a screenshot of its core in the editor with "Hold back highlights" at
   max.** Unblocks the highlight-knee redesign ("Image quality", the v0.240.0 measurement). Worth: blown cores
   on the brightest targets a beginner shoots first.
7. **On a cloudy night, does the "locating" stage run unreasonably long?** ASTAP's 3-rung ladder can spend
   3× `astap_timeout_s` per unsolvable sub. **Question:** *would you trade fewer rescue attempts on hard
   frames for a hard per-frame time limit (yes/no)?* Unblocks the ladder-budget half under "Bugs".
8. **Have you ever seen new subs sit un-ingested until you pressed Scan?** Unblocks the watcher clock-skew
   hardening note under "Bugs" (a NAS clock ahead of the app's). **Answer:** yes/no.
9. ~~**Skip folders named `batch_stack_tmp` at scan time?**~~ — **ANSWERED YES 2026-09-08 and SHIPPED in
   v0.393.0.** The scanner skips it, the skipped-folders report says so in its own words, and the report's
   "bring it in" still ingests it — the owner's condition. Nothing left to ask.
10. **The mixed-pointing guard (`mixed_pointing_guard`, off): do you want it on?** Unblocks the O(n²)
    preflight speed-up under "Performance", which only matters if the guard runs. **Answer:** yes/no.
11. **A target with an edge-on galaxy or a bright elongated nebula (NGC 891, NGC 4565, M82), and whether
    any of its subs were flagged "streak".** Unblocks the per-frame trail-vs-object detector under "Image
    quality" (needs real data to tune). **Command:** the target's Frames table filtered to "rejected" —
    a screenshot is enough.
12. **A faint target ASTAP struggles with** (the "only N of M located" case) — its name, and a yes/no to
    trying the off-by-default `astap_bootstrap_solve` on it. Unblocks "validate the stack-then-solve
    bootstrap on real faint-field data" under "Autonomy". Worth: the #1 thin-stack complaint, answered on
    real subs. *(Narrowed 2026-09-11: this row used to unblock "Try harder to locate these" too — that
    **shipped as v0.427.0**, needing no answer, because the button runs the already-measured bootstrap
    rather than a new ASTAP sensitivity profile. He can now press it on that target himself, from the
    un-located bucket of "Why some frames were left out"; what is still worth asking is which target, and
    what the rescue made of it.)*
13. **A heavy-nebulosity stack (North America, Rosette).** Unblocks the SExtractor skew-guard confidence
    check under "Image quality" — a log read, no code change unless it fails.
14. **Three yes/no's on residue from shipped features:** a 9:16 portrait zoom clip for Reels/Shorts? A
    noise-delta *picture* beside the "Did it get better?" sentence? Auto-*apply* the classified object
    preset instead of offering it as a chip? Each is small; none is built until wanted.
15. **One offline dependency: `astroalign` for the WCS-free star-registration fallback?** *(Cut down
    2026-09-11 — the four networked items this row used to bundle with it were **declined outright** by
    Q4's standing LOCAL policy, so asking about them again would re-open a settled question. What is left
    is not a network question at all.)* **Answer:** yes/no to adding one pure-Python offline package to the
    image so a faint field whose subs never plate-solve can still be registered against each other.
16. **De-duplicate the 11 historical mosaic target pairs (observer [#878](https://github.com/JimmyeJones/astrostack/issues/878)).**
    The naming collision that minted them is **closed** — recurrence has been dormant since 2026-07-03,
    confirmed on live data (see the #878 entry under "Bugs"). But the 11 existing `<T>_mosaic-<hex>` /
    `<T>_mosaic_sub` pairs still register 41,732 frames twice, which cost ~24.9 h of redundant re-stack time
    on the last full reprocess and shows two Library entries per mosaic. Reconciling them is a **merge
    migration** that rewrites on-disk target layout (§9) and must never touch `incoming/` (§10), so it needs
    your OK before an agent runs it. **Decision:** merge each pair, keeping the more-complete target? *(The
    observer measured no urgency — nothing new has been duplicated since this was filed; this is one-off
    cleanup, not a live leak.)* **Worth:** removes the redundant re-stack time and the duplicate wall entries.

- ~~**Satellite/aircraft-trail forecast for the Tonight planner (opt-in; needs a data source).**~~ —
  **DECLINED 2026-09-08 by the owner's standing LOCAL policy (AGENTS.md §1 Owner Facts, Q4); struck
  2026-09-11 as that answer instructed.** Predicting passes needs current orbital elements (TLEs) and a
  periodic refresh, i.e. the running install reaching the internet — which is the one thing the answer
  ruled out, permanently and as a policy rather than a per-feature gate. **Do not re-file, re-spec or
  re-ask it**; the idea was good and it is simply not for this install. Kept as one struck line rather
  than deleted so a future run recognises it as answered rather than missing. (The *post-hoc* half — "the
  trails in your subs weren't a mistake; stacking removed them" — needs no network and is already served
  by the shipped rejection overlay and its caption.)
- ~~AI star removal (StarNet-class ONNX).~~ — **DECLINED 2026-09-08 by the same answer** (named in it
  explicitly, as both a network/model-download question and a heavy ML runtime); struck 2026-09-11. Do not
  re-file or re-ask.
- Anything that exposes the app publicly, changes auth defaults (e.g. turning auth
  on by default), or is otherwise hard to reverse.
- Live capture / real-time Seestar streaming integrations (explicitly de-scoped).
- ~~**Surface SIMBAD target identification in the headless webapp (opt-in).**~~ — **DECLINED 2026-09-08 by
  the owner's standing LOCAL policy (AGENTS.md §1 Owner Facts, Q4), which names it; struck 2026-09-11 as
  that answer instructed.** It makes an outward call from the live install to CDS/SIMBAD, and the policy is
  a standing rule rather than a per-feature gate. **Do not re-file or re-ask.** The beginner value it was
  after — "you're imaging M 42, an emission nebula" plus the background-flatten hint — is already served
  **offline** by the bundled catalogues: `seestack/objectinfo.py::identify_object` feeds the Target page's
  object card and its blurb, and `seestack/bg_advice.py` supplies the flatten nudge. If anything is still
  missing there, it is a copy or wiring task on bundled data, not a network one.

_(Normal, tested changes merge to the default branch automatically — see
AGENTS.md §8. Only the items above need a human's OK first.)_

---

## Shipped

_Newest first. One line each: what + commit/PR. Entries that had grown to paragraphs were cut to one line on
2026-09-08; their full text is in [`SHIPPED.md`](SHIPPED.md) under that date's heading — search the version._
- **v0.478.2** — 🟡 PRIORITY 3 (disk hygiene on the RAM/disk-capped NAS), the **second** drifted hand mirror the v0.478.1 lever turned up: **the cross-run "night after night" deepening reel was not a registered run artefact, so deleting a stack left the reel and its signature on disk for good.** `RUN_ARTEFACT_SUFFIXES` is the one list every operation on a run's whole file set reads — archive on re-stack, carry on merge, and **delete**, where `delete_run_artifacts`' own docstring says "reclaiming space is the entire point" — and `_build_or_get_deepening_reel` spelled its three filenames by hand instead. **Reproduced before fixing:** a run deleted through the real `delete_run_artifacts` left `master_deepening.webp` + `.sig` behind, **2.0 MB** on a synthetic run; a real reel is a 1024 px animation of *every* stack a target has, i.e. the second-largest orphan the output tree can hold after `_share.png`. The writer and the resolver now take their names **from the table**, so a reel nothing cleans up cannot be spelled again. **Registering it alone would have been a regression, and that half is here too:** a reel describes the target's whole *series*, so renaming it onto each superseded basename would leave one stale copy per re-stack — new `SERIES_ARTEFACTS` makes an archive **remove** it (a cache, rebuilt on the next request) and a merge **skip** it (the destination's series is a different series), while a delete reclaims it. **The durable half:** `tests/test_run_artefact_coverage.py` scans `seestack/` + `webapp/` for every `f"{basename}_<name>.<ext>"` literal and requires the suffix to be registered — the static complement to `test_run_purge`'s existing guard, which runs the *writer* and so structurally cannot see a cache written later by the webapp. One `_EXEMPT` entry with its reason (`_fullres.png` is a `Content-Disposition` download name, never a file), plus a test that a stale exemption cannot hide the next one. Tests +5; **two fail before** on exactly `{'_deepening.webp', '_deepening.png', '_deepening.sig'}` and on the files left behind by the delete. One existing assertion in `test_output_archive.py` deliberately updated — `len(archived) == len(RUN_ARTEFACT_SUFFIXES)` became `- len(SERIES_ARTEFACTS)`, with the rule it was pinning ("nothing is left at the canonical name") kept and the new rule asserted beside it. Engine + one router; no config, schema, on-disk *layout*, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.478.1** — 🟡 PRIORITY 3 (friendliness), and the answer to the question the v0.477.2 run left behind (*which other hand-mirrored list has nothing checking it?*): **two reject reasons the app writes were shown to the owner as their own internal identifier.** `rejectReasonLabel` is a hand mirror of a vocabulary owned by the Python that stores it, and `auto:seestar_output` / `auto:file_missing` had no branch of their own — so the frames-table badge read **"Auto: seestar_output"** and **"Auto: file_missing"**, snake_case identifiers on the one surface that explains why a sub was left out, both live on the owner's install. Now *"Seestar's own stack"* and *"File missing"*, deliberately short (this badge is `flexShrink: 0` in a 420 px row — v0.477.1's clipping mechanism one element along). The same drift on the sibling surface is fixed with it: the grouped breakdown bucketed `auto:seestar_output` as *"Left out for other reasons"* and now has its own reassuring bucket. **The durable half is a drift test in the shape v0.477.2 used for the route table** — `tests/test_reject_reason_labels.py` derives the vocabulary from the code that *writes* it (`ast`, not grep, so a docstring is not mistaken for a write) and requires each exact reason to have a label **of its own**, since being swallowed by a broader prefix is the failure it catches. Tests +13; **three fail before** (scratch reverts, run). Additive throughout; no config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.478.0** — 🟢 PRIORITY 3 (friendliness / enjoy-share), found on the **first** dogfood pass that ever opened `/show` (v0.477.2, an hour earlier): **"Show and tell" told a beginner with their first finished picture that there was nothing to show.** The page whose whole promise is *"point a screen at it and it plays"* says *"Once you've finished stacking **a target**"* — singular, and false: it is built from `/api/gallery/best`, which self-hides below `BEST_PICTURES_MIN = 2`. That floor is well argued *for the wall* (its own comment: *"with one picture there's nothing to curate"*) and the argument is about **curating**; a slideshow plays them one at a time, which one picture does perfectly well. Worse than the empty state: once the owner had *also* shot the Moon the show **played** and silently left the nebula out, the stills coming from a different endpoint with no such floor. And the way in was gone too — `/show` is not in the nav, so it is reached from `/best`'s "Play slideshow" button, which asked `hasAnythingToShow(items, …)` where `items` is *the wall's* list, empty below the same floor (its own comment had the right instinct and the wrong list). Fixed with two additive pieces: **`min_targets`** (query param, `ge=1` so it can only lower a floor, default `BEST_PICTURES_MIN` so `/best` and every existing caller are byte-identical; the show asks for 1 **on its own react-query key**, since one cache entry for two floors would let whichever page loaded first decide what the other shows) and **`n_finished`** (defaulted response field, reported whichever way the floor goes, so the *button* can answer its own question without a second whole-library request — this endpoint opens every project and the owner has 104 targets). The empty-state copy needed no change: with the floor at one it became true. Tests +3 Python / +4 frontend, **six fail before** (scratch reverts, run). Upgrade-safe (§9): one optional query param, one defaulted field; an older backend omitting it reads as today's behaviour. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.477.3** — 🟡 PRIORITY 3 (friendliness / trust), found on the **first** dogfood pass that ever opened `/sky-so-far/:year` (v0.477.2, an hour earlier): **"Your year under the stars" named the same targets twice, in two stacked cards, and the second one linked nowhere.** *"First light in 2024"* (chips that link to the target) sat directly above *"What you pointed at"* (the same names as dead badges). Two different facts on a year with repeat visits — **one** fact on a year where everything was new, which is the guaranteed shape of a beginner's **first** year, i.e. of the reader this page is written for. The class this repo already has a name for, and this page already answers it **for its nights** one function up: `yearNightCards` folds the longest and sharpest night into one card when they are the same night, with a docstring reading *"Rendered as two cards it read as the page repeating itself"*. New pure `yourYear.yearTargetCards` does the same for the targets — one card when every target was a first light, keeping the richer framing and saying the thing two cards could not (*"All 4 objects you pointed at in 2026 were ones you'd never imaged before"*; singular gets its own sentence). **Nothing removed** (§1): every name is still on screen, once, and in the folded case each now carries its link instead of being a dead badge; a year with any repeat visit renders exactly as it did. Folding requires **set equality**, not containment, so an inconsistent payload cannot quietly fold a name out of view. Tests +6 pure / +2 rendered, **one fails before** (scratch revert, run). Frontend-only; no API, config, schema, on-disk or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.477.2** — ⚪ Infra / maintainability (in service of not missing bugs): **three registered routes had never been in front of a browser, because the dogfood probe's `ROUTES` is a hand-mirror of `frontend/src/main.tsx`.** `/live` — *a nav entry*, and the one page whose own docstring says it is "meant to be left open on a phone for hours" — plus `/show` (reached from a button, never the nav) and `/sky-so-far/:year` (the year is a property of the library, so like `/compare` it cannot be a constant). Same structural hole as the missing observing site, the empty `incoming/`, the click-only Compare comparators and the 1:1 editor preview, and it paid the same way: **both new pages produced a real finding on the first pass that opened them** (v0.477.3 and v0.478.0). New `yearRoute()` beside `compareRoute()`, asking the year the same way `YourYearCard` does and resolving it by `yourYear.defaultRecapYear`'s own rule; `""` on a library with no nights, so `--empty` is unaffected. The durable half is **`tests/test_dogfood_route_coverage.py`**: it parses the router children out of `main.tsx` and every route-shaped literal out of the probe, normalises both (`:param` and `${VAR}` alike → `*`), and requires each registered route to be reachable or listed in a tiny `_EXEMPT` map **with its reason** — plus a second test that a stale exemption cannot sit there hiding the next one. **Fails before** on exactly `['live', 'show', 'sky-so-far/*']`. Tooling + tests only; no app code touched. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.477.1** — 🟡 PRIORITY 3 (friendliness), found by the `--closing` flag's **first** pass an hour after v0.477.0 shipped it, and measured in a real browser either side: **three nudge cards chipped a target's name and then hid the fact beside it.** `MergeSuggestionsCard`, `CleanupSuggestionsCard` and `LastNightCard` each render `"<target name> · <fact>"` inside a Mantine `Badge` — a *sentence* in a `height: var(--badge-height); overflow: hidden` box whose label is `nowrap` + `ellipsis`. At 420 px the Alert body is **306 px**, the label box **288 px**, and the two strings wanted **299 px** and **317 px**, so the tail — on the merge nudge, how many subs and how many hours each folder holds, i.e. the entire basis of the decision it is asking for — was ellipsised away inside the chip with **no scroll and no `title`** to reach it. Fourth instance of the mechanism `frontend/src/badgeFit.ts` exists for (v0.434.1, v0.436.2, v0.472.3) and the first its existing rule could not fix: `NO_SHRINK`'s `max-content` is right for a badge in a **table**, where widening the table is honest because the table scrolls, and wrong in an `Alert` body that does not — it would move the same lost value one element outwards. New shared `badgeFit.WRAPPING_BADGE` lets the chip grow **downwards** instead (root height auto, label `white-space: normal`); measured after, both labels **288 px of 288 px** on two lines, nothing overflowing. Nothing removed, no copy changed. Tests +1 vitest case (**fails before**, on `"Lagoon and Trifid Nebulae mosaic_sub"` — the shape the owner's own `<T>_mosaic_sub` duplicates take) and +2 assertions on the sibling cards' existing tests. Frontend-only; no API, config, schema, on-disk or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.477.0** — ⚪ Infra / maintainability (in service of not missing bugs), the backlog's own preferred shape (a) for *"the season-closing card is the next self-hiding surface no dogfood pass can reach"*: **`/tonight`'s fourth prescriptive card had never been rendered in a browser, and unlike every other such hole there was no setting that could fix it** — a season closes as a function of the target's RA against the **date**, and both bundled samples sit at M 42, whose northern-autumn season is *opening*. So the card whose whole argument is that its answer expires was pinned by jsdom alone, and the one bug found in it (v0.476.0) had to be read out of the code. New pure `seestack/nightplan.py::closing_sky_position` probes a 48-step RA grid at five declinations **through `season_closing` itself** — so the demo and the card cannot disagree about what "closing" means — and answers `None` rather than a plausible pair when there is no darkness to compare (78°N in midsummer). New fifth `POST /api/sample` shape `"closing"` seeds a **pair** of targets at **one** sky position with **1 min** and **1.5 h** kept: a pair because the card's job is to say what the season ending will *cost*, which is a function of depth (this entry's own "range of `total_exposure_s`" requirement), and one position so depth is the *only* variable — measured on load, `noise_gain` 0.872 against 0.225, shallow first, which is v0.476.0's ranking finally rendered — **1° apart in declination**, not identical, because the first build's identical pair correctly raised the merge nudge's "Same object in more than one folder?" on every Library screenshot the flag takes (caught by the flag's own first pass; a flag must seed the state it is *for* and no other). Not stacked (the card reads the registry), ~7 s. `scripts/agent-dogfood.sh --closing` drives it and prints `location_source`, the exact `n_closing` and every row, saying **"NOTHING IS CLOSING — do not read it as CLEAN"** on an empty list. The Care note is honoured both ways: the coordinates are a *target's*, chosen by the caller, and every other shape now **refuses** a centre rather than ignoring one, so the bit-identical pixels every recorded baseline rests on cannot move by accident. Tests +14 Python (the engine ones pin the *property* — on three dates × three sites the position is one `season_closing` reports, comfortably inside the scan — plus the end-to-end path the flag walks). Fully additive: three optional request fields, three defaulted response fields, no config/schema/on-disk/default/API-shape change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.476.0** — 🟠 PRIORITY 2–3 (autonomy / friendliness), a bug the Builder verified and **measured** itself: **"Shoot these before they're gone" chose which of your targets to even look at by keeping the ones it would then tell you to let go.** `seestack/nightplan.py::season_closing` borrowed `plan_week`'s `WEEK_MAX_TARGETS = 40` cap *and its selection key* — `-(total_exposure_s)`, the forty targets with the **most** integration on them. That key is well-argued for the week plan ("finish what I've got" must not drop the project you have spent nights on) and is exactly backwards for this card, which **ranks** by `noise_gain_from_more_time` so that *"the least-finished of two targets leaving in the same week is named first"* (its own docstring), and whose row copy says in as many words that *"a target already 10 h deep reads, correctly, as one that can be let go"*. Selecting on one key and ranking on its opposite. **Measured on a 104-target library** (the owner has 104): the cap reported **7 of the 18** targets that were leaving; every one shown had **12.7–19.1 h** on it and every one hidden had **0.3–9.4 h**; and one of the three targets in its **last week** was hidden — the one the Dashboard's "Last chance this year" interrupt (`closingUrgentSentence`, `weeks_left <= 1`) would have named first. **The cap was also buying almost nothing**, exactly as `season_closing`'s own docstring says (*"the cost scales with the horizon, not with the library"*): the work per sampled night is one dark-window search, one Moon ephemeris and one vectorised alt/az batch, measured at **1.96 s for 1 target, 1.96 s for 40, 1.99 s for 104, 2.18 s for 400, 2.53 s for 1,000**. So the one cap is now **two**, each about the thing it is actually for: new `SEASON_MAX_TARGETS = 400` bounds the **scan** (cost only, past any hand-built library), and new `CLOSING_MAX_ROWS = 40` bounds the **list** at exactly the number of rows the endpoint could already return — so widening the scan cannot make the card longer than it is today on a page the owner already calls busy. When the scan cap does bite it now keeps the **least**-finished, the same key the ranking uses, documented as the deliberate mirror of `plan_week`'s. New `n_closing` carries the exact total so `closingHeadline` says "17 of your targets" rather than counting the rows it happened to be sent; absent on an older backend, where the list *is* the total. Tests +6 (3 Python engine, 1 webapp, 2 vitest), **three fail before** (scratch reverts, run). Additive response field only — no config, schema, migration, on-disk, default or API-shape change; `plan_week` is untouched.
- **v0.475.3** — 🟡 PRIORITY 2–3 (autonomy / friendliness), a bug the Builder verified itself in the code: **the health card diagnosed registration smear and then prescribed a set of subs that only exists once the cure is already on.** `stackhealth`'s `soft_stars` note — "your stacked stars came out fatter than the subs that made them, so the combine, not the sky, softened them" — ended, on *every* run, with *"a steadier mount, or **re-solving the roughly-aligned subs**, keeps them tight."* Those subs are a specific population with their own column: `n_roughly_aligned` counts the frames **sub-pixel refine** had to leave unshifted, `stacker` persists it only under `eff.subpixel_refine and not eff.drizzle and refine_active`, `StackOptions.subpixel_refine` defaults **False** and nothing turns it on — so on a default install the column is NULL, the sibling `roughly_aligned` note is silent *by design*, and the card sent the reader after frames the app had never shown them and never would. Meanwhile the app's own remedy for that exact diagnosis — *"a phase-correlation pass that nudges each frame by a fraction of a pixel… for slightly tighter stars"* — sat unnamed behind the Stack form's collapsed **Advanced** disclosure. Now the diagnosis is unchanged and the **cure** is chosen by what the run did: new pure `stackhealth.run_option_flag` (three states — `True`/`False`/*can't say*, deliberately unlike `_run_sigma_kappa`'s default-guessing fallback) and `_refine_is_the_open_lever`, so the switch is named only when the run says refine was off **and** it did not drizzle (drizzle uses a pixmap and never runs the refine step). `HealthNote.action` gains `"subpixel_refine"`, wired to `/targets/<safe>/stack?open=advanced` — and the Stack form's Advanced accordion is now controlled off that parameter, because a bare link lands on a long form with the answer folded away (the gap `printBiggerAction` already exists for). Tests +5 Python / +3 vitest, **two fail before** (scratch reverts, run). Fully additive: no config, schema, migration, on-disk, default or API-shape change, and `subpixel_refine` itself stays off. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.475.2** — 🟠 PRIORITY 1 (editor correctness), the `EditContext.op_notes` entry filed 2026-09-03 under "Infra / maintainability": **a recipe may carry the same op twice, and its outcome notes could not.** `op_notes` was keyed by op **id** where its siblings `fitted` and `field_deltas` have always been keyed by the recipe op’s **uid** — so a second `tone.color_calibrate` overwrote the first’s note, and the editor’s preview-vs-export advisory (*"the saved picture’s colour will differ a little from this preview"*, `colorCalProxyFallbackCaption`) **vanished** whenever the *first* op was the one that fell back on the decimated proxy. The entry’s own "check first" is what sized it: `Editor.tsx::addOp` has no duplicate guard, so two **Color calibration** ops is two clicks. New `EditContext.record_note` / `notes_for` key a note to the instance through the same `_fit_key` the fits use, and new pure `seestack/edit/opnotes.py::merge_color_cal` is the one place that decides what "more than one" means — the **last** note with a mode for the balance the picture carries, `any()` for the parity flag, the same rule the sibling `star_reduce_preview_overstates` warning already applies across every `stars.reduce` op. Both readers (the live histogram, the walk-away auto-edit’s History stamp) go through it, so they cannot describe one render differently. **Bit-for-bit unchanged on every recipe the app renders today**, Auto included; no response shape, config, schema, on-disk or default change. Tests +9, one fails before (the real op run twice through `apply_recipe`). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.475.1** — 🟠 PRIORITY 1-adjacent (trust), second half of observer issue [#967](https://github.com/JimmyeJones/astrostack/issues/967): **the sub that stands in for "one raw frame" was picked on sharpness alone, and sharpness is not sky noise.** Sky shot noise is the dominant term in the σ the badge divides, and it is uncorrelated with FWHM — so a target whose sharpest frame was also one of its brightest-sky frames inflated the number by however much brighter that sky was (observer: a reference σ **2.53×** the sample median, a **188×** badge on 5,460 subs where √N = 73.9). `reference_sub_from_frames` now takes the sharpest frame **among the middle half of the target's measured `sky_adu_median`** (`_typical_sky_frames`) — an interquartile band rather than a tolerance, so there is no constant to get wrong, it survives a bimodal (moonlit/dark) target, and it picks the dominant *exposure* for free, since sky scales with exposure and a 3× longer sub carries √3 the sky noise. One-sided by construction: unchanged below 10 measured skies, unchanged with none, and an empty band falls back to the whole pool. `FrameHealth` gains `sky_adu_median` so the health card and the reveal endpoint make the same pick — a disagreement would make every stamped measurement a permanent miss. Tests +8, three fail before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.475.0** — 🟠 PRIORITY 1-adjacent (trust), observer issue [#967](https://github.com/JimmyeJones/astrostack/issues/967) verified and fixed: **the "stacking cut your noise ~N×" badge read above √N because neither side has independent pixels.** `noise_ratio._diff_sigma` took σ from the MAD of *adjacent*-pixel differences — `2σ²` only for independent neighbours — while the sub arrives through `bilinear_debayer` and the master through a registration warp and, on most runs, a drizzle kernel. Measured against **ground truth** on a debayer+warp fixture: the old estimator read **+9 %** on a native master and **+119 %** on a 2×-drizzled one (17.2× against a true 7.9×), and the error direction is toward *silence* — `noise_vs_expected` only nudges on a **low** number, so an underperforming stack had its one noise diagnostic withheld. σ is now a **second difference at a lag chosen from the data** (`_lag_sigma`, `Var = 6σ²`, exactly 0 on a linear ramp so a gradient cannot creep in at long lag), walked over L = 1…16 per side until the estimate plateaus — measured, a native master plateaus at 4 and a drizzled one at 8. New reads 0.97× / 0.93× truth. **Faster, not slower** (157 → 81 ms on a 1024² crop, `_MAX_PAIRS`). `_NOISE_RATIO_CACHE_VERSION` 1 → 2, since the stamp fingerprints the inputs and not the estimator. Tests +4, three fail before; the pre-existing `test_noise_ratio_expectation.py` is green either way, exactly as the entry predicted, because its fixture has independent pixels. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.474.0** — 🟡 PRIORITY 3 (friendliness / trust), observer issue [#968](https://github.com/JimmyeJones/astrostack/issues/968) verified in the code and fixed: **auto-grade has two 25 % rails and set one flag from both**, so a mosaic that hit its *per-panel* rail — a count limit on one patch of sky — was shown the target-wide sentence (*"this looks like a rough session… consider a conservative pass, or review the night's data"*). Measured on the owner's library: **7 of the 21 targets showing that banner flagged too few frames to have reached the target-wide cap at all**, one of them raising it off a **single** withheld frame at an 8.0 % flag rate. And the remedy is the wrong lever twice over — a conservative pass *raises* the z threshold, which shrinks the flagged set and cannot release what a count limit withheld, and the withheld frames are concentrated on **panels**, not on a night. Fixed by splitting the flag (`GradeReport.capped_overall` / `capped_panels` / `withheld_per_panel`, with `capped` left as their union so no existing reader changes) and putting the copy in **one shared pure `gradeCap.gradeCapNotice`** the Target page and the Stack form both call, so they cannot tell different stories about one report. Tests +11, four fail before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.473.1** — 🟠 PRIORITY 4 + engine correctness, observer issue [#965](https://github.com/JimmyeJones/astrostack/issues/965) verified in the code and fixed: **the only plate-solve guard asked *where* a frame landed and never *at what scale*.** `mosaic._footprint_outlier_indices` is a median+MAD on the footprint **centre** — and a scale error is **zero at the centre by construction** and grows linearly to the corners, so a false solve that lands on the right patch of sky passed every guard and reprojected into the stack at the wrong scale, counted as a full contributor in `n_frames_used`, `total_exposure_s` and the coverage maps. The observer's control is the same file solved twice by the app itself (the #878 duplicates): two solves agreeing at the centre to **16″** put the corners **1,022″** apart. 178 of 89,443 accepted frames are beyond ±1 %, worst **+11.45 %**. Fixed with a new pure `mosaic._plate_scale_outlier_indices` run beside the footprint pass: ±1 % of the population's **own median** (no hardcoded optic, no header read, works on frames already in the library), **guarded by a consensus bar** — deliberately *not* a MAD test, because a spread set of plate scales means two instruments, which is a reason to say nothing rather than to widen the net. Own reject sentence via an additive `CanvasResult.scale_excluded_frame_ids`. Tests +10, three fail before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.473.0** — 🟠 PRIORITY 2 (autonomy / memory safety), observer issue [#966](https://github.com/JimmyeJones/astrostack/issues/966) verified in the code and fixed: **reprocess-all ran with `unattended=False`**, so all three of the engine's over-budget degrade levers were off for the one job that walks the whole library — on the owner's, for five days. Measured in his own `jobs` rows: **7 `MemoryError` refusals across 3 batches**, five distinct mosaics, every one a drizzle-with-rejection canvas whose message named a drizzle scale that would have fit, two of them near-misses of ~0.1 GB; projected library-wide, **17 of 83 targets refuse under `unattended=False` and 0 under `unattended=True`**. Root cause: `pipeline._stack_target` derived the posture from `auto`, and the two are different questions — `auto` is *"the user made no stacking choices"* (it re-defaults rejection and weighting, which a reprocess must never do to the owner's reused options), `unattended` is *"is anybody there to act on the advice?"*. Split into a separate keyword defaulting to `auto`, so every existing caller is byte-for-byte unchanged, and reprocess-all passes `unattended=True`. Tests +4, two fail before — including one pinning the *consequence*, the batch's own options through `stacker._afford_drizzle_reject`. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.472.3** — 🟢 PRIORITY 3 (friendliness), the defect **v0.472.2 shipped and the probe caught before it merged**: the new week-plan chip read *"Needs 3×3 mos…"* on a phone, **a 76 px box holding a 91 px word, with no scroll that could reach the rest**. Third instance of the one mechanism `frontend/src/badgeFit.ts` was written for (v0.434.1 on the Nights card, v0.436.2 on the Tonight score column): a Mantine `Badge` is `overflow: hidden; text-overflow: ellipsis`, so it contributes **no min-content width** and a squeezed table column ellipsises the value *inside* it — not a truncated label with the value elsewhere, the value itself, gone. The week table's "Point at" column is the narrowest on the page, and the card's own comment about its moon note had already recorded the same trap ("a badge truncates, and in this column on a phone the caution came out as *Moon 92%, up…*"). `style={NO_SHRINK}` — the shared rule, not a width picked against today's words — and a test pinning `min-width: max-content` on that badge, the same assertion the Tonight row's three badges already carry. **Measured either side on a real phone-width browser:** `1 thing(s) to look at` → `nothing overflowing, no console errors`, and `/tonight` **3,847 px → 3,718 px** (below the 3,834 px it measured *before* this run, because the un-shrunk chip had been squeezing the target names onto extra lines). Frontend-only, one style prop; no new test case — the assertion is added to the chip's own test, which is where a reader looks for it. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.472.2** — 🟢 PRIORITY 2/3 (autonomy + friendliness), found by a `--mosaic` dogfood pass that was mechanically CLEAN, reading the "what the TONIGHT page SAYS" block against the Target page's: **"Plan my week" named a target for each of the next seven nights and said nothing about how to shoot it.** The week table listed *Tonight / Tomorrow / Monday · Point at · Sample: Orion Nebula (M42)* while that target's own page said *"only about 20% of it made it in… shooting it in mosaic mode next session is the biggest win here"*. That is **exactly the gap v0.472.0 closed one card up the same page** — mosaic mode is a setting chosen on the scope *before* a session, so the row that says what to point at is the one place the advice can still be acted on — and the week card, which plans seven sessions rather than one, was not in that fix. `WeekTargetPick` now carries `framing`/`mosaic`, made by the **same** `framing_hint`/`mosaic_plan` calls against the **same** measured frame (`plan_week` gains a `field`, wired from the router's existing `_frame_field`), with the same `canvas_is_mosaic` stand-down — so the two cards on one page cannot badge one object two ways, which is what the engine and API tests assert (against `plan_tonight`'s own answer, never against a literal). The frontend reuses `framingRowBadge`, the tonight row's own helper. **One deliberate difference from that row:** the chip appears once per **target**, not once per night (`planweek.framingBadgeNights`) — a week where one target is best-placed on five nights would otherwise stack five identical "Needs 3×3 mosaic" chips down one column, which is the always-on repetition the standing "extremely busy" priority is about, and the name is already in every row. The week cache signature gains the frame field, the catalogue sizes and the mosaic flag, since all three can move without any of the acquisition numbers already in it moving. Additive optional fields only; no config, schema, on-disk, default, endpoint or ranking change, and a pick with no verdict renders exactly as it did. Tests +8 (3 engine, 2 API, 3 vitest) plus 2 pure-helper cases; **six fail before**, verified by scratch reverts of the engine half and the render. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.472.1** — 🟢 PRIORITY 3 (friendliness / trust), the contradiction **v0.472.0 itself created** and the Target page had already closed one screen over: **the planner row said "Plenty — try something new" an inch from "Needs 3×2 mosaic".** The readiness badge prices the integration the target has, which is the integration of the *framing it was shot at*; that was unambiguous while it was the only thing on the row with an opinion about the canvas, and v0.472.0 put a second one beside it. On an oversized object a beginner now read *you are done here* beside *you have a sixth of it*, on the one screen read while choosing what to point at. Fixed the way v0.444.2 fixed it on the Target page, reusing the machinery that fix added rather than inventing a second one: `integrationReadiness` has taken a `canvasScope` since then, and the planner row was simply the caller with no framing verdict to pass it. New pure `tonight.readinessFramingScope` reads the scope off the **same** `framing` the badge beside it is drawn from — so "have I shot enough?" and "will it fit in one frame?" cannot answer as if the other had not been asked — and `readinessRowBadge`/`readinessRowHint` pass it through. The number is unchanged (it is the honest goal for the canvas the owner has); what changes is that the *"plenty"* chip drops its **prescription** — "Plenty for this framing", leaving "shoot it wider" to the badge whose job that is — and every chip's hover gains the scope ("of ~6 h **for the framing you've shot**"). `IntegrationReadiness` now carries `canvasScope` so the chip asks the same question the sentence answered instead of keeping its own copy of the blank-scope rule. Only the `mosaic` level scopes anything — `tight` means it about fits, the same bar `framingIsFragment` sets — and a target already shot *as* a mosaic carries no verdict at all (`canvas_is_mosaic`), so its row is untouched by construction. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change, and a row with no framing verdict is byte-for-byte what it was (pinned). Tests +5 vitest, **one fails before** (verified by a scratch revert). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.472.0** — 🟢 PRIORITY 2/3 (autonomy + friendliness), found by a `--mosaic --calibration` dogfood pass that was mechanically CLEAN — the finding was in the block it prints, read across two screens: **the planner's "Needs 3×2 mosaic" badge vanished the moment the owner shot one frame of the object.** `/tonight` said *"Tonight · Sample: Orion Nebula (M42) · 87 min"* while that target's own page said *"it's bigger than one frame, so more time can't bring the rest in — shooting it in mosaic mode next session is the biggest win"*; mosaic mode is set on the scope **before** a session, so the advice was missing from the one screen read while pointing, on every session after the first. `nightplan.PlannedTarget.framing` was populated for catalog rows only — the third member of the family `difficulty` and `recentre_nudge` were already moved out of (both carried for library rows with that same argument spelled out in the same file). `LibraryTarget` now carries `size_arcmin`/`size_minor_arcmin` and `plan_tonight` makes **both** rows' verdicts with the same `framing_hint`/`mosaic_plan` calls and the same `field` — the size travels, never the verdict, because `_annotate_library_targets`' `identify_object` call passes no field and carrying its verdict would have put two rules on one table. The old comment's real half is kept as an explicit exception: a target already being shot as a mosaic has answered the question, so `canvas_is_mosaic` (from `target_field_fulls` against the engine's own `AUTO_UNION_AREA_RATIO`) stands the verdict down. Frontend-free — `framingRowBadge` never had an `already_targeted` branch. Tests +6, **three fail before**. Additive optional fields only; no config, schema, on-disk, default, endpoint or ranking change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.471.7** — 🟡 PERFORMANCE + memory safety (AGENTS.md §10) on the **walk-away scan**, found by reading `_auto_stack_degraded_recheck`'s own promise that a healthy target *"pays nothing but a couple of DB reads"*: **it built a `FrameRow` per accepted sub, up to six times per target per poll.** `_solved_accepted_count` (asked once by `_auto_stack_frame_count` and again by each of the two rechecks behind it) summed a generator over `iter_frames` to take a **count**; `_detect_mixed_pointings`, `_auto_stack_panel_depth` and `_auto_stack_readability_hold` each read the same rows again for two coordinates and two paths. New `Project.count_accepted_solved()` (`COUNT(*)`, with the empty-string arm spelled out so it stays the engine's own `if f.wcs_json` and cannot disagree with the stacker about which subs exist) plus `iter_frame_columns` for the rest. **935 ms → 54 ms** for the count and **993 ms → 254 ms** for the pointing read on a synthetic project the size of the owner's deepest target (35,894 subs), identical answers. `readable_frame_path`'s rule gained a column-shaped spelling, `project.first_existing_frame_path`, with the row-shaped form a wrapper over it and a test comparing the two over every shape — one definition, two callers. Tests +4, **three fail before** (scratch reverts). No config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.471.6** — 🟡 PERFORMANCE + memory safety (AGENTS.md §10), the **unattended** sibling of v0.471.2, found by asking that fix's question sideways: **three more places ask "which master fits these subs?" and were still building a `FrameRow` for every accepted sub to answer it** — `pipeline._confident_master_binding` (in the job worker, with a stack about to allocate its canvases, and again per target per scan from `_auto_stack_calibration_recheck`), `pipeline._apply_saved_calibration_masters`' two lazy reads (`_sub_dims` / `_sub_bayer`, which read the whole table *twice* on a run that checked both), and `routers/stack._uncalibrated_advice`. All three now read `Project.acquisition_values` / `iter_frame_columns`, which have existed since v0.471.2. **1,525 ms / 128.3 MB peak → 513 ms / 11.7 MB** on a synthetic project the size of the owner's deepest target (35,894 subs), arguments identical field for field — every representative value keeps its own arithmetic, so no master is picked differently. Tests +3, **all three fail before** (scratch reverts); two hand-rolled `iter_frames`-only test fakes became real `Project`s, which is the shape that would otherwise keep passing through exactly this change. No config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.471.5** — 🟡 PERFORMANCE + memory safety (AGENTS.md §10), closing shape **(b)** of the same measured LEAD, and **not** the way it was sized: **the "First look" card built a `FrameRow` for every accepted sub of the target to read four small fields off one of them and take a count.** The lead's dilemma ("a narrow projection means either returning a tuple or re-reading that one row") rests on the lever being *what is read*; v0.471.4 measured that these reads **stream**, so the lever is what the caller **keeps** — and `best_frame` is a `min()`, which keeps one frame. So no projection and no new record: `qc.grading.best_frame` takes an `Iterable` and streams a strict-`<` running minimum (identical tie-break — `min()` keeps the first frame at a winning key, and so does `<`), the endpoint hands it `iter_frames(accepted_only=True)` itself, and `n_accepted` is `Project.count(accepted_only=True)` rather than a `len()` of rows built to be discarded. **1,181 ms / 135.3 MB peak → 858 ms / ~0 MB**, same pick, same count; it still returns a `FrameRow`, so no caller changed. Pure optimisation; no endpoint, config, schema, on-disk, API-shape or default change. Tests +5, **both guards fail before** (scratch reverts). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.471.4** — 🟡 PERFORMANCE + memory safety (AGENTS.md §10 — this box has an OOM history), closing shape **(c)** of the measured Target-page LEAD: **the "How's my stack?" card read every sub of the target as a whole `FrameRow` to ask seven small questions and one bit.** On the owner's deepest target that is 35,894 rows, each carrying its own plate solution (a FITS header *text* of ~25 eighty-character cards) — **1,180 ms / 144.0 MB peak → 541 ms / 9.8 MB**, field-for-field identical records, identical notes and identical darks guide. The lead's open question ("what does a *frame* mean to `stack_health`?") was answered by enumerating every attribute its three functions touch: new `project.FrameHealth` record + `Project.iter_health_frames`, plus `FrameRow.solved` as a property so the one derived bit has a single definition — the engine functions take a `stackhealth.GradedFrame` union and cannot tell which kind they were handed. Every existing caller still passes whole rows. **A `_FRAME_EXPRESSIONS` facility that answered the bit in SQL was built and then removed, because the measurement did not support it** (269 ms → 256 ms, same peak): the read streams, so the header is transient and the 144 MB was always the *retaining*, never the reading — which is the thing to know before picking shape (a) or (b). Pure optimisation; no endpoint, config, schema, on-disk, API-shape or default change. Tests +16, **both guards fail before** (scratch reverts). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.471.3** — 🟡 PERFORMANCE (same run, same question one page over, measured both ways): **two more Target-page fetches were building a `FrameRow` per sub — 35,894 on the owner's deepest target — to read four small fields and one.** `…/frames/sky-brightness` **1,074 ms → 322 ms**, `…/restack-gain` **1,132 ms → 370 ms**, identical answers. Time rather than memory this time (both already streamed), but ~1.5 s of a page load spent on the plate-solution column neither of them reads. New general `Project.iter_frame_columns(*columns, accepted_only=False)` yields those columns as plain tuples in `iter_frames`' own id order, with the names checked against `_FRAME_COLUMNS` before they reach the SQL; `acquisition_values` is expressed on it, so there is one piece of SQL rather than two. Three more of the same page's fetches were measured and **deliberately left** — they need an engine signature decision, and two of them are the bigger fish because they `list()` the target: filed as a lead with the numbers. Pure optimisation; no endpoint, config, schema, on-disk, API-shape or default change. Tests +7, **both endpoint guards fail before** (scratch revert). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.471.2** — 🟡 PERFORMANCE + memory safety (AGENTS.md §10), Builder-found by asking v0.471.1's question one endpoint sideways and then **measured**: **the Stack form's `calibration-suggestions` and the Calibration page's coverage roll-up each read every accepted sub of a target as a `FrameRow` to ask six questions about the camera** — and the biggest column on a solved sub is the plate solution neither of them reads (`wcs_json` is a FITS header text of ~25 eighty-character cards). The roll-up pays it **per target, across the whole library**. Measured on a synthetic 35,894-sub project: **1,132 ms / 146.4 MB peak → 244 ms / 8.4 MB** (4.6× faster, 17.4× less memory), identical values. New `Project.acquisition_values` + `_ACQUISITION_COLUMNS` reads the six columns and returns parallel lists; `ORDER BY id` is kept because `modal_dim`/`modal_bayer` break a tie on whichever candidate they met first. The same commit retires the drift risk the fix ran into: the eight fields were hand-mirrored in the two call sites, which is why `gain` had to become `dominant_gain` in both at once (v0.469.0) — now one `_acquisition_signature`, so the form and the page **cannot** describe one target differently. Pure optimisation: identical responses over 40 randomised awkward targets, `iter_frames` untouched; no endpoint, config, schema, on-disk, API-shape or default change. Tests +8, the memory one **fails before** (scratch revert). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.471.1** — 🟡 PERFORMANCE + memory safety (AGENTS.md §10 — this box has an OOM history), Builder-found by reading `routers/frames.py` at the owner's scale and then **measured**: **opening the frames table on his deepest target read all 35,894 subs eighteen times over.** `GET …/frames` paginates, but answered each request by materialising every `FrameRow` in the target, sorting in Python and discarding all but the window — and `api.listFrames` deliberately pages the *whole* target 2,000 at a time until a short page. Measured on a synthetic 35,894-sub project: the full paged read **9.09 s / 163.6 MB peak → 2.40 s / 83.5 MB**, a single 500-row page 472 ms → the cost of 500 rows. New `Project.iter_frames_page` hands SQLite the sort and the slice; the ordering is unchanged and pinned against the Python sort it replaces on every sortable column × direction × window. Nulls-last is load-bearing (a test fails without it); the `id ASC` tie-break is **insurance, not a fix, and the test says so** rather than pretending to fail before. `sort` is validated in the engine against `_FRAME_COLUMNS`, derived from `FrameRow`'s own fields, because it arrives from a query string. Pure optimisation — identical responses, `iter_frames` untouched; no endpoint, config, schema, on-disk, API-shape or default change. Tests +34, the endpoint's own **fails before** (scratch revert). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.471.0** — PRIORITY 3 (friendliness / enjoy-share), the last open slice (c) of the wall-chip feature: **the Library wall's "Not stretched yet" chip is now the one click to that picture's editor**, instead of naming a problem whose fix was a ~3,300 px page away. The run it links to has been on the wire since v0.448.0 (`UnstretchedItem.run_id`), so nothing new travels; the chip is a `<button>` inside the card's `<Link>` that stops its own click (`WishlistStar`'s shape), so the card still goes to the target and nothing was restructured or removed. The hint's copy is a fix in itself — it said *"Open it and press Auto"*, stale since v0.390.0 made the editor seed Auto itself, and a different account of the same screen from the Gallery's hint for the identical state. A response with no usable `run_id` keeps the plain chip. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change. Tests +9, **2 fail before** (scratch revert). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.470.2** — 🟠 BUG ×3 (image quality + trust — PRIORITY 1/3/4, Builder, the three pieces of observer [#952](https://github.com/JimmyeJones/astrostack/issues/952) that v0.470.0/.1 did not cover; this run built that fix independently and collided, closing its own PR as superseded — see [#953](https://github.com/JimmyeJones/astrostack/pull/953) for what the merged version did better). **(1) The one run in 680 where the measurement fired, it answered about the wrong pair:** `level < deep_level` accepted any integer below the mode, so IC 360's levels **3,116 and 3,117** — one sub apart, each a tenth of the canvas — were compared and reported **1.0078 over 15 %**, where the depth bands on that canvas read **2.27 over 27 %**. Grain falls as 1/√depth: one sub apart is a predicted 0.02 %, so that comparison measured sky samples, not depth. A candidate must now be a tenth shallower — a bound read off `_GRAIN_BAND_THIN_OF_BULK`'s own reasoning (1/√0.9 = 1.054×, an order below the bar the ratio is graded on), not picked — and such a canvas falls through to the band rule, which has something true to say about it. **(2) The new measurement could not reach the canvases it exists for:** `backfill_coverage_grain` is the only path by which an already-stacked mosaic picks it up and it reads **strided** (step 3 on a 3494×2470 canvas), while `_GRAIN_MIN_SKY_PIXELS` is an absolute 500 — so a sample of a ninth the pixels had to clear the whole-canvas bar, on top of a thin band already losing most of its sky to a globally-thresholded, 4 px-dilated object mask. Measured on the repo's own dithered fixture: **948 sky pixels at full resolution, 171 at stride 2**. The floor is now scaled by 1/step², by exactly the arithmetic `include_min` uses two lines above it; nothing at stride 1 moves, and the change can only ever make a strided read answer where it was silent. **(3) Three cards still offered the night for a rim:** `grainProjection`, `nextBestMove` and `integrationTrend` prescribe from the same verdict the note does, and all three still said "more light" / "more passes" / "another pass over it" — the last on the card whose whole subject is what is worth shooting. All three now fork off the **same** `has_ragged_border`, served on the run row as `ragged_border` rather than re-derived, because a second reader of one rule is how two surfaces come to prescribe opposite things. Tests +3 Python / +6 vitest, **fail-before verified by five scratch reverts**; additive optional field only, no schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.470.1** — 🟠 BUG (trust — PRIORITY 3, measured in-repo the same run): **"Trim border gives a clean, even rectangle" is a promise the trim cannot keep on a dithered mosaic, and v0.470.0's new ending had just made it twice.** The two yardsticks differ by construction — "thin" for the trim is under a quarter of *one panel's* depth (`COVERAGE_THIN_RATIO`, deliberately the level it keeps down to), while the grain bar is half the depth *most of the canvas* is at, where 1/√depth says the difference starts to show — so everything between them survives the crop. Measured inside the rectangle `largest_covered_rect` keeps on the dithered 2×2: `coverage_thin_fraction` **0.0**, `measure_coverage_grain` still **1.71× over 13 %**; the observer measured 10.1–30.5 % at 1.39–2.22× across the owner's 22 real mosaics against **0.9 %** on the single-field controls, which is the control showing the trim works where it can. Both sentences now stop where the app can keep them, gated on `uneven_grain_verdict` — the same reader the grain note uses, so one card cannot make two promises about one button. A single field, an even mosaic and every pre-measurement run keep today's sentence **byte for byte**, pinned as an equality both ways. Tests +3, **one fails before** (scratch revert). No config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.470.0** — 🟠 BUG (image quality + trust — PRIORITY 4/1-adjacent, from observer issue [#952](https://github.com/JimmyeJones/astrostack/issues/952), reproduced before it was fixed): **the mosaic grain measurement was silent on every genuine mosaic in the owner's library, and `PanelSeamsBadge` was over-claiming "Panels even" with the silence.** `measure_coverage_grain`'s 10 %-of-canvas bar is applied to a single **integer** coverage level — right for a tiled mosaic, and it finds nothing on a dithered one, where the per-pixel count ramps through **79–1392** distinct levels (modal level 2.0–17.5 %, largest level below it 0.0–7.4 %). `grain_ratio` was non-NULL on **2 of 680** runs, both single fields, and the one place it fired compared **3,116 subs against 3,117** — while three runs showed a green *"you shouldn't see seams between them"* over canvases measuring **1.86× grainier across 44 %** of themselves. New `_grain_from_depth_bands` asks the same question of two **bands** of depth, reached **only** when the level comparison finds no candidate, so every canvas answered today is answered by the same code with the same numbers. Both bounds derive from `_GRAIN_UNEVEN_RATIO` (half the bulk = 1.41× grainier, the shallowest still predicted to clear the bar; ±15 % reference = 1.08× internal spread), and the bulk is the **median** — not the mode, which on a ramp lands anywhere, including on the shallowest panel. `_region_sky_mask` gains `sigma_allowance`: its structure guard judges a region against the *canvas's* sky spread, which is the wrong yardstick for one known to be shot shallower, and it was refusing exactly the bands worth reporting — the band path allows √(deep/thin) and no more, in both places it is applied. And the newly-firing note's sentence was made true of that canvas: the thin part there is the ragged **perimeter** (0 % of thin pixels beyond half the inscribed radius on any of his 22 mosaics), not a panel to go back to, so new shared `has_ragged_border` gives it a third ending. Measured on a dithered 2×2 fixture: **1.73× over 22.7 %, 12 subs against 40**, conservative against the 1.83 the physics predicts. Tests +6, **three fail before** (scratch reverts); the precondition is asserted, not assumed. No config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.469.2** — 🟠 BUG (friendliness + image quality — PRIORITY 3/4, Builder-found this run by sweeping the v0.469.0 *family* one surface sideways, and reproduced before it was fixed): **the "How to add darks" guide told the owner to go and shoot darks at a gain his camera cannot be dialled to.** `stackhealth.recommended_dark_spec` took `statistics.median` of the accepted subs' gains — and the function's own docstring, two lines above, already argues why that is wrong, for the *exposure*: *"a target shot at 10 s and 30 s has a median of **20 s**: a length none of their subs was shot at, offered under the words 'the same settings as your subs'"*. v0.457.0 fixed the exposure half and left the gain sitting beneath the paragraph that condemns it. The gain case is the sharper one: an exposure is a quantity, so 20 s is at least a length a camera could be set to, while **140 is not a setting at all** — and there is no `scale_dark_to_light` for a gain, so darks shot to that instruction calibrate nothing. Fixed by giving `DarkSpec` the same treatment its exposure already has: `gain` is now `apply.dominant_gain` (the setting the most subs carry) and a new `gains` tuple carries the distinct settings via `distinct_gains`, additive through `DarkSpecOut` and the client type. The guide names them all — *"10 s at gain 80 and 200"* — and `darkSpecPerLengthNote` widens into `darkSpecPerSettingNote`, which asks for a set of darks per gain with the reason (*"a dark carries the gain-dependent readout pedestal, and nothing rescales it"*) and, when **both** settings moved, says it in **one** sentence rather than two, because a reader who changed both needs one instruction and the guide sits under the standing "extremely busy" complaint. The same run also fixed the third median-gain reader, `routers/stack.py`'s uncalibrated advice (`diagnose_uncalibrated` / `incoming_calibration_advice`), so the "why isn't this calibrated?" answer and the stack that would calibrate it judge one target's masters against one gain. **Byte-identical on every single-gain target**, which is every Seestar library until someone changes the setting — pinned on both sides. Tests +9 (4 engine, 2 webapp wire, 5 vitest — one vitest case renamed with the function); **fail-before verified by two scratch reverts** (the median restored; `darkSpecGains` made to ignore the set). No config, schema, on-disk, API-shape or default change.
- **v0.469.1** — 🟠 BUG (autonomy — PRIORITY 2, Builder-built this run, closing shape **(a)** of the same binder LEAD): **when two masters matched a target equally well, which one the walk-away stack got was whichever the registry happened to list first — including when one of them had never been that cold.** A master's stamped `sensor_temp_c` is the *median* of its source frames, so a dark built across a −15 °C night and a +5 °C one is stamped −5 °C and scores an identical `_match_distance` to a dark genuinely shot at −5 °C. v0.468.0 made the app *say* so on the Calibration page; nothing made it *choose*. Fixed with a tie-break, not a distance: new `_temp_range_span` (derived from the `SSTMPMIN`/`SSTMPMAX` cards v0.468.0 started writing) and `_match_rank`, which orders candidates by `(distance, span)`. **Why it is a tie-break is the whole design:** `_match_distance` also feeds `_dark_match_confident` and its siblings and `master_coverage`'s "which targets does this cover?", so charging a blended master extra *distance* could flip a bind into a refusal and strip calibration off a target that has it today — which is exactly what the lead warns is unsettleable from this repo. A tie-break can only ever reorder two masters already level, so nothing that binds today stops binding. Applied at all four places that rank masters (`recommend_masters`, `auto_bind_master_ids`' dark/flat/bias candidate sorts, `_recommend_flat_dark`, `existing_master_like`) and at none of the three that gate; the interactive form's badge score stays the distance alone, because two equally good matches must not be shown two numbers. One-sided like every other reading in the module: a master built before the range existed — the whole installed base — scores 0 °C and keeps its place, pinned by a test. Tests +5 (one parametrized over both registration orders, because "whichever came first" is precisely what this replaces); **fails before in the order that used to lose**, verified by stubbing the span to 0.0. No config, schema, on-disk, API-shape or default change.
- **v0.469.0** — 🟠 BUG (autonomy — PRIORITY 2, Builder-reproduced this run, closing shape **(b)** of the binder LEAD filed with v0.468.0): **the unattended binder judged every master against a gain the camera was never set to.** A gain is a discrete setting, and `pipeline._confident_master_binding` handed the binder `_med([f.gain …])` — so a target shot 3 subs at gain 80 and 3 at gain 200 was judged against **140**, and both failure directions follow: the gain-80 dark that matches half the stack scores 0.43 away and can be refused, while a gain-140 dark that matches **none** of it scores 0 and is bound — on the walk-away path, where nobody reads the advisory v0.466.0 added for exactly this. With three or more settings the median need not even be the majority: three subs at 80, one at 140 and three at 200 puts it on the one sub in seven. Fixed with a new pure `apply.dominant_gain`, built from `distinct_gains`' own grouping (hoisted to a shared `_gain_groups`, so "is this a second setting or a header round-trip?" cannot be answered one way when the app counts a target's gains and another way when it picks the one they stand for); an exact tie resolves to the **lower** setting, deterministically (re-reading the same frames in another order must not rebind a target) and toward the safer error (a smaller pedestal *under*-subtracts, where the opposite over-subtracts and clips shadows to hard zeros). Wired into all three places that took a median gain — the binder, the Stack form's `calibration-suggestions` (`params.gain`) and the coverage roll-up's target signature — so the page, the form and the finished run cannot describe one target three ways. **Byte-identical on every single-gain target, which is the whole installed base:** there the mode, the median and the only value are the same number. The **temperature** half of the lead was weighed and deliberately not built — a temperature is continuous, so a value between two nights' readings is one the sensor really passed through, and there is no mode to reach for; the reasoning is on the lead. Tests +7 (4 engine, 3 webapp); **2 fail before**, verified by reverting the call site in the working tree. No config, schema, on-disk, API-shape or default change — `params.gain` is an existing field whose value is now always one of the settings `params.gains` already lists.
- **v0.468.1** — 🟠 BUG (image quality / correctness — PRIORITY 4, in `seestack/calibrate/`, Builder-found by sweeping the family of v0.468.0 one *kind* sideways, and reproduced before it was fixed): **a master bias built from a folder with a few darks in it combined all of them — the identical folder built as a `dark` set those frames aside.** `masters.build_master` gates a **dark**'s exposure (v0.458.0) and a dark-or-bias's gain (v0.467.0); the bias was exempt from the exposure rule, and the comment saying why — *"a bias is by definition the zero-length frame"* — is a statement about what a bias **is**, not about what is in the folder, so it argued **for** the gate rather than against it. Measured on a synthetic folder of 0 s readouts (500 ADU) with 10 s darks (1500 ADU) mixed in: an even split gave a **1000 ADU** master stamped **5 s** — a bias frame claiming to be a five-second exposure — and the 4-to-2 folder gave **833 ADU** stamped **0 s**, which is the silent one, a pedestal 67 % too big wearing a bias's own label; the same folder built as a dark skipped the intruders with `"wrong exposure"`. **It matters more here than in a dark, because the bias is what carries dark exposure-scaling:** `_effective_dark` computes `bias + (dark − bias)·t_light/t_dark`, so an inflated bias is wrong at *every* pixel of every scaled frame, and the bias is also `build_defect_map`'s fallback source. **The one subtlety, and why extending the gate is not a one-liner:** `apply.distinct_exposures` drops a non-positive value on purpose (for a light or a dark a `0 s` card is a blank, not a length), so the commonest contaminated-bias folder — 0 s frames plus a stray dark — grouped as *one* length and gated on nothing. `_majority_exposure_group` / `_exposure_in_group` therefore take an opt-in `allow_zero`, passed only by the bias call, which carries **0 as a length of its own matching only another 0** — an exact match, not a new threshold, because `0` is 100 % away from every positive length and `0/0` is not a ratio. It stays a **majority** rather than "the shortest wins", so a lone mistyped `EXPTIME = 0` is the frame that gets set aside rather than the one that defines the master and skips every real frame after it — the failure the majority-*shape* rule already exists to prevent. The Jobs line gets a bias-specific "because" (*"a bias is the readout on its own, so a frame shot for seconds is dark current rather than a bias"*), since *"a bias only matches subs of its own exposure"* would be false — a bias is exposure-independent where it is **applied**. Byte-identical on every uniform folder of any kind, and the **dark** path is untouched (a stray 0 s frame in a dark folder is still dropped from the grouping, exactly as before). Tests +11 Python / +1 vitest; **8 fail before**, verified by reverting the gate in a scratch copy. One existing vitest case was deliberately re-pointed rather than weakened — it used `kind: "bias"` incidentally to assert that *both* reasons get named, which is now a dark's sentence; it keeps that claim on a dark, and the bias wording gets its own case beside it. No config, schema, on-disk, API-shape or default change.
- **v0.468.0** — 🟠 BUG (image quality / correctness — PRIORITY 4, in `seestack/calibrate/`, Builder-found and reproduced before it was fixed): **a master dark built from a folder that spans two nights' temperatures is stamped with a temperature no frame in it was shot at — and when that median lands on the subs, the one check built to catch a temperature mismatch reports a perfect match.** The third acquisition number, on the *build* side. `masters.build_master` gates **exposure** (v0.458.0) and **gain** (v0.467.0); `MasterMeta.sensor_temp_c` was a bare `np.median` over the frames' `CCD-TEMP` with nothing anywhere asking what that median was a median *of*. Reproduced on a synthetic set at one exposure and one gain with only the temperature differing — 3 frames at −10 °C (100 ADU) and 3 at +15 °C (1400 ADU): a **750 ADU** master stamped **2.5 °C**, a level and a temperature no frame ever had, on all three combine methods; the 4-to-2 folder is the silent one (`mean` → 533 ADU stamped −10 °C, i.e. the majority's own label on a pedestal 5.3× the majority's level). Handed subs shot at 2.5 °C, `calibration_warnings` returned **`[]`**. **The fix is deliberately to *disclose*, not to gate, and that is the part worth carrying forward:** an exposure and a gain are *settings*, so a second value is a second population by definition — a temperature is continuous and a Seestar's sensor is uncooled, so it follows the night and the season, and dropping the minority would throw away good frames and leave the master noisier for nothing. `apply.py`'s own constant comment already says as much (*"a temperature… earns a tolerance wide enough to cover a night"*). So `MasterMeta` gains `sensor_temp_min_c` / `sensor_temp_max_c`, written into the master's FITS as additive `SSTMPMIN` / `SSTMPMAX` cards (part of what the master *is*, unlike `n_supplied`, so a master reloaded off disk can still say its temperature is a middle); new pure `apply.dark_temperature_blend` / `dark_temperature_blend_warning` fire at **`TEMP_MISMATCH_TOL_C`**, the module's own "far enough that dark current has moved" bar rather than a sixth threshold; `CalibrationMasters.dark_temp_min_c/max_c` carry it, and the sentence is said **before** the dark↔lights comparison because it is the premise that comparison rests on, and with no `light_*` argument at all (it is a fact about the dark). One sentence, four surfaces for free through `calibration_warnings` (Jobs, History, Stack, Editor), plus `calibration.master_temp_note` on the Calibration page's master row and on the build job at the moment it happens — where no frame was set aside, so every count the summary reports says it was a clean build. **Nothing about a pixel changes**, and a one-night folder, a flat, a bias, a camera that writes no `CCD-TEMP` and every master built before the cards existed are all silent. Tests +13 Python / +5 vitest; **6 fail before**, verified by two scratch reverts (the build-side record, then the webapp store and the advisory emission separately). No config, schema, on-disk layout, API-shape or default change; the registry JSON and old master FITS both read as "didn't say", never as "uniform".
- **v0.467.1** — 🟠 BUG (autonomy + friendliness — PRIORITY 2/3, found by a `--calibration --incoming-lag --mosaic` dogfood pass that was otherwise CLEAN, and reproduced in one call before it was fixed): **a folder of darks the owner has just copied in is invisible to the page whose entire job is to notice it, and refreshing does not help.** The `incoming/` calibration-folder walk is cached app-wide for `INCOMING_SCAN_TTL_S` (120 s) and is warmed by *whichever consumer asks first* — the Dashboard's incoming-lag note reads the same walk (`routers/incominglag._calibration_folders`), so on a real install it is usually that poll, not the Calibration page, that looked. The dogfood pass made it visible by accident: it seeds the lag state (which polls the note) and *then* writes the darks, and printed `[offer] NOTHING FOUND — the seeded frames are invisible to the app`, `[masters] 0 in the registry`, `[run 1] masters actually applied: NONE` — while `discover.find_calibration_folders` on the very same path answered `Darks 10s dark 6 10.0 80.0`. So every calibration surface the `--calibration` flag exists to reach was unreached on that pass, and on the owner's box the one-click *"you already have darks, shall I build one?"* offer stays empty for up to two minutes after the copy, through a reload. Fixed by keying the cache on **`incoming/`'s own immediate sub-folder names** as well as the TTL (new `calibration._incoming_subfolder_names`): a folder added, renamed or removed changes the set and the next request re-walks, while subs landing in a folder that already exists do **not** — which is the property that keeps it safe, because re-walking on file mtimes would re-list a hundred folders of thousands of subs every few seconds on exactly the night the app is busiest, to notice nothing. One `os.scandir` of one directory, reading the directory entry's own type, so it costs no `stat`, opens no file and keeps `incoming/` strictly read-only (§10). Still bounded by the TTL, unchanged: a calibration folder nested one level down, and frames that only now clear `discover.MIN_FRAMES` in a folder already there. Tests +6 (`tests/webapp/test_calibration_incoming.py`), **3 fail before** — verified by reverting the name check in a scratch plugin; the other 3 pin that nothing got more expensive (an untouched folder is still walked once, a night of subs still does not re-walk, an unreadable `incoming/` still falls back to the TTL). No config, schema, on-disk, API-shape or default change.
- **v0.467.0** — 🔴 BUG (image quality / correctness — PRIORITY 4, in `seestack/calibrate/`, Builder-found and reproduced before it was fixed): **a master dark or bias built from a folder holding two gains is a photograph of neither — and its minority case was silent.** `masters.build_master` gained a majority-**exposure** gate in v0.458.0; it never had the same gate on **gain**, which is the other setting a pedestal frame's whole content depends on (raise the gain and the offset, the read noise and the amplified dark current all scale with it). Reproduced on a synthetic set at one exposure and one temperature with only the gain differing — 100 ADU (gain 80) and 300 ADU (gain 160) in: an evenly-split folder gave a **200 ADU** master stamped **gain 120**, a level and a setting no frame in it was ever shot at, on all three combine methods. The 4-to-2 folder was worse because it was *silent*: `mean` gave a **166.7 ADU** master stamped gain **80**, so v0.466.0's gain advisory — which compares the master's own stamped gain against the lights — saw a perfect match and said nothing about a pedestal 67 % too big. And unlike an exposure there is no lever anywhere that corrects a gain gap afterwards: `scale_dark_to_light` rescales a mismatched *length*, nothing rescales a mismatched *setting*. Fixed with the majority-gain gate built from the same parts as its siblings — new `masters._majority_gain_group` / `_gain_in_group` grouped by the engine's own `apply.distinct_gains` + `gain_mismatch`, so "two gains" means one thing everywhere; lowest wins a tie (deterministic, `distinct_gains` is lowest-first); a frame with no recorded `GAIN` is kept ("didn't say" is not "said the wrong thing"); gain 0 groups like any other value because it is a legitimate setting. **Darks and biases only** — a flat is normalised to its own median before it divides, so a constant gain factor divides straight back out. The Jobs line now says what to do with the frames it set aside (`buildMasterSummary`, `"wrong gain"`), and names **both** reasons when a folder holds two lengths *and* two gains, so a re-run can't set frames aside for a reason the line never mentioned. Behaviour is byte-identical on every single-gain folder, which is every folder until someone empties two nights of settings into one. Tests +11 Python / +2 vitest; **8 of the 11 fail before**, verified by reverting the gate in a scratch plugin (the three that stay green are the ones pinning that the gate does *nothing* on a one-gain folder, a header round-trip and a flat). No config, schema, on-disk, API-shape or default change.
- **v0.466.2** — 🟠 BUG (trust — PRIORITY 3), found the same run by re-reading v0.466.1's own new copy against the card it now sits beside: **the sentence that fix had just written was itself a whole-canvas claim, and on a mosaic `noise_sigma` is not one.** σ is a single robust estimate over the finished canvas, dominated by the panels that got the most subs — so *"The background here already measures clean"* landed a line above this same card's *"about 23 % of the picture has 3 subs where most has 6, so that part looks about 1.4× grainier"* on the bundled 2×2, the shape the owner's multi-night mosaics have. Fixed with the treatment `grainProjection.ts` already gives its own clean verdict: *"Across most of it the background already measures clean…"* on a measurably uneven run, today's sentence on a single field, an even mosaic, or any run missing one of the four figures. The guard for those figures is hoisted to a public `uneven_grain_verdict(run)` read by **both** sentences — two readers of one measurement is how v0.466.1's bug got in. Uneven-grain note unchanged. `DarksGuide`'s lead carried the same over-claim and is fixed by **removing** it rather than scoping it — it now says what darks do here (*"mostly means hot pixels rather than less grain"*, true on any canvas since darks never touch shot noise) instead of restating the note's verdict, so it needs no scope flag and there is one fewer place to drift. Tests +3 Python, **fail-before verified by scratch revert**. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.466.1** — 🟠 BUG (trust + friendliness — PRIORITY 3), Builder-found this run by a `--mosaic --editor --incoming-lag` dogfood pass that was otherwise CLEAN: **the Target page's health card promised that darks "would cut the background speckle" on a picture the readiness card an inch above had just *measured* as clean.** `stackhealth.stack_health`'s calibration note fired on `calstat` alone and then made a claim about this picture's grain, while the very `StackRunRow` it was handed carried `noise_sigma` — the number that settles it. Reproduced on both samples in one pass, and **not a sample artefact**: the clean bar's provenance is the owner's own 271–787-frame stacks measuring σ 0.015–0.020, i.e. inside it, so this is his everyday state on every target with no master dark. Fixed by keeping the offer and dropping the unearned clause — new public `background_reads_clean` + `CLEAN_BACKGROUND_SIGMA` (**the same literal** as `grainProjection.ts::CLEAN_SIGMA`, pinned from both sides so two cards can never again hold private opinions about one σ) picks the sentence; a measured-clean picture is told what darks still buy (hot pixels, the camera's own warmth — the part a robust σ cannot see), and a grainy or **unmeasured** run keeps today's sentence byte for byte. `StackHealthOut.background_clean` serves that one fact to `DarksGuide` so the guide stops re-asserting "the single biggest cleanup for a noisy image" under a note that just withdrew it. Nothing removed, no threshold moved, no pixel changed, calibrated runs unreachable. Tests +8 Python / +3 frontend, **fail-before verified by scratch revert on both sides**. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.466.0** — 🟠 IMAGE QUALITY + TRUST (PRIORITY 4), Builder-reproduced this run, closing the gain LEAD filed the same day: **a gain-mismatched master dark was applied in silence, and the run's own advisory was structurally unable to mention it** — `[f for f in CalibrationMasters.__dataclass_fields__ if "gain" in f]` was `[]`, so with exposure and temperature matched a gain-200 dark subtracted its full 300 ADU pedestal from gain-80 subs and `calibration_warnings` returned `[]`; meanwhile `_dark_match_confident` auto-binds anything up to a whole relative gain unit away (gain-100 scores 0.250, gain-120 0.500, gain-160 exactly the 1.0 bar). **The gate the lead filed it behind was the wrong question**: a tolerance is what a *severity verdict* needs, and gain does not get one — an exposure gap has `scale_dark_to_light` and a temperature gap is a continuous drift, while a gain is a setting nothing anywhere corrects for, which is why `_acquisition_reason` already reports it on `gain_d > 0`. So the sentence states both numbers rather than grading the gap and `GAIN_MISMATCH_TOL` absorbs header round-trip noise and nothing else. `apply.dark_gain` + `gain_mismatch` + `distinct_gains`; `run_stack` hands over **every** frame's gain, not the reference frame's (a target is not necessarily one gain either); and the Stack form says it at pick time off served `params.gains` + `tolerances.gain_frac`, because the run half alone re-creates the form↔run split v0.464.1 exists to close. Reports only — binding, pixels and every existing warning untouched, and silent on a library shot at one gain. Tests +25, **seven fail before**. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.465.4** — 🟡 BUG (friendliness — PRIORITY 3), measured by the pass that verified v0.465.3: **a History run card that had earned six badges gave each of them two or three pixels rather than give the row a second line** — "Sky even" 45 px box vs 47 px word, "dark+flat" 54 vs 56, "21 frames" 61 vs 64. Not one badge too long: the row two pixels too short, taxing every occupant. **Desktop, not phone, and that is the tell** — the cards sit in `SimpleGrid cols={{base:1,sm:2,md:3}}`, so a card is ~390 px however big the screen is and a wide screen just buys three of them. Fixed with the sibling card's own shape: the Gallery card of the same run is badge-for-badge identical by design and has always let its badge row wrap, so History's `wrap="nowrap"` was the outlier; the heading gets the card's whole width, exactly as Gallery's does. A badge is a whole short fact — there is no such thing as most of one — and the run name is how you tell one stack from another, so **neither** yields: the row does. (Keeping the shared row and only letting the badges wrap was tried first and the verifying screenshot showed the heading as "mas…"; a test now pins the name out of that row.) Tests +2, **both fail before**. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.465.3** — 🟡 BUG (friendliness / mobile — PRIORITY 3), measured this run by a `--mosaic --calibration` dogfood pass: **the header's "N running" badge — the only element on any screen that says the app is working for you — was clipped on a phone on all 14 probed routes** (60 px box vs a 63 px word; the probe's own note is that scrolling cannot reveal it). Twenty clean passes missed it because `ActiveJobsBadge` renders nothing when no job is running and no probe had ever looked while one was — the missing-site / empty-`incoming/` / click-only-Compare hole a fifth time, in its cheapest form. Fixed with the header's own idiom (`<Box visibleFrom="xs">`, as the Scan button beside it already does): the count is always text, the word comes back from `xs` up, and the full phrase stays the badge's `title` and a `VisuallyHidden` span at every width — `visibleFrom` hides with `display: none`, which hides from a screen reader too, so the spoken badge would otherwise have become the bare number. `flexShrink: 0` was rejected — it moves the clip onto the wordmark. Tests +3, **two fail before**. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.465.2** — 🟠 BUG (friendliness + trust — PRIORITY 3), Builder-found on a `--mosaic --editor` dogfood pass this run: **the Target page prescribed two different next sessions for the same night — the coaching card asking for "another pass or two over the same mosaic", the framing note an inch below for "more panels next session" — and only one of them knew the other existed.** v0.443.0's `framing` rung closes this *below* `FRAMING_MAX_COVERAGE` (0.67), where the coaching card becomes the widen advice; above it that card deliberately decides the opposite (a `partial` verdict fires just as readily at 95 % captured, where depth is plainly the better lever) and nothing carried the decision down. Photographed at 75 % captured. Fixed as the deference running both ways: a new `framingDepthFirstClause` (beside `framingIsFragment`/`readinessCanvasScope`, one gate in one file) adds *"Most of it is already in this picture, though — until you're happy with the depth, more passes over the panels you already have do more for it than a wider grid"*, gated on the coaching card's **actual** verdict (`coachKind`, the wiring `IntegrationTrendBadge` already uses) so it can never become a third opinion beside "refocus" or "install the star database", and on a *measured* coverage above the bar. Nothing removed, no new element, no new number. The editor and History pass no `coachKind` and are byte-identical. Tests +10, **five fail before**. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.465.1** — 🟠 BUG (trust + friendliness — PRIORITY 3), Builder-found and reproduced this run: **the health panel's uneven-grain note converted a mosaic's depth shortfall into minutes with a plain median sub exposure, while the panel map printed directly above it sums each panel's actual seconds — so on a target shot at two sub lengths the two gave opposite instructions about one panel.** Since v0.406.2 the note reads its shortfall against the map's own `mosaicmap.THIN_MIN_SHORTFALL_S` precisely so they cannot disagree; a median is one member of a set chosen by position, so on a 2×2 mosaic with three quarters of every panel's subs at 10 s the map measured the thin panel 120 s against 480 s (*go and shoot it*) while the note said *"only about 4 min behind, so it evens out on its own"* — the honest figure being 24 missing subs × the 15 s mean = 360 s, the map's number exactly. The existing agreement pin could not see it: its own docstring says *"at one sub exposure"*. Fixed as **one** definition — v0.459.1's `_typical_sub_exposure_s` promoted to public `calibrate.apply.typical_exposure_s` beside `distinct_exposures`, read by both places that multiply a per-sub length by a count (`stacker`'s EXPOSURE/EXPTOTAL, unchanged, and `stackhealth._typical_sub_exposure`). `recommended_dark_spec` deliberately keeps its median: it names a length to dial into a camera, where a mean between 10 s and 30 s is a setting nobody can shoot. A single-exposure target is bit-identical. Tests +5 cases, **three fail before**. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.465.0** — 🟡 FRIENDLINESS (PRIORITY 3), found by the v0.464.0 fix: **the nudge that tells a beginner which dark to shoot never told them which *night* to shoot it on.** The Calibration page's uncovered-targets note ends *"Shoot them at 10s at gain 80"* — two of the three acquisition numbers the app's own binder gates on, its own `_acquisition_reason` blames a miss on, and `calibration_warnings` complains about afterwards. On an **uncooled** sensor the third one is the ambient, i.e. the only one the owner sets by choosing when to go out. One clause on the existing sentence (no new element): a night to aim for when the subs agree, an honest *"they weren't all shot on the same kind of night (−20 °C to 2 °C)"* when they don't, and silence when no sub recorded a `CCD-TEMP`. Rides the tally `_target_acquisition` already has the frames for; the wide/narrow bar is the engine's own `TEMP_MISMATCH_TOL_C`, so no new threshold. Tests +6. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.464.1** — the second half of v0.464.0, and not optional: the Stack form's pick-time temperature caution asked `params.sensor_temp_c` (the median), so on the very target the engine fix is about — three subs at 2 °C, three at −20 °C, a 2 °C dark — the form would have stayed silent while the finished run complained, which is the split `tolerances` exists to prevent. `calibration-suggestions` now serves `params.sensor_temps_c` (a `[[°C, count], …]` tally rounded to the tenth of a degree a `CCD-TEMP` card carries, so a 35,894-sub target answers in tens of rows) plus `tolerances.temp_min_share`, and the form says the engine's three sentences off mirrored helpers in `calibrationFit.ts`. No tally (older backend, no `CCD-TEMP`) falls through to today's wording, pinned both ways. Tests +9. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.464.0** — 🟠 BUG (image quality + trust, Builder-verified by reproduction) — **a target is not one *temperature* either, and the master-dark advisory assumed it was.** `run_stack` asked `CalibrationMasters.calibration_warnings` about `ref.sensor_temp_c` — the reference frame's — under a comment that, 400 characters earlier, explains why a reference frame cannot speak for a session about *exposure*. The Seestar's sensor is uncooled, so a target shot across a winter and a summer night holds a 20 °C spread against a 5 °C tolerance; reproduced on a real `run_stack` (six subs, three at 2 °C and three at −20 °C, a 2 °C dark), the **same subs and the same dark** warned or said nothing depending on which frame `pick_reference_frame` landed on, and when it warned it named a temperature half the subs were not shot at. Now judged against every sub's temperature via new pure `apply.temperature_spread` + `temperature_mismatch_count`, with a share floor `TEMP_MISMATCH_MIN_SHARE` so one stray frame cannot speak for a session either. Reporting only — nothing rescales a dark to a warmer night, so the binding is deliberately unchanged. Tests +7, five fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.463.3** — ⚪ a number in a comment that this run made wrong: `Glossary.tsx` explained its collapsed-accordion design as *"a list of headings, not 38 open entries"*, and the glossary is now 47 terms. Rewritten so it cannot rot again — the 8,194 px measurement it rests on keeps its count as a stated condition of that measurement, and the *current* total is not quoted at all, because the glossary grows whenever a screen gains a word it has to explain. Plus the run's `--editor` dogfood record in [`PROCESS-NOTES.md`](PROCESS-NOTES.md), including the re-measured page heights: `/glossary` is now the second-tallest phone page at 3,364 px (up from ~2,700 — this run's nine entries), recorded rather than sliced because it is an accordion of headings with a search box, where the list *is* the content. Comment and docs only.
- **v0.463.2** — PRIORITY 3 (friendliness), the third and last surface of the same sweep: **the Stack form — the app's other descriptor-driven wall of jargon — linked 20 of its 36 controls, and the seven it was missing include the three drizzle knobs whose own checkbox already links the entry.** *Drizzle pixfrac*, *Drizzle scale*, *Drizzle kernel* and *Canvas mode* now point at `drizzle` / `mosaic`; *Quality weighting* and *Photometric normalization* got the two entries the glossary did not have (`quality-weighting`, `photometric-normalisation`, written in the file's own voice); and *Match mosaic panel brightness* links `mosaic`, whose entry gains the overlap sentence that makes that honest — the same move v0.463.0 made for *Neutralize background*, and for the same reason: one concept, one entry, rather than a near-duplicate per control. **27 of 36 linked**, and the nine that are not are named in `_STACK_OPTIONS_THAT_EXPLAIN_THEMSELVES` with the reason — including `auto_reject`, which resolves *to* two controls that each link their own entry, so a reader following it would land on whichever method this run happened not to pick, and `mono`, deliberately unexplained because AGENTS.md §1 deprioritises that area. Descriptor data only — no code path, config, schema, on-disk, API-shape or default change, and no frontend change (`StackOptionControl` has rendered the glyph since v0.461.0). Tests +1 in `tests/test_glossary_links.py`, **failing before** with all seven controls named.
- **v0.463.1** — PRIORITY 3 (friendliness), the same measurement one screen along: **the frames table's "What do these numbers mean?" disclosure explained five jargon headings in a sentence each and offered one link out — to FWHM, whichever word you were stuck on.** `Ecc.` and `Transp.` are words a beginner has never met, on the page they spend the most time on. `FrameColumn` gains `glossary?: { slug, term }` and each measured column carries its own entry (`fwhm`, `star-count`, `eccentricity`, `sky-background`, `transparency`), rendered as the existing `GlossaryLink` book glyph beside the heading — in the heading row, next to the word it explains, adding no height. **`term` is carried separately from `label` on purpose:** `GlossaryLink` builds its accessible name from what it is handed, so passing the heading through would have asked *"what is ecc.?"*, which is the question rather than the answer. The date column keeps no link deliberately — its own sentence is the whole explanation — and that absence is asserted rather than left to chance. Nothing removed: the tooltips, the trailing link to the full glossary and the keyboard-shortcut line are untouched. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change. Tests +3 vitest (**two fail before**) and +1 Python guard in `tests/test_glossary_links.py`, because a slug written by hand in a `.ts` file is one nothing else in the build can notice going stale.
- **v0.463.0** — PRIORITY 1 (the editor), found by measuring the glossary's own promise rather than by reading a screen: **`seestack/data/glossary.md` says it is "meant to cover everything the interface says out loud", and the editor — the surface densest in words nobody arrives knowing — had 13 of its 21 controls with no entry to point at.** v0.461.0 built the link (`GlossaryLink`, `OpSpec.glossary`) and wired the eight ops whose concept already had a heading; *Deconvolution*, *Star reduction*, *Levels*, *Curves*, *Saturation*, *White balance*, *Sharpen*, *Boost nebula* and *Neutralize background* had none, so the beginner most likely to be stuck got the one control the glossary could not explain. Seven new entries (`sharpening`, `deconvolution`, `star-reduction`, `levels`, `curves`, `saturation`, `white-balance`) written in the file's own voice, plus a sentence on `colour-calibration` naming *Neutralize background* as the after-the-stretch half of the same job — which is what lets that op link an existing entry honestly instead of getting a near-duplicate one. Nine `OpSpec.glossary` slugs; **18 of 21 ops linked**, and the three that are not (`geometry.crop`/`rotate`/`resize`) are named in `_OPS_THAT_EXPLAIN_THEMSELVES` with the reason, so the next op registered has to take the decision rather than inherit a silent absence. Data and prose only — no code path, config, schema, on-disk, API-shape or default change, and the frontend needed nothing (the link is descriptor-driven and self-hiding). Tests +1 in `tests/test_glossary_links.py`, **failing before** with all nine ops named.
- **v0.462.2** — ⚪ INFRA (the dogfood tooling's own honesty), found by *running* `--calibration` rather than reading it: **the pass's one line about broken photosites read two keys `/api/calibration/defects` has never sent.** The endpoint answers `{"masters": [...], "repair": offer|None}`; the probe read `offer_repair` and `summary`, so on the first pass that actually built a master **and was being offered the repair** (`repair.state: "off"`, action *"Repair them"*) it printed `offer=None` and then dumped the raw dict — the line meant to say whether the offer fires said the opposite of the truth and buried the truth in its own fallback. That is the failure this repo keeps writing guards against: a check that answers `None` when it cannot find its subject enforces nothing, and a pass reading it comes back "clean" about a surface it never saw. The probe now prints the offer's state and message plus one census line per master, and says *"the endpoint shape moved; fix this probe"* rather than `None` if neither key is there. Tests +3 in `tests/webapp/test_dogfood_defects_probe.py` — the names the script reads against the names a real library's endpoint sends, pinned from **both** sides (including that the endpoint never grew the two wrong names, which would have made the guard vacuous); **two fail before**. Tooling only; nothing in the app changed.
- **v0.462.1** — 🟡 BUG (friendliness + image quality — PRIORITY 3/4), Builder-found the same run by asking which surfaces quote the drizzle bar and in what unit: **the sentence under the Drizzle checkbox — and the glossary entry that control has linked to since v0.461.0 — recommended it from the target's *frame total*, the one unit the engine says it must never be counted in.** `drizzle_path.py` states the rule outright ("It is a per-**pixel** count, not a target's frame total … Every surface that quotes this bar must feed it the depth, not the total"), and v0.436.0 moved the Stack form's own cautions onto `samplesPerPixel` for exactly this reason. The three sentences a beginner actually reads had not moved: the `drizzle` field help said *"Best with 200+ dithered frames"*, the glossary said *"enable it once you have 200+ aligned frames"*, and the **engine's own recommendation** — the source both were quoting — said *"lots of dithered frames (typically 200+)"*, with the unit only appearing twelve lines later in the constant's comment. The error runs one way and toward harm on the owner's own shape: a 3×3 raster 900 subs deep has ~100 on any pixel, so a mosaic user clears a bar he is nowhere near, and drizzle on a thin canvas comes back slower, noisier and gappier. Two neighbours in the same class went with it — "Auto outlier removal … for your number of subs" (it sizes from the **thinnest panel's depth**, `_resolve_auto_reject(depth=)`) and min/max's "Needs 3+ frames" (the accumulator counts per pixel, and the glossary already said so). Copy only; no behaviour, config, schema, API or default change. Tests +3 in `tests/test_drizzle_bar_mirror.py` — the number already had a mirror guard, the *unit* now has one too, over all three surfaces — **all three fail before**.
- **v0.462.0** — 🟠 BUG (trust + friendliness — PRIORITY 3), Builder-verified against the code from observer issue [#933](https://github.com/JimmyeJones/astrostack/issues/933): **the Stack form's "about how long will this take?" priced every run from timings the *previous* build measured, and said it as confidently as one measured by this one.** `seestack/stacktime.py` splits its basis on three axes — cost class, canvas ratio, minimum basis frames — and its docstring says "comparable" is deliberately strict "because a wrong number here costs more trust than no number at all". It did not split on `engine_version`, and nothing in the path did: `estimate_stack_seconds` took the five most recent qualifying runs whatever engine wrote them. The only upgrade the docstring anticipated was the *first* one, where the timing column is new and there is nothing to read. Measured on the owner's install: six restacks with **identical** target, sub count, canvas and options ran 8.1–36.4 % slower across one version boundary (median +16.9 %) against a same-engine control of **+0.4 %** (−4.6 %..+8.1 %) over 11 repeats — so the form under-stated all six by **7.0–24.9 %**, one direction, 6.0 h shown for 6.9 h of work, on a batch then walking all 95 targets. The app already knew: `reprocess_status` calls a target *outdated* on exactly `run.engine_version != APP_VERSION` and offers to restack it — then the form priced that restack from the old build's rate without saying so. Fixed by **preferring** this build's own timings (`estimate_stack_seconds(engine_version=)`: one run of the code about to execute outvotes five of code that is not) and, when there are none to prefer, still answering but flagging it — `StackTimeEstimate.same_engine` → the endpoint's additive `same_engine` field → `stackTimeLine` appends *"which ran on a different version of AstroStack — the real time may differ"*. Deliberately **not** silence: going quiet would take the form's only answer away on every target for one stack after every upgrade, exactly when the owner is restacking the library *because* the app told him his pictures are outdated. A row with no `engine_version` (pre-schema-9) can never pass as current; asking without naming a version restores the old behaviour byte for byte. Tests +7 engine / +1 API / +3 vitest, **five failing before** with the signature intact and only the logic reverted. Additive response field, no config/schema/on-disk/default change. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.461.0** — ✨ **NEW BEGINNER CAPABILITY** (friendliness — PRIORITY 3), the open half of the v0.423.0 glossary entry (*"the per-screen jargon audit itself: each place that says a term without explaining it can now link `/glossary#slug`"*) and the app's own published promise kept: **`seestack/data/glossary.md` opens by saying *"every entry has its own link — so a screen that uses a word can point straight at the word, and nobody has to leave the app to understand something on screen"* — and in the whole frontend exactly one screen did** (`FrameColumnGuide` → `/glossary#fwhm`). Thirty-eight entries, stable anchors, a page that scrolls to a `#slug` on first paint — reachable only as a nav item you had to already know to go and look for, which is no use to the person stuck on a word. The two screens densest in jargon now offer the explanation **at the word**, via a descriptor field rather than copy edited into twenty components: additive optional `StackOptionField.glossary` on **20** stacking controls (sigma clipping + κ, min/max + count, background flatten/mode/box and the three final-gradient fields, drizzle + its rejection pass, hot-pixel + σ, sub-pixel refine, lucky imaging, scale-dark-to-light, repair-sensor-defects, colour calibration + mode), which reaches the Stack form, Settings' stacking defaults and the editor's parameter panel at once because all three render through `StackOptionControl`; and `OpSpec.glossary` on **9** editor ops (stretch, SCNR, colour calibrate, both background passes, coverage leveling, hot-pixel removal, both denoisers). New `GlossaryLink` renders it as a 14 px book glyph beside the existing `HintIcon`. **A second glyph rather than a longer tooltip, deliberately** — `help` says what the control does to *your picture*, the glossary says what the word *is*, and a Mantine tooltip closes on `pointerleave` so a link inside one is unreachable with a mouse and gone before a finger arrives; **a glyph rather than an underlined label** because `HintLabel` renders inside the control's `<label>`, where a click is forwarded to the control (the v0.374.11 trap one level along — asking what a word means would flip the setting); and **no padding**, so no row is taller and no page grew. A hand-written slug can be wrong *silently* (`_slugify` derives the anchor from the heading text, so a reworded heading breaks one and the page just fails to open the entry), so `tests/test_glossary_links.py` sweeps every slug — the 20 descriptors, the 9 ops, op params **and** the links hard-coded into `.tsx` files, which covers the pre-existing `#fwhm` one, unchecked since it shipped — against the bundled glossary; proved armed by mistyping one. Tests +11 (5 Python, 6 frontend), **4 red under scratch reverts that keep every signature**. Every control without a slug, and every older backend, renders exactly as before; the key is always present and explicitly null. No config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.460.1** — 🟡 BUG (trust — PRIORITY 3), the second task of the same run and the same method: **one alert said *"a typical part of the picture has only 1 sub on it"* and, two clauses later, *"the hands-off auto-stack is waiting until **each part** has at least 3"*.** Only the first is true. The hold releases on `stacker.typical_panel_depth`, a frame-weighted **median**, and that is deliberate — its docstring says taking the thinnest panel instead "would strand the whole target on account of one cell", and `test_autostack_mosaic_depth.py` already pins `typical_panel_depth([40, 40, 40, 3]) == 40`. So a mosaic stacks itself with one corner 3 subs deep, having promised to wait; the error is in the direction that surprises, for the one user whose panels are routinely uneven. **Four more sentences made the same substitution** — `thinStackWarning`, both of `nextBestMove`'s mosaic rungs and `rejectionNote` all said *"so each part of this picture has …"* over a figure `perPixel.ts` is explicit about (*"It is a mean… a mosaic with one deep panel and eight thin ones has pixels on both sides of it"*), one of them four lines under a comment reasoning carefully about exactly that unevenness — while every surface fed by the **backend** already said "a typical part" (the Jobs page's hold lines, the Dashboard's last-night card, `AutoStackThinHoldOut`'s docstring, `overnight.py`). Fixed as the phrase in one place: `A_TYPICAL_PART` in `perPixel.ts`, the module that owns the quantity, with the reason it is that phrase; the hold note now refers back to the clause it already got right (*"waiting until that's at least 3"*). No number, threshold or behaviour moved — this is what the app already does, said accurately — and a single-field target's sentences are untouched. Tests +3, **all three red under a scratch revert of the copy alone**, plus the constant's own case; the two existing assertions pinning the old wording were updated, not loosened. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.460.0** — 🟠 BUG (trust / data loss — PRIORITY 1-adjacent), Builder-found by grepping the app's own copy for a sentence that is a falsifiable claim about behaviour, and traced to the lines before anything was touched: **"Combine into one deep target" permanently deleted every source folder's stacked pictures, saved edits and run history, under its own fine print saying *"keeps every sub — nothing is deleted"*.** `merge_projects` says in its module docstring that *"Stack runs / project meta — those stay per-source"*, and `Library.merge_targets` then `rmtree`s every source target's whole folder — the two sentences are the same fact read twice. So one click, with no confirmation, destroyed each source's `stack_runs` rows, its `output/` tree (FITS, TIFF, preview, coverage + frame-coverage maps, progress reel, share render) and its per-run `project_meta`, **the saved edit recipe first**. The raws survive (they are in `incoming/`, and the frame rows are copied), so "keeps every sub" was true and "nothing is deleted" was not. **Why it stopped being theoretical:** `auto_stack` ships on for fresh installs (v0.391.0) against a camera that writes one folder per night — exactly the population `merge_suggestions` clusters — and nothing filters a suggestion on "has no stacks", so those folders normally *do* hold a picture the app made by itself. New `seestack.io.merge.carry_stack_runs` moves each run's three parts out first: the history row, the output file set — resolved from the stem of `fits_path` and **not** from `output_basename`, because a re-stack archives the old set to `{base}_{stamp}.*` and repoints only the columns, so a carry that trusted the column would copy the newest run's pixels onto the older run's row twice — and the per-run annotations, found by *shape* (`^(.+:)(\d+)$` naming a run this project has) rather than by the nine prefixes `webapp.run_meta` owns, since the engine cannot import `webapp` (§6); a test asserts every registered prefix matches that shape so the two cannot drift. The destination basename is made free first (`_free_basename`): two nights of one Seestar convention are both `master`, and a straight copy would have replaced the destination's own picture with the source's while claiming to keep both. **And a picture that cannot be carried keeps its folder** — `CarryResult.lost` (a full disk, a permission error) makes `merge_targets_result` skip that source's delete and take the partial copies back out, because deleting the folder is the step that makes the loss permanent. Copies rather than moves, deliberately: `copy_stack_runs` is a parameter and only one caller deletes the source, so gutting a project this function does not own would be the worse bug; the transient second copy is freed seconds later. The nudge now says *"and every picture you've already made of it"* and the confirmation names the count, off an additive `pictures_kept` that reads as **unknown** (never zero) on an older backend. Tests +9 Python / +5 frontend; **fail-before verified by scratch reverts with every signature intact** — 3 red in `test_merge.py`, 1 red in the card test. `Library.merge_targets` keeps its signature and `int` return; no config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.459.2** — 🟠 BUG (trust — PRIORITY 3), found by asking what v0.459.0 makes reachable and **reproduced before it was touched**: **a run that scaled its dark on a mixed-exposure target either said nothing at all, or named one of its two sub lengths as though every sub were that length.** The scaling is per *frame* — `apply_raw` is handed each sub's own exposure — but the run's provenance stamp asked `dark_scaling_provenance` about the subs' **median**, so on 4×10 s + 2×30 s subs: with a **10 s dark** the median *is* the dark's own length, the bundle answered "nothing was scaled", the DARKSCAL/DARKDEXP/DARKLEXP cards were omitted entirely and History's "Dark scaled to sub exposure" line never appeared — on the run that had tripled the dark on a third of its frames; with a **30 s dark** the median lands on 10 s and the run stamped *"30s → 10s"*, true of four subs and false of the two it left unscaled. A pre-existing bug, and v0.459.0 makes it the *ordinary* case by binding mixed targets scaled in the first place — so it was fixed in the same run rather than filed. New `CalibrationMasters.dark_scaling_exposures` takes the **set** and returns the dark's exposure plus every distinct length it was applied across; `dark_scaling_provenance` is now implemented in terms of it, so there is still exactly one definition of "did scaling happen?" and its own contract is unchanged (it also, incidentally, stops a non-finite exposure being scaled by). A single-length target keeps `DARKLEXP` and its "30s → 10s" line **byte for byte**; a mixed one stamps new `DARKLEXS` — the set, worded by the engine's own `_join_exposures` so the run Info and the advisory describe one target the same way — carried as an additive `dark_scaling.light_exposures` and rendered as *"Dark matched to each sub · 10s dark across 10s and 30s subs"*, because an arrow there would be the very claim about one length that was wrong. Engine + endpoint + frontend, additive at every layer: an older backend sends no set and reads exactly as today, a newer one sends no set on the single-exposure runs that are all the installed base has. Tests +11 (4 engine, 2 header stamp, 2 endpoint, 3 vitest); **five red** across the three layers under scratch reverts. `tsc`/`vitest` (4,234)/`vite build` clean. No config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.459.1** — 🟠 BUG (trust + image quality — PRIORITY 3/4, Builder-found and **measured** before it was fixed): **a picture's stated integration time was `median sub exposure × frames`, so on a target shot at more than one length it named a number the light was never collected over — by up to ±50 %.** The fourth surface of the v0.456.0 shortcut (*a representative value is a claim that the set is uniform*), and the first one where it is arithmetic rather than wording; found in `seestack/stack/`, which the current focus had closed "until a new bug is found there". Measured on six subs: 4×10 s + 2×30 s holds **100 s** of light and the run reported **60 s** (−40 %); 3×10 s + 3×30 s holds 120 s and reported **180 s** (+50 %); 2×10 s + 4×30 s, 140 s reported as 180 s. That figure is `stack_runs.total_exposure_s` — the `EXPTOTAL` card Siril and PixInsight read off `master.fits`, the hours on every History card, the "N h captured" clause in every shared caption and baked nameplate, and the readiness goal's denominator. New `stacker._typical_sub_exposure_s` keeps the **median** when the subs are all one length (robust, so one mistyped header cannot move a whole stack's figure — and that is every ordinary target, byte-for-byte unchanged) and takes the **mean** when they are genuinely several, which is the only value whose product with the frame count is the light actually collected. "All one length" is the engine's own `distinct_exposures` grouping, so header rounding (9.998 vs 10.0) stays one exposure and a real Seestar step does not — the same question the dark advisory, the Stack form and the master binder already ask. Scaling by `n_used` rather than summing outright is kept deliberately: with every candidate used the mean times the count *is* the sum exactly, and when a sub drops mid-stack it stays the unbiased estimate the figure has always been. The `EXPOSURE` card follows the same typical value so the header cannot contradict itself — a reader multiplying `EXPOSURE` by `NFRAMES` now lands on `EXPTOTAL` — and its comment says *"mean per-sub exposure (s); subs were mixed"* rather than naming a length no sub was shot at. Tests +13 in a new `tests/test_stack_integration_time.py`, **eight red** under a scratch revert of the branch alone, including two end-to-end through a real `run_stack`. No config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.459.0** — 🟠 BUG (autonomy + image quality — PRIORITY 2/4), the open `_auto_bind_for_target` lead filed with v0.456.0/v0.456.1 and the one surface of that family that changes **pixels** rather than sentences: **the walk-away stack bound a master dark against a target's *median* sub exposure and applied it unscaled to the subs that median did not describe.** A target shot at 10 s one night and 30 s the next has a median of 10 s, so a 10 s dark cleared the bind gate and its pedestal was subtracted at full strength from subs integrated three times as long. **What made it decidable without the owner's library — the gate the lead was filed under — is that the app already promises this outcome in writing:** v0.457.0's `partial_detail` tells the beginner *"Build a master bias and AstroStack can scale this dark to all of them"*, and reproduced against the real binder, building that bias changed nothing (`{'dark_master_id': 1}`, no `scale_dark_to_light`) — the dark never reaches the scaling branch, because it passed the median test. `auto_bind_master_ids`/`auto_bind_master_paths` now take `light_exposures_s` (the target's **distinct** lengths, from the engine's own `distinct_exposures`) and ask the binder's own `dark_exposure_split` — the same 25 % gate, the same function the Calibration page's note is written from — whether the dark reaches **every** length; when it reaches some but not all, the *same* dark is bound scaled instead, which is per-frame correct by construction because `apply_raw` is handed each frame's own exposure (ratio exactly 1, i.e. the plain dark, on the subs it already matched). **It can only ever add `scale_dark_to_light` + the bias to a binding it already makes:** it never chooses a different dark, and with no confident bias to scale by a mixed target keeps today's unscaled binding rather than losing calibration on the 95 % — the lead's own instruction, and the run's advisory names the shortfall either way. The Stack form needed no change: `calibrationFit.masterRecommendation` already reads `scale_dark_to_light` off `confident`, so "Use recommended" now lands on the same picks the walk-away stack makes. Wired at all three callers (`pipeline._confident_master_binding`, `calibration-suggestions`, `master_coverage`), so the roll-up's "covers this only partly" note retires itself for the targets it just fixed. A uniform target — every ordinary one, and every caller that passes no set — is byte-for-byte unchanged. Tests +8, **three red under a scratch revert that keeps the new signature** (a `TypeError` is not a fail-before). No config, schema, on-disk, API-shape or default change; `auto_bind_calibration` is still off by default. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.458.3** — 🟡 BUG (trust — PRIORITY 3), the third finding of the same run and the one that explains why that pass's numbers had moved: **the panel count on a target's own card was answered for whichever telescope the library probe reached first.** `frame_field.library_frame_field` answers *"what field does this owner's telescope have?"* for the **library**, newest-activity-first — the only answer the Tonight planner could use, and a guess on a card sitting under **one target's** picture. Measured on the app's own samples: a `--mosaic --big` pass holds two mosaic targets whose panels are 480×320 and 900×600 at 5″/px (40′ × 26.7′ and 75′ × 50′), the probe answers **75′ × 50′ for both**, and the 2×2 sample's card read *"About a 2×2 mosaic (4 panels) covers all of it"* — about a target that **is** a 2×2 — where its own frames give **3×3 (9 panels)**, the number `PROCESS-NOTES.md`'s 2026-09-14 record quotes for that sample. The claim had moved when `--big` shipped (v0.446.0) with nothing about the sample changing, which is the shape of phantom regression a future run would have chased. New `frame_field.target_frame_field` asks the same one-row `Project.solved_frame_geometry` of the target being identified; `identify_target` prefers it and falls back to the library-wide probe for a target with nothing solved. **On a one-telescope install the two are identical and nothing changes** — hence a patch, not a flip. Tests +2, one red under a scratch revert. One extra SQLite open on a request that had already opened the library; no config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.458.2** — 🟠 BUG (trust — PRIORITY 3), the other half of v0.458.1's object box, found by measuring the thing that entry had just filed as "deliberately not changed": **the crop the card offers to fix an off-centre picture measured the square too, so the card promised a re-centring and then withheld the button.** `framing_result_verdict` says *"all in this frame, but sits well off to one side — re-centring it next session would give it more room"*; `recentre_outcome` is the app *doing* that to the picture the owner already has, and it sized its clear-space margin around a **square of the major axis** — a strictly harder test than the verdict beside it had just passed. Measured: a 30′ × 10′ object half-way out to the bottom edge of a 1000 × 800 canvas at 5″/px is `off_centre` with coverage 1.0, and the offer came back `reason="cramped"`; asked about the object's real box it returns a crop keeping **46 %**, comfortably past the 40 % floor that exists to stop a bad offer. Nothing marginal about the crop — the refusal was measuring the wrong shape. `recentre_outcome`/`recentre_crop` now take `size_minor_arcmin` and test the margin **per axis** against the same box the verdict lays along the canvas's long edge, fed by the same `framing_payload` line. The change can only ever *relax* the test (the minor half-extent is clamped to the major), so an offer that existed before still exists and is never smaller — pinned, not argued. Tests +4, one engine repro red under a scratch revert and one endpoint test red when the argument is dropped. Two optional keywords with square-box defaults; `_RECENTRE_MARGIN`/`_RECENTRE_TOLERANCE`/`_RECENTRE_MIN_KEPT` untouched; no config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.458.1** — 🟠 BUG (trust + autonomy — PRIORITY 2/3), Builder-found by reading a `--mosaic` dogfood pass's Target-page block as one paragraph and then reproduced off the sample, on the owner's own S30 field and a real catalogue row: **the framing verdict measured a square where the panel count printed beside it measured a galaxy.** `seestack.framing.framing_result_verdict` modelled every object as a **square box of its major axis**, while `mosaic_plan` and `field_fill` — the two lines that land on the *same* card — model it as **major × minor** and fall back to the square only when the catalogue records no minor axis. Measured: M 31 (178′ × 63′) dead centre in the **2×1** mosaic `mosaic_plan` itself prescribes for an S30 (canvas 243′ × 72′) holds **all** of the galaxy, and the card read *"M 31 is bigger than this mosaic — only about 40% of it is in this picture. Adding more panels next session would capture the rest."* directly above *"About a 2×1 mosaic (2 panels) covers all of it."* — add panels to a grid the same card says already covers it, about a picture containing every pixel. The 40 % is `178×72/178²`, the square running off the short edge of a canvas the galaxy fits inside. The verdict now takes `size_minor_arcmin` (threaded through `ObjectInfo` → `framing_advice.framing_payload`) and lays the box along the **canvas's long edge**, the identical convention the panel count the owner is being asked to go and shoot already makes. **23 of 157 bundled objects record a minor axis, 11 materially elongated** — the mosaic population; every other object and every caller passing none gets byte-identical sentences (`minor_px` defaults to `major_px`, the old expression term for term), pinned across `None`/`0`/negative/swapped axes. (`recentre_outcome` was left on the major-axis radius here and **closed by v0.458.2 above** — the "safe direction" turned out to be the one where the card promises a re-centring and then withholds the button.) Tests +7, **four fail before** under a scratch revert. One optional keyword, one additive dataclass field; no config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.458.0** — 🔴 BUG (image quality / correctness — PRIORITY 4 and `seestack/calibrate/` re-opened by it, Builder-found and reproduced end-to-end): **a master dark built from a folder holding two sub lengths is a photograph of neither.** `masters.build_master` combined every frame and stamped `np.median(exposures)`: 100 ADU (10 s) and 300 ADU (30 s) darks in, a **200 ADU** master stamped **20 s** out — then subtracted unscaled, over-subtracting from every short light and under-subtracting from every long one. `discover.classify_frames` groups by folder and asks only the *kind*, so nothing prevents that folder. Fixed with the majority-**exposure** gate that mirrors the existing majority-**shape** gate (grouped by the engine's own `distinct_exposures`, shortest wins a tie, a frame with no recorded exposure is kept, flats/biases deliberately exempt), and the Jobs line now tells the owner to put the set-aside darks in their own folder and build a second master. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.457.1** — 🟠 BUG (friendliness — PRIORITY 3, Builder-verified by reproduction): **the "How to add darks" guide told a beginner to shoot a night of darks at a length none of their subs was shot at.** The sixth surface of the v0.456.0 shortcut — `seestack/stackhealth.py::recommended_dark_spec` takes the median exposure, and `DarksGuide` renders it as *"at the same settings as your subs — 20 s at gain 80"* on a target shot at 10 s and 30 s. `DarkSpec.exposures_s` (the engine's own `distinct_exposures`) now travels beside the median, `formatDarkSpec` names the set, and `darkSpecPerLengthNote` says a target shot at two lengths needs a set of darks at each. Gain deliberately untouched. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.457.0** — 🟠 BUG (friendliness + trust, Builder-verified by reproduction): **the Calibration page's coverage roll-up described a target by a length no sub of it was shot at, and called a dark "covering" when it matched none of its frames.** The fifth surface of the v0.456.0 shortcut — `webapp/routers/calibration.py::_target_acquisition` reduces a target's subs to `_median(exposure_s)`, so on an evenly split 10 s / 30 s target `uncovered_detail` said *"Shoot them at 20s — that's what those subs were shot at"* (a night of darks at a length matching nothing), `missed_detail` said *"your subs are 20s"*, and a 20 s dark was reported as covering it. Now `exposures_s` (the engine's own `distinct_exposures`) travels beside the median, new `calibration.dark_exposure_split` answers which subs a dark reaches on the binder's own 25 % gate, and `master_coverage` gains `n_partial`/`partial_detail`. **Which masters bind is unchanged** — the binder's `_auto_bind_for_target` median is the separate open lead, and this entry changes no pixel. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.455.7** — 🟡 BUG (friendliness + performance at the owner's own scale — PRIORITY 3), the third and smallest finding of the same run and the same class as v0.455.6: **the Target page and the Stack form asked the identical question under two cache keys.** `routes/Stack.tsx` read the frame list under `["frames", safe]` against the table's `["frames", safe, sort, order]`, while both call `api.listFrames(safe)` — defaults `sort=id`/`order=asc`, one identical request — so clicking "Stack" from the page you were just on re-downloaded the whole list under a cold key: **2.9 MB at 5,477 subs, 19.1 MB over 18 sequential requests at 35,894**, for rows already in memory, and blocking (several pre-flight advisories are gated on `!frames.isLoading`). Now keyed `["frames", safe, "id", "asc"]` — the table's own default-sort entry. Sound whatever the table is sorted by, because nothing on the form reads the list *in order* (four `.filter().length`s and `detectMixedPointings`), and a re-sorted table just leaves the form its own entry as today; every `invalidateQueries(["frames", safe])` still matches by prefix. **The test needed the app's real numbers**, which is the durable half: the claim is about caching, and TanStack's bare `staleTime: 0` makes every entry stale on arrival, so a hand-written client refetches and the claim is untestable for a reason unrelated to the code — the defaults moved out of `main.tsx` (which a test cannot import without rendering the app) into `frontend/src/queryDefaults.ts` (`QUERY_DEFAULTS`, `QUERY_STALE_TIME_MS`), so the test asserts the configuration that ships. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change. Tests +2, one red under a scratch revert. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.455.6** — 🟠 BUG (friendliness + performance at the owner's own scale — PRIORITY 3), Builder-found the same run and **measured against the running app**: **grading one sub re-downloaded every sub — 19.1 MB over 18 sequential requests per keystroke on his deepest target.** `routes/Target.tsx`'s single-frame `patch` mutation (the `a`/`r` keys and every row's accept toggle) ended in `invalidateQueries(["frames", safe])`, which prefix-matches the page's own `["frames", safe, sort, order]` and the Stack form's key, over a list that is **deliberately complete** (`api.listFrames` pages until it holds every sub — a 2,000-row cap once hid the newest frames from the table, the keyboard grading and the Stack pre-flight guards). Measured on the dogfood install: 1,200 rows = 636,988 bytes, i.e. **531 bytes a row** and a floor, so **2.9 MB at 5,477 subs and 19.1 MB at 35,894** — per grade, on the one action done dozens of times in a row, from a phone over a NAS. `PATCH …/frames/{id}` writes one row and returns it whole (`FramePatch` = accept / reject_reason / user_override / bayer_pattern, none of them one of the table's sort keys), so the refetched list would differ in exactly that row: new pure `components/target/frameCache.ts::replaceFrameInList` + `qc.setQueriesData` swaps it into every cached sort/order variant for no bytes, and returns the **same array** when the id is absent so another target's cache is untouched. **Bulk actions deliberately keep invalidating** (many rows, server-computed reasons, ids not rows, a click not a keystroke); `["target", safe]` and `["reject-summary", safe]` still invalidate. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change, and the page shows what it showed before. Tests +6, the page ones shaped so the **request count** is what fails — red under a scratch revert with `expected 2 to be 1`. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.456.1** — 🟠 BUG (friendliness + trust — PRIORITY 3), the sibling v0.456.0 named, and not a follow-up tidy: **the Stack form was still asking the *median* exposure, so it and the finished run disagreed about one target.** `routers/calibration.py` reduced the subs to `_median([f.exposure_s …])` and `routes/Stack.tsx` rendered it as "your subs are Ns" — false however N is chosen on a target shot at 10 s one night and 30 s the next, and on an even split it names **20 s, a length no sub was shot at**. Worse, a 20 s dark is then a *perfect* match for that median, so the form said nothing at all about a dark that is wrong on every single frame; the same median also decided `darkExpMismatch`. This endpoint's stated contract (the reason it serves `tolerances`) is that the form warns about exactly the pairs the run complains about, and v0.456.0 had made the run smarter than the form. Now `params.exposures_s` serves the **distinct** lengths from the same `calibrate.apply.distinct_exposures` the engine groups with, `calibrationFit.mismatchedExposures` asks the existing `exposureMismatch` test of every length (one-sided, like every other check in that file), and `joinExposures` mirrors the engine's `_join_exposures` so one target is described the same way before the night is spent and after. The sentence names only the subs the dark is actually wrong for — a 10 s dark is right for two-thirds of them, and "a mismatched dark" flat would be as wrong as saying nothing. A one-exposure target is untouched, including against an older backend that serves no set, pinned by a test. Tests +7; **four fail before** (two `Stack.test.tsx` under a scratch revert, two endpoint). One additive optional response field; the median is still served, so old/new mix in either direction. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.456.0** — 🟠 BUG (image quality + trust — PRIORITY 1-adjacent/4), Builder-found and reproduced 2026-09-18: **a target is not necessarily one exposure, and the master-dark advisory assumed it was.** `run_stack` asked `CalibrationMasters.calibration_warnings` about `ref.exposure_s` — the **reference frame's** — under a comment saying it "stands in for the (uniform) session". Nothing makes a session uniform: shoot a target at 10 s one night and 30 s the next and it is one target with two exposures in it, and `pick_reference_frame` (which chooses on quality and pointing, and has never heard of exposure) then silently decided whether the advisory fired at all. Measured: with a 10 s dark and subs at 10 s and 30 s, a 10 s reference gave `[]` and a 30 s reference gave the full warning — same target, same masters, same subs — and the warning that did appear claimed the pedestal was wrong "on every frame", which is false for the subs the dark matches. The 30 s subs get that dark subtracted **unscaled** either way (`_effective_dark` is handed each frame's own exposure, so the scaling path was already per-frame correct; only the telling was broken), leaving residual dark current on part of the stack with nothing saying so. `calibration_warnings` now takes `light_exposures_s` — every light's exposure — and `run_stack` hands over the frames it is stacking; new pure `calibrate.apply.distinct_exposures` groups them with `EXPOSURE_MISMATCH_TOL`, the module's own "same exposure?" constant, so header rounding (9.998 vs 10.0) is one length and a Seestar step (10 → 20 → 30 s) is never one, grouping against each group's first member so a ramp cannot chain, naming each group by its median, and dropping missing/non-finite/non-positive values rather than inventing a mismatch out of a blank FITS card. **A one-exposure target is untouched and that is pinned, not asserted** — the mixed branch is separate, and a test asserts a uniform set (and a rounding-spread set, and a set of `None`s) returns *exactly* what the reference frame alone returned; mixed subs with exposure-scaling on stay silent, correctly. Tests +7, **all seven fail before**, the load-bearing one at `run_stack` level using no new API (`calibration_warnings=[]` before, named warning after). Advisory only — no pixel, config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.455.5** — 🟠 BUG (friendliness + performance at the owner's own scale — PRIORITY 3), Builder-found and measured 2026-09-17: **the mixed-pointing pre-flight guard tested every pair of subs, on a bound a later fix had removed under it — 15.3 s of frozen tab on his deepest target.** `frontend/src/components/target/mixedPointings.ts` clustered the accepted+solved pointings with an all-pairs loop whose own comment called it *"O(n²), bounded by the 2000-frame list cap"* — a cap `api.listFrames` no longer has, because the truncation fix made it page until it holds every sub. Measured on that exact code, one dithered pointing (the common case *is* the worst case — every pair is inside the 3° link distance): **474 ms at 5,477 subs and 15.3 s at 35,894**, his two deepest targets, **synchronously inside the `useMemo` that renders `routes/Target.tsx` and `routes/Stack.tsx`** — so a tab that stops responding, with no spinner, on the page he opens every session from a phone. The linkage now runs on a cube grid (`CELL_AXIS`/`CELL_REACH`/`cellKey`) whose body diagonal is exactly the link chord, so a shared cube is a link *by construction* (all 35,894 subs of one pointing land in one) and only the ±2 neighbourhood is ever visited, stopping at the first linking pair because rule 1 leaves each cube internally connected. **No threshold moved and nothing is approximated** — `LINK_DIST_DEG` and `MIN_POINTING_FRAMES` are untouched and the partition is identical, pinned by an exhaustive all-pairs oracle (written longhand in the test, not imported) over 250 seeded random skies including both poles, the RA=0 seam, and spreads at 2.9°/3.1°. **15,305 ms → 3.2 ms**; 25-panel mosaic 11,286 ms → 25.4 ms. Tests +4, **three red under a scratch revert** at 10,992 / 6,945 / 7,800 ms against an asserted 1,500 ms budget. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change, and the warning fires on exactly the batches it fired on before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.455.4** — ⚪ DOC-ONLY follow-up to v0.455.3, from reading its own first pass: the `--deep` target is by far the deepest in the scratch library, so **every prescriptive card on `/tonight` names it** — correct behaviour, but it makes a `--deep` pass a poor one on which to read that column as one paragraph (the thing `dogfood_probe.mjs` prints it for). Named as a caveat in the flag's help and in AGENTS.md §7 so the next run expects it rather than investigating it. No code change.
- **v0.455.3** — 🟠 INFRA (the dogfood tooling's next structural blind spot, one layer below the last four): **`scripts/agent-dogfood.sh --deep` — no pass had ever held the owner's *scale*.** Every sample was six subs per pointing against his 5,477 and 35,894, and the probe measures **page height**, which the frames table's scroll container makes independent of its rows by construction. A fourth demo target (`sample_data` shape `"deep"`, one field shot 1,200 times, deliberately un-stacked, small sensor because QC is per-frame) plus `scripts/dogfood_deep.mjs`, which measures rows-against-subs, DOM node count and first paint, and scrolls the table's foot to exercise the auto-grow jsdom structurally cannot reach. Verified in both directions on the real app. Tests +13. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.455.2** — 🟠 BUG (friendliness + performance at the owner's own scale — PRIORITY 3), Builder-found and measured 2026-09-17: **the Target page rendered one DOM row per sub, so his 5,477-sub target put ~121,000 nodes into a table that can show twenty of them.** New pure `frontend/src/frameWindow.ts` (`FRAME_WINDOW_STEP`, `growFrameWindow`, `frameWindowForIndex`, `frameWindowNote`) windows the *rows* while leaving the *list* complete, so every badge and outlier test on the page stays exact. Measured with the real component: 5,477 subs **120,727 → 6,840 nodes** and **41.1 s → 2.6 s** to first paint (jsdom), 2,000 subs 44,233 → 6,840, and 20 and 200 subs **byte-identical** — the cost is now flat in the number of subs. Nothing removed (the owner's one hard constraint): the window grows as the table is scrolled, and its foot carries a "Show all N" button as the guaranteed path. Frontend-only. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.455.1** — 🟠 INFRA (the dogfood tooling's last named structural blind spot): **`scripts/agent-dogfood.sh --calibration` — no pass had ever held a master dark.** Every run ever recorded had an empty calibration registry, so the masters list, `/api/calibration/incoming`'s one-click offer, `/api/calibration/defects` and its repair offer, the per-target `calibration-suggestions`, `auto_bind_calibration` and the "darks were applied" half of the stack-health vocabulary had only been photographed empty — on an app that tells the owner on *every* stack that adding darks is the single biggest cleanup available to him. Same shape as the missing observing site (v0.436.1), the empty `incoming/` (v0.442.0) and the click-only Compare modes (v0.440.2), and it paid the same way: **v0.455.0 was found while building it.** New `webapp.sample_data.write_sample_calibration_frames` generates darks/flats/biases matching the sample lights' own `EXPTIME`/`GAIN`/`CCD-TEMP`/sensor size (a mismatched master is refused by the registry, which would leave the pass in the empty state it is escaping, silently), each declaring `IMAGETYP` because that card and never a folder name is what `discover` classifies from, with the darks' hot pixels a **fixed pattern** across the set (a moving one is erased by the median combine and the defect census then finds a clean camera — pinned by a test). The script seeds them into the scratch `incoming/` and makes the app **discover and build them itself** through the beginner's endpoints, prints the offer / registry / defect census / suggestions / health note, and turns on `auto_bind_calibration` before the stack. **Caveat stated in its own output:** the samples' lights carry no hot pixels and no vignette, so the masters reach the *surfaces* without improving the *picture*. Tests +4; no production behaviour touched. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.455.0** — 🟠 BUG (autonomy / library hygiene — PRIORITY 2), Builder-found 2026-09-17 by putting a scratch install into the one state no dogfood pass had ever been in, and reproduced before anything moved: **a folder of darks under `incoming/` became a light target, in the one place the app itself told the owner to put them.** The Calibration page's build form is placeheld `/data/incoming/darks` and asks for "a Seestar `Dark` folder on your NAS"; `GET /api/calibration/incoming` is an entire shipped feature whose premise is that calibration folders live under `incoming/`; and `seestack/io/scanner.py` had **no notion of a calibration frame at all**, so exactly those folders were ingested as targets — a "Darks 10s" of six lights on the Library wall and in the Gallery, counted into the campaign stats, offered by the planner, chipped "Not stretched yet", stackable into a picture of nothing. Two halves of one app disagreeing about what the same files are, the #880 junk-target shape arriving from a folder the app asked for. Fixed by giving the scan `discover.classify_frames` — the rule extracted from `classify_folder`, i.e. **literally the one the build offer is decided by** — so the set the offer lists and the set the scan passes over are one set by construction rather than two implementations agreeing. The rule is strict and one-sided (every sampled header must declare a recognised calibration kind; a frame that says nothing, which is what an ordinary Seestar sub says, rules the unit out on the **first** read), so a healthy library pays one header per folder and a night of real subs cannot be lost to it however the folder is named — four of the seven new scanner tests are about *not* skipping, including a folder called "Darks" full of subs and one light dropped among the darks. The skip carries `discover.MIN_FRAMES` **deliberately**, because that is what makes the two sets identical, which is what lets `webapp/incominglag.py` exclude them without opening anything under `incoming/` (AGENTS.md §10) — otherwise the "subs waiting" note would complain for ever about the folder the app asked for. `plan_incoming_units` still plans them (it may not read headers — it runs on every watcher poll), and that one deliberate divergence is now pinned by a test rather than left to be found. Upgrade-safe: a library that already holds a "Darks" target keeps it untouched — nothing is deleted or renamed — new scans simply stop minting more; one additive `ScanResult` field, no config, schema, on-disk, API-shape or default change. Tests +14 (7 scanner, 2 pure lag, 1 endpoint, 1 plan-divergence, 4 sample-writer wait — 3+1 fail-before verified by scratch-reverting the fix and the wiring separately). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.454.0** — 🟠 BUG (trust / image-quality reporting — PRIORITY 3/4), Builder-verified from the open "estimator drift" lead under Infra (which asked exactly this question of the other stored columns and named `noise_sigma` as lead one — checked and cleared 2026-09-17; **this is lead two, and it holds**): **a perfectly clear mosaic still wears a "Hazy night" badge, because v0.304.2 fixed the estimator and dated nothing.** `transparency_score` is the median flux of a frame's brightest *stars*, so up to v0.304.1 the per-run `transparency_ratio` divided by ONE target-wide `p90` baseline — set by whichever mosaic panel has the richest star field, so every other panel read as haze. Reproduced on the three-panel fixture the v0.304.2 fix already ships: one steady sky stores **0.5001** and measures **0.9996** today, i.e. either side of `HAZY_RATIO = 0.6` — so every mosaic run stacked before 2026-08-30 is still stamped "Hazy night" on History, Gallery and Compare, telling the owner (26 mosaics, months of runs) to **reject his haziest subs** on nights when nothing about the weather changed. Fixed the way `seam_scale` fixed its twin: a new additive `stack_runs.transparency_scale` stamped by `run_stack` with `TRANSPARENCY_ESTIMATOR_GENERATION`, dated by `engine_version` for every row written before it, and one shared reading rule (`stackhealth.readable_transparency_ratio` → `stored_hazy_verdict_for`) served as an additive `hazy_verdict` to all three surfaces, with `HAZY_RATIO` moved out of `HazyNightBadge.tsx` into the engine beside `seam_verdict`'s thresholds. **It withholds rather than heals, and that is forced:** `seam_residual` can be re-measured because its input is still on disk, whereas this figure's input is *which frames the run used* and no column records it. **And it withholds outright rather than reading one half**, because the scale change is **two-sided** where the seam's was one-sided — measured over 300 randomised mosaics, today's estimator reads higher on 251 (to +0.72) and lower on 49 (to −0.27), a property a test now pins so the rule can be revisited rather than rediscovered. Precisely scoped: a **single-field** run of any vintage is never withheld (`_panel_transparency_ratios` returns `[]` there, i.e. the old answer exactly), no stored figure is rewritten or cleared, and the export path — which inherits the ratio but deliberately not `is_mosaic`, and carries today's `engine_version` — now reads its source through the same rule at both write and read time, so the badge cannot be laundered past the fix by an edit. Upgrade-safe: no `SCHEMA_VERSION` bump (the un-gated `ALTER`, so the upgrade stays rollable), additive optional response fields, older backend falls back to reading the ratio. Tests +17 (13 Python, 4 frontend), fail-before verified twice by scratch-reverting the fix (two engine tests red on the raw read; the frozen-DDL migration guard red on the missing `ALTER`). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.453.6** — 🟡 BUG (friendliness / trust — PRIORITY 3), Builder-found and fixed the same run, and it really does close the class: **the caption sweep fixed four surfaces and there were five — the fifth is the editor, where the picture is actually finished.** `postCaptionForRun`'s own doc comment names the four it was written for (the Target hero's menu, that hero's lightbox, every History run card, the Gallery viewer; v0.453.2 added the "My best pictures" wall), and none of them is the editor: it has its own share job and its own server-built caption, so it was still handing over `seestack.sharecard.share_blurb`'s *"M 42 · 15–18 Nov 2024 · 3.2 h · 152 subs"* as both the "Caption to paste" line under its Export panel and the text given to the OS share sheet — on the screen a beginner reaches *having just made* the picture they want to post. The sweep missed it because all four fixes were found by following `SavePictureMenu`'s callers and the editor calls none of them (`share_blurb` has exactly one production caller, `pipeline.submit_editor_share`). `Editor.tsx` now builds `postCaptionForRun` from the run row and the identity it already holds — `["identify", safe]` it has fetched for years, and a `["runs", safe]` `useQuery` on the key the Target and History pages warm, so arriving from either is a cache hit — with the share sheet's **title** left as the terse line, the split v0.453.1 settled on. **`scaleBar` is deliberately null**: every other surface captions the run's *stored preview*, whose geometry `storedPreviewScaleBar` knows, while the editor renders the *master* through the user's own recipe, so one crop makes the run's bar describe a different rectangle — and a wrong "5.4 full Moons wide" in a public post is worse than no clause. A missing run row, a failed list read or an older backend falls back to the server blurb, byte for byte. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change. Tests +2, both red under a scratch revert; the existing blurb test is unchanged and now pins the fallback it was always testing. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.453.5** — 🟡 FLAKY TEST ON `main`, found by this run's pre-merge suite and **reproduced on unmodified `origin/main`** before being touched: **`test_skipped_folders.py` was the only file in `tests/webapp` waiting on a *scan* job for 60 s.** `test_a_scan_remembers_the_folder_it_could_not_account_for` failed on `job … did not finish in 60s` — a wall-clock timeout in the file's own `_wait_job`, not an assertion, with its captured log showing the scan had run and emitted its warning. It is load- and ordering-dependent: green alone (17 passed, 82 s), green for `tests/webapp` entire under `-n 4` (2,339 passed), and red on the *fourth* full suite of a session — the same shape as the `/tmp/pytest-of-root` trap in AGENTS.md §7, and it reads exactly like a red `main`, which §2 makes task #1. It was one. The fix moves **toward** the repo's own convention, not away from it: `test_pipeline.py` passes `timeout=120` at every scan call site, `test_incoming_readonly_guard.py` waits 180, the editor/archive/channel-combine suites all wait 120 — this one file was the outlier. Now a named `_JOB_TIMEOUT_S = 180` carrying the measurement. **Nothing loosened:** every assertion about what the scan remembered is untouched, and a job that genuinely never finishes still fails, two minutes later instead of one. Record in [`PROCESS-NOTES.md`](PROCESS-NOTES.md).
- **v0.453.4** — 🟠 INFRA / the same class, pinned by the source instead of by memory (filed with v0.453.3 directly below): **`tests/test_edit_neighbourhood_drift.py`.** SCNR sat unscaled on the one-click Auto path for five months with `test_edit_proxy_parity.py` — the file whose whole subject is this class, whose header says a 2026-09-09 sweep *“confirmed every current op passes it”* — standing beside it, because that file covers the ops somebody **remembered**; and the whole-recipe composition test could not have caught it either, because the divergence is *localised* (1.00x on a flat cast, 0.68x on green knots) and moves no summary statistic far enough to spend its budget. Two tests aimed at the class, one blind by omission and one by construction. The guard walks `seestack/edit` with `ast`, finds every scipy-ndimage neighbourhood filter (18 names), resolves its `sigma`/`size`/`footprint` through local assignments **and enclosing scopes** (load-bearing — sharpen and deconvolution scale in the op body and filter inside a nested `run`, so a naive scan cries wolf twice on correct code), and requires it to trace to `proxy_scale` or be named in `_UNSCALED_BY_DESIGN` **with a reason**. Thirteen sites: eight resolve, five exempt — and the exemptions are the deliverable, three of them **measured** rather than argued (`classify_target`'s cues hold their verdict across proxy steps 1–8: chroma 0.032 galaxy / 0.447 nebula, ext_frac 0.0254–0.0255; only a sparse cluster at step 5+ moves, and it *declines* rather than guessing). The trap is armed three ways, including running the **pre-v0.453.3 spelling of `_scnr`** through the resolver — and against the real tree with the fix scratch-reverted it goes red naming `seestack/edit/ops/tone.py::_scnr::gaussian_filter(_SCNR_NOISE_SIGMA)`, today's bug by its exact site. Tests +5; no production code touched. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.453.3** — 🟠 BUG (editor preview↔export parity — PRIORITY 1), found by an adversarial read of the editor ops for pixel-unit parameters the proxy does not scale, and measured before anything moved: **the one-click Auto recipe's green-cast removal previewed less green than it saved.** `tone.scnr`'s noise-protected default estimates the green *excess* through a Gaussian whose sigma, `_SCNR_NOISE_SIGMA = 3.0`, is a **full-resolution** pixel measure — and it was handed to `gaussian_filter` unscaled at both resolutions, so the live preview smoothed `proxy_scale` times more sky than the export and *flattened* the excess wherever the cast had structure. Measured on green knots (sigma 2/4/8 full-res px) against the export's own removal at the same pixels: the preview took out **0.83x** at proxy step 2, **0.68x** at step 3, **0.45x** at step 6 — and his mosaics decimate by 2–3, so that is his everyday state. The direction is the dangerous one: judge `amount` on that preview and you save a picture corrected harder than the one you looked at. New pure `tone.scnr_noise_sigma(proxy_scale)` shrinks it for the proxy with a 1 px floor → **1.00 / 1.00 / 0.83x**, whole-canvas divergence 5.5–15.6 % → 0.3–5.5 %; identity at `proxy_scale <= 1`, so **every export and the loupe's 1:1 window are byte-identical**. The floor is the measured half: the smoothing exists because the per-pixel estimator rectifies chroma noise magenta (**+2.05 %** of sky level, vs the export's **+0.20 %**), an unfloored `1/proxy_scale` gets back to **+1.34 %**, the floor caps it at **+0.59 %** — i.e. a 32–55 % structure divergence traded for 0.4 % of sky level, in the preview only, with both directions pinned. No sixth advisory: the residual is ≤ 5 % at every step he reaches. Tests +5 in `tests/test_edit_proxy_parity.py` (which exists for this class and did not carry SCNR), **four red under a scratch revert**. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.453.2** — 🟡 PRIORITY 3 (enjoy/share), closing the class v0.453.0/.1 opened: **"My best pictures" — the page you open to show someone your pictures — shares them with their story.** Its viewer was the last of four to hand the OS share sheet `sharePictureText`'s *"M31 — captured 2 May 2026"* while the same run, opened from anywhere else, went out as the full `postCaption` sentence. The identity comes **off the row**, not a per-picture lookup: `GET /api/gallery/best` already calls `identify_object` once per target to fill `object_type`/`blurb` and was dropping the match's `id` and `name`, so those ride along as additive `object_id`/`object_name` — same call, zero extra work, no `/identify` per opened picture (pinned by a test that they are the catalogue's answer, not the folder name echoed back). The scale clause takes the Gallery's route (`…/info` + `…/annotations`, only once a picture is open, only on a FITS-backed run, on the cache keys the other viewers use), so a trimmed preview gets `preview_scale_bar` and never the wider canvas's. An unmatched target, an older backend and a preview-only run all fall back to today's shorter sentence under the wall's own name. Tests +4, all red under a scratch revert. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.453.1** — 🟡 BUG (friendliness / trust — PRIORITY 3), found while shipping v0.453.0 by checking the half of its lead that turned out to be false: **"Copy caption" and "Share picture" sat one item apart in the same menu and described the same picture two different ways.** `SavePictureMenu`'s share items got `postCaption`'s ready-to-post sentence only if the caller passed a `shareCaption` prop, and of its two callers **only History did** — so on the app's most prominent picture, the Target hero, "Copy caption" copied *"Orion Nebula (M42) — a stack of 240 subs (40 min total), shot on 15 Nov 2024 with a Seestar. A vast stellar nursery. The whole frame is about 5.4 full Moons wide."* while "Share picture" two items below handed the OS sheet *"M42 — captured 15 Nov 2024"*. The hero's **lightbox** share was the same short text again. Now **nobody passes the caption in**: the menu builds exactly what its own "Copy caption" builds, off a **non-fetching** `useQuery` on the annotations key (`enabled: false` — no request ever, but it re-renders when "What's in it?", the big view or "Copy caption" puts the measurement in the cache), so a share stays synchronous and a run nobody has asked about simply shares the sentence minus its scale clause. `shareCaption` survives as an explicit override. And the **mapping** — which run column feeds which clause — is now written once as pure `postCaption.postCaptionForRun`, typed structurally so a `StackRun` and a `GalleryItem` both satisfy it; all four surfaces use it, with a test that the two row shapes caption identically. The sheet's title and the file's name still come from `sharePictureText`, where a label and a slug are what is wanted. Tests +7, all red under a scratch revert; three existing date assertions re-pinned against the new sentence rather than loosened (they asserted equality with the short text, which this replaces; the *never the stack day* property they were about is now asserted harder). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.453.0** — 🌟 PRIORITY 3 (enjoy/share), the Gallery-lightbox lead filed the same day, built as its own shape (a): **the same picture now carries the same caption whichever page you opened it from.** The Gallery's full-screen viewer shared `sharePictureText`'s *"M 42 — captured 15 Nov 2024"* where the Target hero and every History card hand the sheet `postCaption`'s ready-to-post sentence — same run, same bytes, two stories, decided only by the page. The lead's gate was the scale clause, and it was half the size it looked: the viewer has fetched the annotations on every open since the North-up toggle shipped (it is how it decides whether turning would move the picture), so the bar was in hand and only the run's *geometry* was missing. That is now one shared `preview_orient.preview_geometry_out`, returned by **both** the run listing and `…/stack-runs/<id>/info`, with a test that they agree on one run in all three states — because two copies of "is this preview a crop?" is how a caption ends up describing a different picture from the one on screen. The lead's named trap is pinned: a cropped run's clause comes off `preview_scale_bar` (3.8 Moons), never the canvas bar (5.4). One request per *opened* picture, FITS-backed runs only; the removed-tint caption now rides the same fetch instead of making a second one, and the identity warms the Target page's own cache key. Every clause still degrades to silence; the sheet's title and the file's name are unchanged. Tests +5, all red under a scratch revert; two assertions in the tint block deliberately rewritten (they pinned "opening a picture fetches nothing", which this retires on purpose). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.452.2** — 🟡 TOOLING + copy, found by running v0.452.1 in a browser: **the dogfood pass can reach the note it just changed, and the mixed note stops saying one thing twice.** `--incoming-lag` seeded only *good* unimported subs, so the damaged-file branch this run shipped was structurally unphotographable — the missing-site (v0.436.1) / click-only-Compare (v0.440.2) / empty-`incoming/` (v0.442.0) hole a fourth time, with one more turn of the screw: the branch needs a file that will not parse **and** a whole-library scan that recorded it, so seeding a bad file alone would not have been enough. It now writes one unreadable sub, scans, then lays down the waiting ones — the **mixed** state a real install is in — and prints the unreadable count so a failed seeding cannot pass for the old state (`DOGFOOD_LAG_SUBS=0` reaches all-damaged, `DOGFOOD_LAG_DAMAGED=0` gives the pre-v0.452.1 shape). The browser then showed what jsdom could not: the new sentence ended with the same *“AstroStack never writes to that folder”* reassurance the note says two lines above it, on a board that keeps two notes inline. Moved into the all-damaged branch, where the generic reassurance stands aside; pinned both ways. Sweep record in [`PROCESS-NOTES.md`](PROCESS-NOTES.md).
- **v0.452.1** — 🟡 BUG (friendliness / trust — PRIORITY 3), found and fixed in the same run as v0.452.0 because that fix is what turns it from a wrong sentence into a contradiction: **the Dashboard stops offering a scan that can never help.** `/api/incoming-lag` compares files on disk with frame rows — the right question, and blind to *why* a row is missing — so a file the app has opened and **cannot read** counts as waiting forever, and the note built on it has been telling the owner his six damaged subs *“haven't been imported yet”* over a **Scan incoming now** button since May. New `webapp/unreadablesubs.py` remembers what the scan found, keyed by the folder spelling `PlannedUnit.folder` and `Project.source_folders_under` already share (one `library_meta` key, the `skipped_folders` pattern) — because deciding readability means *opening* a file and this endpoint may open nothing under `incoming/` (§10). `FolderLag.n_unreadable` + `IncomingLagResponse.n_unreadable` then let `incomingLagUnreadable` move the note by exactly as much as it should: nothing damaged → byte-for-byte unchanged; some damaged → the headline stays and one sentence is added; **all** damaged → it stops calling itself a delay, and the scan button becomes **Open Jobs**, where v0.452.0 names the files. **They are still counted as waiting** — going quiet about an unimported sub is the failure this endpoint exists to prevent — only *explained*. Only a whole-library scan may write the record (a scoped one has seen one folder), and a repaired file leaves it on the next scan; both pinned, the guard by its own scratch revert. Tests +18, five fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.452.0** — 🟡 BUG (friendliness / trust — PRIORITY 3), verified from observer issue [#914](https://github.com/JimmyeJones/astrostack/issues/914): **a raw sub the app cannot read is finally said out loud.** A file whose FITS header won't parse never becomes a frame row, so it leaves no trace at all — no row, no `reject_reason`, no count — and *“not there”* is indistinguishable from *“you never shot it”*. The scanner has always tallied them (`TargetScanResult.n_errors`) and exactly one surface rendered the tally: the **legacy desktop dialog** (`gui/library_dialog.py:119`). `webapp/pipeline.py` never read it, so on the container install this app ships as, an unreadable sub was dropped, re-tried, dropped again and never once mentioned (measured on the owner's library: six subs across five targets, on disk since May, each exactly the median byte size of its own folder with no `SIMPLE` card in it, so no size or zero-byte check can see them). New `TargetScanResult.unreadable_examples` (basenames, capped at 5 — the count stays exact) feeds two optional summary keys, `unreadable` and `unreadable_targets`, set only when non-zero exactly as `skipped_folders` and `video_folders` are; the Jobs page puts the count on the summary line where the desktop dialog always put it and names the targets and files in a self-hiding alert that says what to do. **Reported, never acted on** — nothing under `incoming/` is touched (AGENTS.md §10), asserted by a test. A zero-byte half-copied sub is still a *skip*, not an error — `ingest.py` makes that distinction on purpose and it is now pinned. Tests +10, six red under a scratch revert. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.451.1** — 🟡 PRIORITY 3 (friendliness / trust) on the mosaic frontier, the disclosure half of the twice-reproduced `mosaicEffort` lead: **a mosaic's price tag says it is pricing the whole grid, not what's left.** Read down the framing card on a target that *is* a mosaic, the first two sentences are about what is left (*"adding more panels next session would capture the rest"*, *"about a 3×3 covers all of it"*) and the third silently prices the entire grid from scratch — with the panels already shot inside it, which on the owner's 26 mosaics can quote a job mostly done. `mosaicDepthText` now takes `{ alreadyAMosaic }` and ends *"— the whole grid from scratch, not counting what this picture already has"*, off `StackFraming.canvas`, the same fact `framingTitle` already switches on. It states the assumption and **subtracts nothing**: whether the existing pointings even fall inside the proposed grid is the lead's own real-data gate, still open, still not to be blind-subtracted. A single frame, a caller that cannot tell and an older backend all get today's sentence byte for byte. Verified on the running app (`--mosaic`, `…/framing` → `level: partial, canvas: mosaic`), not only in jsdom. Tests +4, two fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.451.0** — 🌟 PRIORITY 3 (enjoy/share + understand), the one genuinely missing half of the Scout's 2026-09-17 share-caption entry (the rest of it shipped as v0.385.0 — grepped, not assumed): **the caption you paste under your picture now says what the object *is*.** "Copy caption" already carried the identity, sub count, integration, capture window, nights and scale bar; all it could say about the subject was the catalogue's bare type word (*"a galaxy"*), while the "What am I looking at?" card beside the same picture showed the curated sentence the bundled catalogue holds for **157 of 157** objects. `postCaption` now tells it — `ObjectInfo.blurb` through `SavePictureMenu.copyCaption` and History's `shareCaption` — *in place of* the terse appositive, because both together stutter (*", a nebula — … A vast emission nebula …"*). No blurb → the caption is byte-identical to before, existing full-sentence tests untouched; a blurb beside no identity is ignored rather than told; one missing its full stop gets one so it cannot run into the scale sentence. Frontend-only, offline, **no new element on any screen**. Tests +7, five red under a scratch revert. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.450.0** — 🌟 NEW BEGINNER FEATURE (PRIORITY 3, with a PRIORITY 4 motive), slice (b) of the "finished / not stretched / thin" card signal: **the Library wall says which pictures are still too thin to look good.** A card's two numbers are target *totals*, and on a mosaic a total says nothing about what one patch of sky got — thirty subs over a 3×3 raster is three everywhere, and the owner has 26 mosaics — so his own "gibberish" case sat on the wall reading `30/30 frames`. `GET /api/unstretched-pictures` gains `thin`/`thin_count` off the scan it already makes (one endpoint, one wall, one visit), with the depth measured against `derived_light.stacking_field_fulls` so a finished picture's crop cannot read as depth. **No new sentence:** the chip's hint is `thinStackWarning`'s own — the function the Gallery card's orange frame badge already asks — so the two walls cannot disagree about one picture; new `webapp/thinpicture.py` is the *decision* only, a mirror of `THIN_STACK_MAX_FRAMES` (rounding included — JS takes a half up, Python takes it to even) guarded by `tests/test_thin_picture_mirror.py`. **Depth takes the card's one chip slot** when a card is both thin and unstretched: Auto cannot make a one-sub stack anything but a stretched one-sub stack. Tests +20, every substantive one red under a scratch revert (twice: the denominator alone, and the wall's precedence + pointer). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.449.1** — 🟡 PRIORITY 3 (friendliness), filed and built in the same run as v0.449.0 because that fix is what makes the state visible: **the Library wall stops telling someone with a saved edit to press Auto.** The chip's standing hint says *"Open it and press Auto to stretch it into a finished picture"* — and Auto replaces the recipe in the editor, so on a card that is unstretched *because its owner's edit was never exported* that advice discards the work the chip is complaining about (and is wrong about the cause: they did stretch it; the export is what's missing). New additive `UnstretchedItem.unexported_edit`, decided by the same `routers.stack._unexported_edit` History, the Gallery card and the Target hero already read, picks the wording through new `unstretchedHint()`. **One badge, not two** — only the hint changes, because two badges about one picture is the clutter the standing IA priority is about. The three keyed meta reads happen only for a card already failing the finished test, so a healthy library pays for none of them. Tests +4 (two server-side including a wall-vs-Gallery agreement check, two rendered). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.449.0** — 🟡 BUG (friendliness / trust — PRIORITY 3), on three **shipped** surfaces at once, found by probing the premise of the open half of observer issue [#903](https://github.com/JimmyeJones/astrostack/issues/903) on the running app rather than building it: **saving an edit made the "Not stretched yet" chip vanish from a card whose bytes had not changed.** `finishedpicture.run_is_a_finished_picture` counted *"the run carries a saved recipe with an enabled op"* as a finished picture — but `routers.editor.put_recipe` writes the recipe row and **nothing else**; no path re-renders a preview on Save. Measured through the real endpoints: the preview PNG's sha1 is unchanged across the save, and the same run's listing says `unexported_edit: true`, i.e. the app already knew. So the chip withdrew from the one card that is unstretched *and* has the user's work invisible on it, the Gallery's per-run chip (v0.448.2) said the same, and the reprocess warning (v0.447.2) over-counted — all three off the one shared predicate. Now a preview is finished when something **baked** it: an editor export's own tone-mapped pixels, or the `preview_display_space` mark `pipeline._auto_edit_process_run` writes beside the bytes — the identical mark `routers.stack._unexported_edit` reads, so the two stop contradicting each other about one run. The enabled-op test is kept as the other necessary half (a bake through an all-disabled recipe renders the linear stack). Tests +3, all three red under a scratch revert; the suite's `_edit` helper now bakes and a new `_save_only` covers the other state, so no existing test was loosened. The #903 remainder is **closed with the measurement** — a hand-saved recipe was never on the wall, so there is nothing for a reprocess to flatten and nothing to carry. Full entry, and the withdrawn carry-forward, in [`SHIPPED.md`](SHIPPED.md).
- **v0.448.3** — 🟡 BUG (friendliness, PRIORITY 3), **found by a `--mosaic` dogfood pass**: the week planner's Moon caution rendered as one Mantine `Badge`, which truncates — in the "Point at" column at phone width (a 79 px box against a 166 px label) it read **"Moon 92%, up…"**, losing the one word (*all* / *part of*) that decides whether the night is worth going out for, with no hover on a phone and no way to expand an ellipsis. New pure `planweek.weekMoonParts` puts the number on the badge and the qualifier on its own dimmed line beneath, the idiom that column's neighbours already use; `weekMoonNote` is now composed from it (and stays as the hover `title`) so the two cannot drift. Re-measured in the running app: `nothing overflowing`. Tests +4, one existing assertion rewritten with the render — it asserted the caution as *one* text node, which was the truncating shape. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.448.2** — 🌟 NEW BEGINNER FEATURE (PRIORITY 3), slice (a) of the "finished / not stretched / thin" signal, plus (c) answered for this surface: **the Gallery wall badges the runs whose picture is still a flat linear stack, per *run*.** New `GalleryItem.finished` off new `finishedpicture.run_is_a_finished_picture_from` (fed the recipe row `_gallery_item` already reads, so no extra DB read), rendered by `components/UnstretchedBadge.tsx`; the two walls' copy is now one module, `frontend/src/unstretched.ts`. The filed slice's "read the same query" would have been wrong — that endpoint answers per target and the Gallery lists every run — and the hint names the **Edit image** button already on the card rather than adding a second link to it. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.448.1** — 🟠 BUG (trust — PRIORITY 1-adjacent (the displayed picture) / 3, observer issue [#903](https://github.com/JimmyeJones/astrostack/issues/903)): **a reprocess no longer flattens a picture the app itself finished — it *prevents* the regression v0.447.2 announced.** New `pipeline._picture_is_auto_finished` asks, per target and before the restack, whether the run `finishedpicture.displayed_picture_run` picks carries the app's own `editor_auto_baked_look` stamp (and no cover is pinned); where it does, the fresh run gets the same Auto finish, counted apart as `kept_finished` and worded by `reprocessSummary`. This is the open entry's own "cheaper alternative", for the subset where re-deriving Auto is unambiguously right; carrying a **hand-saved** recipe forward was left open there and is now **closed by measurement**, not built — see v0.449.0: a hand-saved recipe was never in the preview's bytes, so a reprocess flattens nothing for that population. No cover semantics touched.
- **v0.448.0** — 🌟 NEW BEGINNER FEATURE (PRIORITY 3): the Library wall badges the pictures that are still flat linear stacks — `GET /api/unstretched-pictures` + `Library.tsx`'s "Not stretched yet" chip, off one shared definition (`webapp/finishedpicture.py`). From observer issue [#903](https://github.com/JimmyeJones/astrostack/issues/903). Full entry, and the three next slices, in [`SHIPPED.md`](SHIPPED.md). (#906)
- **v0.447.3** — 🟡 BUG (trust, PRIORITY 3): the Stack form's "about N subs on each patch of sky" stops quoting the thinnest pointing cluster — new `pixel_depth` on `/stack-estimate` (`routers/stack._pixel_depth` → `field_fulls_of_sky`); `panel_depth` keeps its meaning for method selection. Observer issue [#901](https://github.com/JimmyeJones/astrostack/issues/901). Full entry in [`SHIPPED.md`](SHIPPED.md). (#906)
- **v0.447.2** — 🟠 BUG (trust, PRIORITY 1-adjacent / 3): "Reprocess everything" names what it does to the pictures on the wall — `reprocess_status.finished_pictures` + `reprocessPictureWarning`, so an unedited restack replacing each target's displayed picture is a choice rather than a silent change. Observer issue [#903](https://github.com/JimmyeJones/astrostack/issues/903), option (1) of 3; (2) declined and (3) re-sized, both with reasons in the open entry. (#906)
- **v0.447.1** — 🟡 BUG (friendliness, PRIORITY 3), found by a `--mosaic --editor` dogfood pass whose page sweep was otherwise CLEAN, by reading the Tonight page's prescribing column as one paragraph: **two rows of "Plan my week" were both called "Tonight".** In the small hours the planner legitimately lists the night whose darkness is already under way (yesterday's date, `dark_in_progress`, its minutes clipped to what is left) *and* the evening to come — and `weekNightLabel`'s `ahead <= 0 → "Tonight"` named both of them identically, one row above the other, same target on both, with clock windows that look nearly the same because they are the same hours on different dates (03:21–04:16 against 03:17–04:16). The headline above the table used the word a third time without saying which it meant. The one column whose whole job is *which night*, saying the same word twice, on the page an astrophotographer opens at 3 a.m. New pure `planweek.nightInProgressDate` reads which night the reader is **inside** off the planner's own flag — the same fact `weekDarkPhrase` already turns into "3.6 h left", rather than a clock cutoff this file would have to guess at — and `weekNightLabel`/`weekNightLabelInline` name everything relative to it: the night under way is "Tonight", the evening to come is "Tomorrow", the rest shift with them. Nothing hidden: both rows still render with their own dark phrases. Omitting the new argument gives exactly today's answer, so an older backend that sends no flag is unchanged, and on an evening whose darkness has begun the shift is zero. `PlanWeekCard` computes the date once for the headline, the table and the per-target line so the three cannot disagree. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change. Tests +5, **two fail before** under a scratch revert. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.447.0** — 🟠 BUG (trust, PRIORITY 3/4, on the mosaic frontier), from observer issue [#889](https://github.com/JimmyeJones/astrostack/issues/889) and verified in the code before a line was written: **a mosaic's panel-flatness figure is now read on the scale the estimator that wrote it was using.** v0.313.1 changed what `seam_residual` means (`measure_seam_residual` stopped charging each coverage level's own estimation noise to the seam), no stored row was ever re-measured, and nothing marked which scale a row was on — so `seam_verdict` read both through the same two thresholds. On the owner's library that is 217 pre-fix figures against 65 post-fix, both scales in one History list on 54 targets, and of the 38 pairs with byte-identical inputs **25 change the displayed verdict**, 20 of them off "check" — which on Compare becomes *"B's sky still steps where its panels join"* about two stacks of the same files. The two estimators are **ordered**, not merely different (`se >= 0` on both ends of the max−min over an untouched yardstick), so the fix is a one-sided read rather than a blanket silence: new `stackhealth.stored_seam_verdict` / `seam_scale_is_current` keep an old `"flat"` (a figure below the bar can only move further below it) and refuse an old `"check"`, falling back to the silence the ambiguous middle band already uses. And `coverage_backfill.backfill_seam_residual` **re-measures** a superseded figure instead of returning it, giving the "check" back where the master and coverage map are still on disk, keeping the old figure where they are not. New additive `stack_runs.seam_scale` records which generation wrote the figure (`engine_version` dates the *stack*, and a healed row's two differ), stamped by `run_stack` and the heal in the same statement as the figure — **no `SCHEMA_VERSION` bump**, like `duration_s`, so the upgrade stays rollable. Server-side throughout; no frontend change, no endpoint, config, on-disk, API-shape or default change. Tests +14, **six fail before** under a scratch revert — including one that reproduces the mixed-scale library in a single process (the same pixels read "check" by the old estimator and "flat" by today's) and one that proves the one-sided property on six scenes rather than arguing it from the diff, plus the §9 upgrade test. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.446.4** — 🟡 PRIORITY 1 (editor), found by printing the editor's advisory column as **one paragraph** (the method the last six notes found everything by, newly possible because v0.446.0's big canvas is what makes those captions speak at all): **the two advisories that say the preview shows the effect *not at all* were the only two that never said where you could see it.** Hot-pixel removal ended at *"Your exported full-resolution image still gets the cleanup"* and deconvolution at *"the exported image applies it at full strength"* — reassurance with no answer, an inch above the control that answers it. v0.445.3 declined exactly these two on the grounds that *"neither asks for a judgement"*; **the ops' own parameter lists disagree** — `detail.hot_pixels` carries `Threshold (σ)` 2–10 and `detail.deconvolve` carries `Iterations` 1–50 and `Blur width` 0.5–5 px, so a reader shown nothing has knobs and no way to set them, and the obvious move on deconvolution is to raise the iterations until the preview shows something and save ringing nobody judged — the exact trap `sharpenPreview.ts` was rewritten to close, so deconvolution now carries the same warning in the same words. That call was also made before anyone had rendered this screen. **The promise is verified in the engine, not asserted in a caption test:** `tests/test_edit_proxy_parity.py` plants one stuck pixel and measures it **0.95 → 0.95 at proxy step 3, 0.95 → 0.20 at 1:1**, and measures deconvolution's peak gain at **0.020 on a step-4 proxy against 1.056 at full size** — so "Check it at full size" really does show what these two hide. Six `data-testid="preview-advisory"` markers + `dogfood_editor.advisories()` print the column together on every pass, which is the finder that found this. Frontend copy + one engine test; no endpoint, config, schema, on-disk, API-shape or default change, and no new element on the panel. Tests +6. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.446.3** — 🟡 PRIORITY 1 (editor), measured in a browser on the v0.446.0 canvas — the first thing that could open this modal at all: **the black box around the full-size window grew when a caption *below* it did.** It is a block-level child of the modal's right-hand column with `background: "#000"` and no width of its own, so turning on "Compare with the preview" — which adds `LOUPE_SPLIT_CAPTION`, a full sentence — stretched it from **512 px to 858 px** against a window that stayed 512: about 350 px of flat black painted beside the reader's own pixels, in a modal whose whole job is showing them those pixels, with nothing else on screen that colour. `width: "fit-content"` makes it hug the window; `maxWidth: "100%"` is untouched so a window bigger than the space still shrinks and scrolls (re-measured 512/512 either side of the toggle, and 512 at phone width with no page overflow). jsdom lays nothing out, so its test can only pin the property — the band itself can only ever be caught by something that renders, and `dogfood_editor.mjs` now measures the box against the window on every pass. Frontend + tooling only. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.446.2** — 🔧 INFRA (the finder, not the app), the other half of the same hole: **the full-size check is now clicked, and the field leg stops driving the mosaic.** v0.446.0 made the editor's decimated-preview surface *reachable*; nothing reached the part of it behind a button. `FullSizeCheck` is a modal, and its navigator, marker, `X-Loupe-Window` sentence and split comparison are each another click deep (the split two) — `dogfood_editor.mjs` adds every op the Add menu offers and had pressed none of them, the same blind spot `--editor` exists for and the one `--mosaic`'s Split/Blink modes hit in v0.440.2. New `driveFullSizeCheck()` opens it, waits for the real full-resolution window, prints its three sentences as one paragraph, clicks a **corner** of the navigator (where the window's clamp inside the canvas actually does something) and checks the marker followed, turns the comparison on and drags the divider through its pointer capture, draining console errors and failed requests at each step. Driven on the real app: *"This is the middle of your picture."* became *"This is the top-left of your picture."*, the split drew, nothing errored. It is explicit about **not** reaching it too — *"not offered (preview is 1:1 — run with `--big` to reach it)"* — because a silent skip reads as a clean run (v0.436.1's lesson). One `data-testid` added, on the modal's lead sentence (the line v0.446.1's bug sat in), guarded both ways by `test_dogfood_big_anchors.py` (+4). **And a defect the first `--big` pass exposed in the tooling itself:** `SAFE` was `/api/targets`' first row, which is ordered by activity — so with a second demo stacked it became the mosaic, running both editor drives on one target and putting a mosaic's page heights into the field sample's `$SHOTS`, the directory the §1 baselines are measured against. It now asks `/api/sample` which target the field sample *is*, with the old row as fall-back. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.446.1** — 🟡 PRIORITY 1 (editor) + 3, and the **first finding the v0.446.0 sample produced** — found by reading a screenshot of a surface that had never been drawn: **"The preview is shrunk to about a 2th of full size."** `loupeCaption` wrote the shrink as `a ${Math.round(proxyScale)}th`, a hard-coded ordinal suffix on a computed integer, and `proxy_scale` is `ceil(longest / 1500)` — so **2** is every canvas up to 3000 px and **3** is the owner's own ~3494 px mosaics (*"a 3th of full size"*); the suffix is only right from 4 up. It survived because `loupe.test.ts` pinned exactly one value, `loupeCaption(512, 8)` → `"8th of full size"`, the one number where it happens to be correct — AGENTS.md §8's *fixture that cannot exhibit its own bug*, held in place by a control nothing outside jsdom could reach. Fixed by reusing the vocabulary the app already owns (`recentreCrop.keptFractionWords`), so the editor says *"about half of full size"* / *"about a third"* in the same words the re-centring advisory does rather than inventing a second one. **The same bug, second site, found by grepping for its shape:** `seestack/video/lucky.py` built *"graded every {stride}th frame"* → *"every 2th frame"* on the Moon & Sun page, at the very first stride a long capture reaches (`_sampling_stride(3000, 1500) == 2`); new pure `lucky.ordinal(n)`, teens and hundred-elevens included. Tests +9, **eight fail-before**, including an end-to-end one that grades a real capture and reads the finished sentence off `result.warnings` — the unit test pins the helper, that one pins that the warning is built from it. Copy only; no endpoint, config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.446.0** — 🔧 INFRA (the finder, not the app), the LEAD filed with v0.445.2/v0.445.3 and the **fifth** instance of the same hole — the first to hide a whole *subsystem* rather than one card: **the editor's decimated-preview surface is drawn in a browser for the first time.** `edit/proxy.py` strides only above `PROXY_MAX_PX` (1500); the field sample is 480 px wide and the mosaic's union canvas 907×615, so `get_proxy` hands **both** back at `proxy_scale == 1.0` — and the five preview↔export advisories, `previewScaleCaption`, and the **whole** of `FullSizeCheck` (button, modal, navigator, `X-Loupe-Window` marker, split comparison — ~250 lines of the priority-1 screen) were structurally unreachable by every pass ever run, `--editor` included. New opt-in `load_sample(shape="big")` + `agent-dogfood.sh --big`: the same 2×2 mosaic — same grid, step, uneven depth, hazy panel, ragged corners — at **900×600** panels, so the canvas is **1694×1150** and the preview is decimated by exactly **2**. The lead's "measure before scoping" set that size and closed its own worry: 61.5 s of stack vs the small mosaic's 19.0 s, i.e. about a minute, not twenty. The pass prints what `/editor/loupe-info` answers and says **explicitly** when `proxy_scale` comes back at 1 that the surface is *still* unreached, so a shrunken sample cannot pass for a clean pass (the v0.436.1 `location_source` lesson). The two existing samples are byte-identical, **pinned by digest** rather than argued — their page-height and trim baselines rest on those exact pixels. Tests +11 (5 sample, 6 a new `test_dogfood_big_anchors.py`), the load-bearing one verified fail-before by a scratch revert to 480×320 (`assert 907 > 1500`). Additive: three defaulted response fields, a widened request `Literal`; no endpoint, schema, on-disk or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.445.3** — PRIORITY 1 (editor), the second half of the same read: **one limitation, five captions, two opposite instructions.** `sharpenPreview.ts` closed with *"Raise the radius if you want to judge it here"* while `denoisePreview.ts`, an inch below and about the identical decimated-proxy mechanism, says *"Don't raise the strength to make the preview look clean"* — and the denoise one is right about why (someone who cannot see the effect pushes the slider until the preview looks right and saves a picture processed twice as hard as the one they judged; Auto's own 1.5 px radius raised to 4 px previews beautifully and saves halos). The sharpen wording predates the full-size check and nothing revisited it when a better answer shipped. No advisory on the panel now asks the reader to change the saved picture in order to see it: the three that ask for a judgement (sharpen, star reduction, bilateral denoise) name the control instead, via a single `loupe.ts::FULL_SIZE_CHECK_LABEL` the button also renders, so a caption cannot point at a label that isn't there. Deconvolution and hot-pixels are untouched — neither asks for a judgement. Frontend copy only; tests +3, all three fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.445.2** — PRIORITY 1 (editor), found by reading the editor's advisory column as one paragraph: **the "Check it at full size" control stops vanishing without a word when a rotation takes it away.** The five "this preview isn't the export" advisories are gated on the *proxy* (`sharpen_preview_understates` &co.); the control that answers all five is gated on `_loupe_geometry_problem` — so an enabled `geometry.rotate` over a mosaic-scale canvas leaves the reader told to *judge it at full size* with nothing to judge it with. The sentence naming the op to move was already computed, sent and typed (`LoupeInfoOut.reason`, `client.ts`'s `LoupeInfo`) and rendered **nowhere**: `FullSizeCheck`'s first line was `if (!info.data?.available) return null`. New additive `LoupeInfoOut.fixable` marks only the two *geometry* refusals, so the reason is shown where the button would have been while "the preview already shows every pixel" stays silent — at 1:1 none of the five advisories is speaking either, and a line there would be a new always-on element. Tests +5, three fail-before (verified by stashing the source); the existing "takes no line at all" test was strengthened, not weakened. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.445.1** — 🔧 INFRA (the finder, not the app), filed and built in the same run as v0.445.0 because that fix is the evidence for it: **a dogfood pass now reads the *Tonight* page as one paragraph.** The probe has printed the Target page's prescriptive cards since v0.437.8 and the Dashboard's notice board since v0.444.4; `/tonight` is **the other page that prescribes** — it says where to point — and nothing had ever printed it, though it is the page most exposed to the failure that printing exists for: four *independent, self-hiding* cards in one column (`WishlistTonightCard`, `NearlyThereCard`, `ClosingSeasonCard`, `PlanWeekCard`), each naming a target for tonight, none knowing what the others named. v0.445.0 is exactly that gap and had to be found by reading `routes/Tonight.tsx` and two card sources in an editor. `TONIGHT_PRESCRIPTIVE` now goes through the existing `prescriptiveClaims` extractor, collected on `/tonight` at the desktop width (these cards self-hide on *data*, not on window width), printed under the question it exists to ask: *do these point at the same night and the same target, and if not, does the page say which wins?* **By test id rather than structurally**, unlike `noticeBoardClaims` — Tonight has no `NoticeBoard` whose children *are* the claims, only siblings in a plain `<Stack>` — so it is guarded by the same three-way `*_anchors` shape (`test_dogfood_probe_anchors`, +3, **all three red before**): every id is rendered by real source, the two cards that actually prescribe a target (`closing-season`, `plan-week`) cannot be dropped, and the probe must collect **and print** it. With no observing site all four are empty, so the block **names that reason** instead of printing an approving blank. AGENTS.md §7 gains the paragraph. Scripts, tests and docs only; no app code, no test id added to a shipped component, nothing in the image's file set. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.445.0** — 🟡 PRIORITY 3 (friendliness) + 2 (autonomy), found by reading the **Tonight page** as ONE paragraph — the method the last five runs found everything by, aimed at a surface nobody had aimed it at: **the week plan now acknowledges the season that is closing.** `ClosingSeasonCard` and `PlanWeekCard` sit adjacent on `/tonight` and are both true — the upper says *"M 27 is on its way out of your sky — about 2 weeks left"* and *"a clear night spent on one of these buys something the rest of the year can't"*, the lower answers *"which night should I go out?"* with *"Your best night is Saturday — M 31"*. But `nightplan.plan_week`'s score is **pure observability** (altitude + Moon) and has never heard of a season ending, so on any week where the best-*placed* target is not the one *leaving*, the page hands a beginner two prescriptions and withholds the one fact that would let them choose. Worse, the line that could have named it was the line most likely not to: `otherTargetNights` head-slices `plan.targets` (ordered by **date**, up to `WEEK_MAX_TARGETS = 40`) to **4**, and a closing target's best night is typically latest in the week — it is the one setting earliest — i.e. exactly the row the cap cuts. Now `closingWeekNote` puts one sentence **under the headline it corrects** (not a fifth card on a page the owner calls busy): *"…Its best night this week is Tuesday — and unlike the others here, that one doesn't come round again."*; `otherTargetNights(plan, limit, closing)` keeps a leaving target's row at the **same list length** and in `plan.targets`' own soonest-first order; and `targetNightPhrase` marks it *"(about 2 weeks left)"* with `closingSeason.weeksLeftPhrase` itself, so the two cards cannot word two countdowns. **Deliberately NOT done:** teaching `plan_week` to score a closing season — a blind weighting change on the planner's on-by-default hot path whose honest weight no measurement in this repo settles; the reader gets the fact and keeps the decision. Silent when there is nothing to reconcile (no closing plan / an older backend's 404, nothing leaving that is also placed this week, or the headline already naming it). One request, not two: the identical `["plan-closing", minAlt]` key and options `ClosingSeasonCard` uses, so the pair can never be answered by two snapshots. Frontend-only, additive, self-hiding; no endpoint, response-shape, config, schema, on-disk or default change. Tests +11, **9 red before** under a scratch revert, both rendered ones included. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.444.4** — 🔧 INFRA (the finder, not the app), filed and built in the same run as v0.444.3 because that fix is the evidence for it: **a dogfood pass now reads the *Dashboard's* notice board as one paragraph.** The probe has printed "what the Target page SAYS" since v0.437.8; the Dashboard is the screen the owner opens, carries **twelve** conditional notes on one `NoticeBoard`, and nothing had ever printed it — v0.444.3 had to be found by reading that board's *source* note by note, because every note on it is self-hiding (an ordinary pass photographs an **empty** board, and even `--incoming-lag` only printed what the API answered). `noticeBoardClaims(testId)` walks the board's own children rather than a list of test ids — `NoticeBoard` sorts by priority, renders one wrapper per item and hides the folded ones with `display: none` rather than unmounting, so the wrappers *are* the notes in reading order with the fold readable off the box height. Structural on purpose: a list would rot as notes are added, and would have been wrong on the first run — the verification pass's top note was the ASTAP-readiness alert, an inline `<Alert>` with **no `data-testid` at all**, reported as `(untagged alert)` rather than dropped. Verified by running it against a seeded fault, not reasoned about. A healthy board prints that it is silent, because "CLEAN" on an empty board is a statement about nothing being there — the missing-site / click-only-Compare / empty-`incoming/` lesson a fourth time. Scripts only: no app code, no test id added to a shipped component, nothing in the Docker image's file set. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.444.3** — 🟡 PRIORITY 3 (friendliness) + 2 (autonomy), found by reading the Dashboard's notice board as ONE paragraph rather than note by note: **the incoming-lag note stopped guessing at a cause the note directly above it had measured, and stopped offering a scan that cannot help.** `StuckImportNote` and `IncomingLagNote` were built the same day from one observer report, both rank `warning`, are ranked adjacent, and `NoticeBoard`'s `inlineCount` is **2** — so the event they exist for is exactly the one where they are the two notes a beginner reads. There the upper said *"waiting 11 days behind “Reprocessing all targets”… cancel it on the Jobs page to let the import through"* while the lower said *"this **usually means** an import is still waiting its turn"* and offered **"Scan incoming now"** — a guess under a measurement, and the opposite instruction: `POST /api/scan` does not de-duplicate (`submit_pipeline` → `jm.submit("pipeline", …)`), so on a serial worker that enqueues a *second* import behind the job you were just asked to let through. Plus *"Nothing is lost — your subs are safe…"* printed twice in consecutive notes, on a board where only two fit. `incomingLagCause` + `importIsWaiting` (`importWaiting.ts`, the file that exists so two surfaces cannot make two claims about one queue) now read it off the **same** `["job-queue-health"]` query key the sibling already populates — no second request, no way to disagree — and `importIsWaiting` is deliberately the same predicate `importWaitingNote` speaks on, pinned at every rung. Queued: the wait is quoted, the button becomes **Open Jobs**, the duplicate reassurance is withheld. Nothing queued: the old sentence was *wrong* about the cause, so it now says nothing is queued and the scan is earned. Nothing removed — the reassurance is now said once across the pair instead of twice. Frontend-only; an older backend lands in the scan branch, byte-for-byte today's note. +9 tests, all three rendered ones reverted-and-watched-fail first. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.444.2** — 🟢 PRIORITY 3 (friendliness), the LEAD filed by the run that shipped the v0.443.0 framing rung: **the readiness card now says which canvas its goal is for.** *"goal ~2 h · 1 min of ~2 h — a good start"* sat an inch under *"Shooting it in mosaic mode next session is the biggest win here"* and *"…is about 18 h of shooting"* — nobody told to point two ways, but a beginner asking **how much more do I need?** got ~2 h from the card whose whole job is answering that, about a canvas the same screen had just recommended replacing. The number stays (re-pricing to 18 h would quote a canvas the owner does not have — the mosaic is a separate `<T>_mosaic_sub/` target — and break the card's own "of your `total_exposure_s`" arithmetic); the sentence gains the scope it always assumed: *"1 min of ~2 h **for this single field** — a good start"*. On `plenty` the scope **replaces** the noun, because *"plenty for a clean image of this target"* is the one phrase that claims something about the **object** rather than the picture, and on a fragment that is false. **The lead's "check first" set the gate and was already measured:** `partial` fires on *any* object bigger than its canvas (95 % captured included), which is most of a big-object library — so the clause is gated on the *fragment* bar `FRAMING_MAX_COVERAGE`, shared with the coaching card as one predicate (`framingIsFragment`, split out of `framingRung` rather than copied) so the two cannot come to different opinions about which canvas is right. `readinessCanvasScope` answers null for every other verdict, a non-finite coverage and an older backend, and the Target page is the only caller with a verdict to hand — so the planner rows, `continueTonight` and `libraryProgress` are byte-for-byte unchanged. Frontend-only, one clause inside an existing sentence, no new element and no page taller; no endpoint, response-shape, config, schema, on-disk or default change. Tests +11, the wiring one red before under a scratch revert. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.444.1** — 🔧 INFRA (test reliability), the run's first task because `main` was **red** (AGENTS.md §2): **the suite's lowest job-wait budget sat on its heaviest job.** `test_export_print_is_fitted_to_the_paper_and_carries_its_dpi` failed with `job did not finish in time` — the wait in `_wait_job`, not any assertion — under the suite's own `-n 4`. Measured before touching anything: **6.3 s** alone and **11.1 s** under six busy CPUs on this 4-core box, and nothing in the two commits that landed before it touches `webapp/jobs.py` or the export path. `tests/webapp` carries fourteen hand-rolled `_wait_job` helpers at 60–180 s; `test_editor.py`'s was **30.0**, the lowest of the fourteen, while the jobs it waits on are the heaviest — the editor's *print* export renders onto a whole sheet of paper (A3 at 300 dpi is ~3500×4960 px, from a 3000×2000 master). Raised to the **120.0** the two sibling export modules already use, with the measurement written beside it so it is not tidied back down. **Not a weakened test (§10):** every claim is checked *after* the wait, all 21 call sites are unchanged, and a job that truly never finishes still fails — four times later. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.444.0** — 🟠 PRIORITY 2 (autonomy / data-integrity), the LEAD at the top of "Bugs": the half of observer issue [#883](https://github.com/JimmyeJones/astrostack/issues/883) that v0.441.1 deliberately did NOT build — **a long-haul batch now hands the single worker back to a waiting import, between targets.** v0.441.1 shipped the *sentence*; the wait itself was unchanged, and on the owner's box it was `reprocess_all` holding the worker continuously from 09-04 while an import queued on 09-11 never started and **2,259 subs over two nights were never imported**. Re-ordering the queue could not help (the blocker is a *running* job) and a second worker is the change the memory bound exists to prevent — so `submit_reprocess_all` asks `jobqueue.queued_kind_to_yield_to` at each target boundary and, if an import is queued, stops and re-submits its own remainder (`only_targets` + carried counters) behind it. FIFO does the rest: the import runs next, the remainder after it, **nothing concurrent at any point** — the lead's "must not let two bodies touch the same project DB" satisfied by construction rather than a lock. **A slice never yields before finishing a target**, so a watcher re-enqueuing an import cannot bounce the batch forever and the slice count is bounded by the target count. Only the import (`YIELD_TO_KINDS`) is worth interrupting for — a clicked stack or export is watched and cancellable, and a *running* import is not waiting on anything. Counters and progress are carried, so the Jobs page reads `12/104` rather than restarting, and `reprocessSummary` says *"…so far — paused to let an import through, resuming after it"*: paused is not cancelled. **Residual recorded, not hidden:** a single very long unit of work (one huge restack) still holds the worker — inherent to a serial worker, and not the case the observer measured. Tests +12, three red before under a scratch revert. Additive keys and internal kwargs only; no config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.443.0** — 🌟 PRIORITY 2/3 (autonomy + friendliness), from the LEAD a `--mosaic --editor` dogfood pass filed earlier the same day: **the coaching card and the framing card no longer prescribe different next sessions.** `nextBestMove` claims to name *the single* highest-leverage move and had never heard of framing, so on the bundled samples it read "Add more time — 1 min so far…" over "only about **15 %** of it is in this picture. Shoot it in mosaic mode", and "another pass or two over **the same mosaic**" over "**adding more panels** next session would capture the rest" — opposed instructions about where to point the scope, an inch apart. New `framing` rung between `soft` and `integration`: **above** the time rungs because more time cannot buy what never lands on the sensor (and on a single field that depth is *stranded* — mosaic subs go to a separate `<T>_mosaic_sub/` target, so the hours do not carry over), **below** `soft` because a refocus tightens the wider session too. The crowding-out risk the lead filed itself for is answered by a coverage bar rather than by the verdict: `partial` fires just as readily at 95 % captured, so the rung asks for a third or more of the object to be **missing** (`FRAMING_MAX_COVERAGE = 0.67`) — both photographed cases clear it, the 95 % case the lead warned about is untouched. One measurement, one number: `seestack.framing.rounded_coverage_pct` is public and served as an additive `coverage_pct` beside the sentence it is baked into, and the rung **declines** rather than re-rounding `coverage` on an older backend. Not applied to `clipped` (re-centre and shoot longer are jointly satisfiable). `IntegrationTrendBadge`'s `ADD_TIME_KINDS` → `COACH_DEFER_KINDS` now includes `framing`, which keeps that card's visibility byte-for-byte where it was wherever the new rung took over from an add-time one. Tests +13 (9 `nextBestMove.test.ts`, 1 plateau deference, 1 `Target.test.tsx` wiring, 2 Python). Additive field + optional input; no config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.442.1** — 🔧 INFRA (maintainability in service of not missing bugs), filed and taken in the same run as the feature that proves it: **a dogfood pass can finally put subs in `incoming/` that the library never imported.** The scratch install's drop folder is **empty on every pass ever recorded** — the sample arrives through `POST /api/sample`, which writes straight into the library — so anything that reads that folder is structurally invisible to the tooling, v0.442.0's note first. Same hole as the missing observing site (v0.436.1) and the click-only Split/Blink modes (v0.440.2), a third time. `--incoming-lag` writes a few subs with the app's own `sample_data._write_sample_fits`, dates them eleven days ago (past `incominglag.LAG_MIN_AGE_S`), stretches the watcher's quiet period so they are not imported mid-pass, and prints what `/api/incoming-lag` answers. **A flag, not the default:** an observing site is data a real install *has*; unimported subs are a **fault**, and seeding one by default would put a warning banner in every Dashboard screenshot and every page-height baseline. Measured: phone `/` 2,570 → **2,886 px** with the flag, the note in the shot, otherwise identical and still clean. `-h` also stops truncating its own header. Tests +4 `tests/test_dogfood_lag_anchors.py`, the `*_anchors` guard shape — the script reaches into the app by name, and a renamed writer or route would leave the pass printing CLEAN about a state it no longer reaches. Tooling + AGENTS.md §7 only; nothing in the app or the image changes. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.442.0** — 🌟 NEW BEGINNER FEATURE (PRIORITY 2–3, autonomy + friendliness), the Scout's entry filed the same morning from observer issue [#883](https://github.com/JimmyeJones/astrostack/issues/883): **"N subs are in your incoming folder that aren't in your library yet" — the one signal that catches an import which was never queued at all.** A frame that was never imported has no QC row, no reject reason and nowhere in the record it can be *seen* to be absent, so the library quietly stops growing while every screen looks healthy — the observer measured 2,259 subs sitting in `incoming/` for eleven days. `jobqueue.import_waiting` (v0.441.1) sees only the *queued* shape; a poll that walked a folder during a job that then died, a swallowed scan error or a classification skip leave nothing queued. The entry's cost objection is answered by not paying it: `Watcher.poll_once` already `stat`s every FITS under `incoming/` on every poll, so the listing is a by-product — new `Watcher._record_incoming_units` / `incoming_units()` group what it already holds, and **nothing walks, opens or `stat`s that tree a second time** (§10). New pure `scanner.plan_incoming_units` derives which folder becomes which target by calling `_apply_seestar_convention` itself, so the note can never name a folder the scanner skips on purpose — pinned by a test that runs the plan **and a real `scan_and_organize`** over one tree and compares. `webapp/incominglag.py` under-reports by three rules: convention skips excluded, a folder silent until its newest file has been still for `LAG_MIN_AGE_S` (2 h, the same number as `IMPORT_WAIT_MIN_HOURS` — a night still arriving over SMB is *supposed* to be ahead), and registered frames rolled up by path component so #878's double registration can only ever floor the count at zero. "Nobody has looked" stays distinct from "nothing is waiting" (`checked: false` past `SNAPSHOT_MAX_AGE_S`). `IncomingLagNote` joins the Dashboard's existing `NoticeBoard` at the `warning` rung below `StuckImportNote`, leads with *nothing is lost, your subs are safe exactly where they are*, and offers only the ordinary Scan incoming. `GET /api/incoming-lag` added to `_READONLY_GET_PATHS`, one path as that list requires — and the v0.441.0 mirror test duly went red until the Settings screen named it too. Tests +24 Python / +8 vitest, **nine fail before** under a scratch revert. Additive endpoint, module and note; no config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.441.2** — 🟠 BUG (image quality / trust, PRIORITY 4), from observer issue [#877](https://github.com/JimmyeJones/astrostack/issues/877) and verified red by a scratch revert: **a preview PNG that is a *crop* of its canvas, on a run older than the column that records crops, is no longer placed as if it showed the whole canvas.** `stack_runs.preview_crop_json` is NULL on all 614 of the owner's runs while 42 of the stored previews are baked crops, and NULL is contractually “a plain full-canvas downscale” — so the Sky map’s tile and footprint mask, History’s object pins and scale bar, the rejection overlay, the wallpaper crop and the native-resolution gate all measured against a canvas the picture does not show. New `preview_orient.recovered_preview_crop` is the run-row companion to `parse_preview_crop`, shaped like the sibling `baked_north_up_deg`: a recorded value wins outright, and a NULL column falls through to a check of the stored PNG’s own **shape**. A plain downscale preserves the canvas’s aspect ratio, so one that does not is provably not a downscale — and earns `UNKNOWN`, "decline to place geometry", which every consumer already honours, never a fabricated rectangle. Shape rather than size on purpose (`PREVIEW_ASPECT_TOLERANCE = 0.01`): keying on size would accuse every preview an older build wrote at another width and strip a working overlay from a whole library. A baked North-up turn *swaps* the shape and so looks exactly like a crop to a header, so `baked_north_up_deg` and `north_up_pixel_transform` are consulted before anything is accused. All twelve call sites go through the one resolver; the sky-overlay etag and the footprint fingerprint now key on the resolved crop rather than the NULL. No backfill migration — the verdict is free at read time and reversible, where a migration would write a guess into the owner's database. Tests +9, five red before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.441.1** — 🟢 PRIORITY 2/3 (autonomy + trust), from observer issue [#883](https://github.com/JimmyeJones/astrostack/issues/883) and verified in the code before a line was written: **an import job that has been queued for days now says so, on the Dashboard and on the Jobs page.** `JobManager` is one `queue.Queue` and one worker (deliberately — two stacks at once on a RAM-capped NAS is an OOM kill), so a `reprocess_all` that runs for days holds the queue for days; and the import job is the one **nobody starts by hand**, so while it waits nothing anywhere says so — every target keeps the frame count it had, and a frame that was never imported has no QC row, no reject reason and nowhere in the record it can be *seen* to be absent. On the owner's box that came to **2,259 subs over two nights sitting on disk for eleven days**, with an import queued and never started for the last three. New pure `webapp/jobqueue.py::import_waiting` reports the longest-waiting queued `pipeline` past `IMPORT_WAIT_MIN_HOURS` (2.0) plus the running job holding the worker — only that kind (an editor export waiting its turn is ordinary serialisation), **still reporting when nothing is running at all** (a queue that is not busy and not moving is the worse case), and skipping an unparseable or future-dated stamp rather than manufacturing a stall. New `JobManager.active()` (in-memory only, no DB read) and `GET /api/jobs/queue-health`, declared before `/{job_id}` and pinned there by a test. One wording in `frontend/src/importWaiting.ts` serves both surfaces; days rather than "70.4 h"; the holder's engine kind goes through `jobKindLabel`; every body leads with *nothing is lost, your subs are safe in incoming/*. The Dashboard note joins the existing `NoticeBoard` as `StuckImportNote` beside `MissingFilesNote` rather than becoming a new banner, self-hiding on a healthy queue and silent against an older backend. **The starvation itself is NOT fixed** — filed as a LEAD at the top of "Bugs", and issue #883 stays open. Tests +30 (14 Python, 16 vitest). Additive endpoint, module and note; no config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.441.0** — 🔐 OWNER-REQUESTED GATE (infra / observability in service of the owner's on-NAS observer agent), filed 2026-09-12 and built as its own shape: **a read-only credential, so observing the app no longer means handing over the keys to it.** `webapp/auth.py` had one shared secret and no roles, so letting an agent read `GET /api/logs` meant handing it the credential that also posts to `/api/stack` and deletes targets — and the only alternative was the `docker` group, i.e. root on the host. New `readonly_token_hash`/`readonly_token_salt` (the password's own PBKDF2, rounds and per-mint salt), `auth.check_readonly_auth` (Basic under the reserved username `readonly`, or `Bearer`; **never** True by default, unlike `check_basic_auth`), and `POST`/`DELETE /api/auth/readonly-token` — minted on request, shown **once**, rotation revoking the old one. The gate accepts it for **GET** only and only on `_READONLY_GET_PATHS` (health, logs, stats, jobs, targets); anything else is **403, not 401**, and `_AUTH_OPEN_PATHS` is untouched — this is a narrower credential, not an open door, which was the entry's one explicit "do NOT". It cannot mint or rotate itself. Minting is refused on a password-less install, where it would guard nothing. Off unless minted, so an upgraded install's gate is byte-for-byte what it was; the two fields joined `_AUTH_KEYS`, so they are stripped from the settings GET/PUT and from a settings backup, and an import cannot forge one. UI inside the existing Access-control panel (no new card), leading with what the token *cannot* do, plus a copyable `curl` against this install's own origin. **Verified against a really-running app** as the entry required, not only the TestClient. Tests +14 Python / +13 frontend, including a mirror test pinning what the screen says the token may read against what the gate allows. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.440.3** — 🟠 BUG (correctness / shutdown hygiene), the entry the on-NAS observer account filed at the top of "Bugs (fix these first)" the same night, taken as filed and with its own measurement reproduced here first: **`SeestarManager.stop()` now returns only once both loop threads have actually stopped.** `_poll_loop` waits on the stop event instead of `time.sleep` at both of its naps, and `stop()` joins both threads bounded by a new `_STOP_JOIN_TIMEOUT_S` (a ceiling on shutdown latency, not a guarantee — a loop mid-poll on several silent scopes can outlast any fixed number, so a miss is logged and the daemons are left to exit). `_scan_now` stays a separate event, as the entry's care note asked. Measured with the filed harness: stale `seestar-poll` threads across `test_incoming_readonly_guard.py` go **1 → 2 → 3 → 0**. Tests +4, three red before under a scratch revert. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.440.0** — 🟠 BUG (trust + friendliness, PRIORITY 3, on the PRIORITY 1/4 mosaic frontier), the first of the four "other listings" the v0.438.16 lead named, and verified red by a scratch revert: **Compare's Split and Blink modes dropped the thin-stack cue the Side-by-side mode on the same page shows.** `AbSide` — the A/B provenance strip whose own docstring says those modes are "as trustworthy as Side by side" about which stack is which — printed `{n_frames_used} frames` as bare text, while `CardMeta` has run the identical number through `FrameCountBadge` (and so through the run's `field_fulls`) since v0.437.7. On a mosaic those are different numbers — nine subs over a 3×3 raster is one sub everywhere — so on the one page whose entire question is *"which of these is better?"*, the loudest answer it has disappeared the moment you changed comparison mode. The strip now renders the **same shared component**, so the two modes cannot spell one count two ways; kept on its existing row (badge at natural width, the rest of the provenance truncating beside it) so no row is added to a compact strip, and every clause — integration, date, measured noise — still reads exactly as it did. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change. Tests +3 in `Compare.test.tsx`, **two red before** under a scratch revert (the Split and the Blink cue); the third pins that nothing was removed to make room.
- **v0.440.2** — 🔧 INFRA (maintainability in service of not missing bugs), filed and taken in the same run as the bug that proves it: **a dogfood pass now reaches `/compare`, and clicks its Split and Blink modes.** Compare is the only route whose URL carries *data* — two `<safe>:<run_id>` refs — so it could not be a constant in `dogfood_probe.mjs`'s route table and had simply never been there: the page whose entire job is weighing two pictures against each other had never been in front of a browser, at either width, on any pass ever recorded. The route is built from the running app's own `/api/gallery` rather than from a new env var (the pictures are already on the wire, and on a `--mosaic` pass the pair is the mosaic **and** the single field — the one comparison where a per-pixel figure and a total are different numbers); fewer than two pictures, as under `--empty` or `--no-stack`, skips it rather than probing an error state the page is right to show. And its Split and Blink comparators are behind a `SegmentedControl`, carrying a provenance strip "Side by side" does not have — **a whole element no amount of navigating could reach**, which is exactly where v0.440.0 lived. The route loop's body is split out as `probeCurrentView`, so a view reached by a click is held to the identical overflow / squeeze / clipped-label / console checks as one reached by a URL, and each route's reported height is taken on landing so a click cannot move it. Verified against the running app: six new screenshots, the sweep still clean, the height table unmoved. Tooling only — nothing in the app, the image or the suite changes.
- **v0.440.1** — 🟠 BUG (trust, PRIORITY 3), the second of the same four, and the same axis with a different face — not a stored request contradicting a recorded result, but **one sentence describing a scorer that is not the one running**: **the "My best pictures" wall said it ranked by "total integration time, cleanliness, and frame count".** `seestack.portfolio.rank_portfolio` blends **four** weighted metrics (`PORTFOLIO_WEIGHTS` — exposure, frames, noise **and** coverage), and it runs every higher-is-better one through `per_pixel_total`, dividing by the run's `field_fulls` *precisely* so a mosaic is judged on its depth rather than on the sum of its panels — the substitution v0.437.3–v0.438.14 spent themselves undoing, restated as a **total** on the one sentence that explains why someone's pictures are in the order they are in, an inch above card captions (v0.437.6) that get it right. New `bestPictures.RANKING_METRIC_WORDS` + `rankingHint()` own the wording and build the sentence *from* the metric list, and `tests/test_portfolio_hint_mirror.py` holds that list to `PORTFOLIO_WEIGHTS` itself — the `fullres.ts` arrangement — so a fifth term added by someone with no reason to open a TypeScript file goes red, and the route may no longer spell a description of its own. Frontend + one guard; no behaviour, endpoint, config, schema, on-disk, API-shape or default change. Tests +4 Python / +3 vitest, **all four Python red before** under a scratch revert.
- **v0.439.1** — 🔧 CORRECTNESS-OF-THE-RECORD (maintainability in service of not shipping a fix for a non-bug), found by a wrong diagnosis this run and pinned so it cannot recur: **the comment at the top of `run_stack`'s rejection-resolution block said the opposite of what the code does.** It read *"The original `options` (with the user's choice intact) is what gets persisted in the run record"* — while 800 lines below it `add_stack_run` is handed `options_json=_json.dumps(asdict(eff))`, the **effective** options, whose own comment says so explicitly. Which of the two `options_json` holds is load-bearing for the whole "listings" axis v0.438.15/16 opened: a Gallery / History / Compare combine-method chip renders a run's stored options and says what the picture was made with, and it is honest *only* because those are the ones that ran. Reading the stale comment, this run diagnosed a trust bug — the chip promising "rejecting satellites, planes and cosmic rays" on a run whose drizzle rejection `_afford_drizzle_reject` had silently declined (reproduced: a 6000x9000 union canvas at drizzle x1.5 needs ~10.2 GB against the ~9.6 GB default budget, declined on an unattended run) — and built the fix across `schemas.py`, two routers, `client.ts` and `RejectionBadge` before the **premise test** came back red: the record already says `drizzle_reject: false`. The whole fix was reverted; what ships is the corrected comment plus the two tests that state the invariant in both directions (`tests/test_drizzle_reject.py`, verified red under a scratch revert of `asdict(eff)` → `asdict(options)`). Comments and tests only — no behaviour, config, schema, on-disk, API-shape or default change. Tests +2.
- **v0.439.0** — 🟢 PRIORITY 3 (friendliness / "plan a night"), found by a `--mosaic --editor` dogfood pass that was otherwise CLEAN: **"About a 3×3 mosaic (9 panels) covers all of it" now says what that grid costs.** The panel count answers *how big a mosaic* and stops where the decision starts — whether 9 panels is an evening or a season — and the app already knew: the planner's framing badge has priced exactly this `MosaicPlan` in the owner's clear nights since v0.416.0, because Tonight is handed `usual_pace_s`. The two surfaces where the owner meets the grid *after* shooting, the measured `FramingVerdictNote` (Target / Editor / History) and `ObjectInfoCard`'s catalogue line, are not — so they say the same claim in hours: *"Giving all 9 panels the depth you'd give one field (~4 h each) is about 36 h of shooting."* New pure `mosaicEffort.mosaicDepthHours` is the arithmetic both sentences now share (split out of `mosaicEffortText`, not copied), the clause is deliberately the planner's own so the two read as one answer in two currencies, and the per-field figure goes through `readiness.fmtGoal` and *is* `integrationReadiness`'s `baseGoalHours` on a single field — so a curated "easy" verdict halves both together instead of one page pricing one field two ways. This matters on the shape this owner shoots: "convert this single field into a 3×3" is the decision the framing verdict exists to prompt, against a readiness goal of ~2 h beside it, and un-priced the two prescriptions are not comparable. Silent — today's behaviour byte for byte — with no `MosaicPlan`, a one-panel "mosaic", a non-finite panel count or an older backend, and it steps aside with the framing line under `hideFraming`. Frontend-only, no new card or always-on element. Tests +14, three red under a scratch revert.
- **v0.438.16** — 🟠 BUG (trust, PRIORITY 3, on the mosaic frontier), the second finding on the **listings** axis and one layer under v0.438.15, verified red by a scratch revert: **the Gallery card's "Stacking settings" list said `Off` against two passes every mosaic had run.** `run_stack` turns the final gradient removal and the photometric normalization on from the **canvas** rather than from the options (`options.X or is_mosaic_canvas`, twice) and never writes back, so the card's verbatim dump of `options_json` contradicted the run's own provenance. **Measured on the app's own demo:** the bundled 2×2 sample stores both as `false` while the same run's `/info` answers `photometric = {mode: transparency, n_adjusted: 18, auto: true, n_panels: 4}` — eighteen frames gain-matched under a row reading "Off". `GalleryItem` gains the run's **own** recorded `is_mosaic` flag (free — the row is in hand; `None` on a pre-column run, on an editor export and on an older backend all read as *claim nothing*). New pure `frontend/src/stackSettings.ts::settingOverride` owns the three places the stored value is not the whole truth — the two mosaic-auto passes (**"On — automatic"**) and the weighting min/max discarded (**"On — not used"**, reusing v0.438.15's gate and note). The row keeps its label, turns yellow and gains a `HintAnchor` naming who overrode the switch and why, including that the photometric pass is self-cancelling; nothing removed, no new element, every replacement ≤ 16 characters and pinned by a length-budget test. `tests/test_mosaic_auto_passes_mirror.py` regexes the engine's **own source** for the gates rather than trusting a second copy of the list, so a third automatic pass added by someone with no reason to open a TypeScript file goes red. Tests +16, five red before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.438.15** — 🟠 BUG (trust, PRIORITY 3), the first finding on the one axis the download-copy sweep had never been run against — **the listings**, a card's copy vs the row behind it — and verified red by a scratch revert: **the Gallery card promised a quality weighting the combine beside it had thrown away.** `highlightBadges` reads a run's headline settings straight off its stored `options`, and min/max rejection is an order statistic that ignores per-frame weights entirely — which `run_stack` knows (`weights_applied = not _min_max_reject_runs(eff, n)`, stamping **`WGTSKIP`** instead of `WGTMODE`) and History's run-info panel says in words. The card went on showing a violet **"Quality-weighted"** chip an inch from the **"min-max"** chip that had discarded it. **Reachable on the beginner's first stack:** the walk-away `auto` chain turns `quality_weighted` on for a stack whose rejection it also picks, and `_resolve_auto_reject` resolves to min/max below `kappa_min_frames` (11 at κ=3), so a 3–10-sub "Process target" run carries both chips. The gate is the one the Stack form already asks, not a second copy: `minMaxIgnoresWeighting` split out of `weightingHint.minMaxIgnoresWeightingHint` (which now delegates to it, pinned by a case-for-case test), already mirrored against `stacker.MIN_MAX_MIN_FRAMES` and the dispatcher itself by `tests/test_weighting_hint_mirror.py`. Fed `n_frames_used`, which can only *understate* the dispatcher's candidate `n` — so the claim is withdrawn only where the engine certainly ignored the weights, and κ-σ, drizzle and sub-floor stacks are byte-for-byte unchanged. **Nothing removed:** the chip stays, greys, reads "Weighting unused" (the same 16 characters, pinned by a length-budget test after the v0.438.3 lesson) and gains a `HintAnchor` with the past-tense sentence naming the lever. Frontend-only. Tests +11, two red before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.438.14** — 🟠 BUG (trust + autonomy, PRIORITY 2/3), the second half of the same rule: **the print nudge stops recommending Drizzle to a cropped picture that cannot support it.** `bigger_print` withholds the Drizzle recommendation below `DRIZZLE_MIN_SAMPLES_PER_PIXEL` (100) precisely so one screen stops advising what the Stack form withdraws — and on a finished export the inflated depth walked straight back through that bar: 2500 subs over a 2800×2100 mosaic is ~65 a pixel, and the same picture cropped to 2000×1500 read as ~128. `webapp/routers/editor.py`'s print-sizes endpoint and `webapp/pipeline.py`'s export refusal now both take their depth from `derived_light.stacking_samples_per_pixel`. The paper sizes are untouched — they are about the export's own pixels, which really are what gets printed. Tests +1, red under a scratch revert. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.438.13** — 🟠 BUG (trust, PRIORITY 3, on the PRIORITY 1/4 mosaic frontier), the `LEAD` the previous run filed with v0.438.10, taken with its own first instruction carried out first: **a cropped picture stops claiming a depth its pixels never had.** Every per-pixel figure divides by `field_fulls` (canvas area ÷ one native frame), and an editor export records the canvas it *wrote* while carrying the stack's frame count and integration forward whole — so Auto's border trim, seeded on first open since v0.390.0, inflates two of the four metrics "My best pictures" ranks on. **Measured on the bundled 2×2 sample against its own `_framecov.fits`**, which settled the lead's open question: the border trim is +6.0 % out and a content crop **+217 %**, but one rule serves both — the *source stack's* canvas is within 1.8 % / 12.8 % and errs **low** where the row's own canvas errs high, the direction `field_fulls_of_sky` already clamps for. New `derived_light.stacking_field_fulls` / `stacking_samples_per_pixel`, walking the existing `root_stack` so an edit of an edit is not measured against another crop; `canvas_w`/`canvas_h` stay exactly what they are for every surface that *describes* the file. Read-side only. Tests +8, all red under a scratch revert. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.438.12** — 🟠 BUG (autonomy + trust, PRIORITY 2/3 — the one in this batch that is not merely wrong but *actionable*), Builder-found by carrying the same rule to the third read that takes the newest run for a stack, and verified red by a scratch revert: **cropping a picture in the editor turned off the advice that would have fixed the next night's pointing — or, the other way round, invented advice to move a correctly-pointed scope.** `pipeline._edit_export_wcs_text` deliberately carries a stack's solution through the recipe's crop and resize, so an export's WCS is *correct* for the canvas it describes — and that canvas is one somebody cropped. Every framing verdict is an offset between the object and the **middle of the picture**, and its lever is a capture action ("nudge your Seestar about 1.0° south"), so a crop moves the answer: crop the nebula into the centre and a real mis-pointing goes quiet, crop it towards an edge and a well-pointed scope is told to move. Both readers took the newest run: `framing_advice.newest_picture_nudge`, whose row the **night planner shows while someone is standing outside pointing the scope**, and `GET …/stack-runs/{id}/framing`, whose card a beginner opens on the finished picture. Measured in the regression: the endpoint answered **`centred`** on a stack that is `off_centre`, and the planner's nudge came back **`None`** the moment the picture was finished. New pure `framing_advice.capture_framing_run(run, by_id)` resolves a row to the run that actually *pointed* — itself for a stack, the stack underneath for a re-render (through `derived_light.root_stack`, promoted from private so one chain walk serves both modules), and **`None`** when a re-render's stack has been pruned. Returning `None` rather than falling back to the export is the safe direction and deliberate: the planner's quiet state is a row with no nudge on it, and no advice costs a beginner nothing where advice pointing the wrong way costs them the night. `is_mosaic` now travels off the same row, which fixes a second thing quietly — an export's column is NULL by design, so a mosaic's *finished* picture had been getting the single-frame wording the verdict reserves for one frame. `_run_row_with_siblings` is the endpoint's read, the same single walk `_run_row` already did. Tests +6 in `tests/webapp/test_stack_framing.py`, four red before; the export fixture now carries the placeholder coverage and NULL `is_mosaic` a real export has. No config, schema, on-disk, API-shape or default change.
- **v0.438.11** — 🟠 BUG (autonomy + trust, PRIORITY 2/3 — and the biggest blast radius of the family), Builder-found by carrying v0.438.10's rule one read further and verified red by a scratch revert: **on every target the owner has finished a picture of, the readiness goal was scaled by the canvas of a *cropped* editor export.** `webapp.field_fulls.target_field_fulls` took the target's field-fulls-of-sky off `stack_runs ORDER BY timestamp_utc DESC LIMIT 1` — the **newest** row — and on an edited target that row is the export, whose `canvas_w/h` is what the editor actually wrote (`_apply_editor_to_run`). A crop makes that smaller, and a crop is not an unusual edit but the **default** one: the editor seeds Auto on first open (v0.390.0) and Auto trims the border, ~8 % of the bundled 2×2. So the scale fell by the crop factor, `goal_hours × field_fulls` fell with it, and the three surfaces reading it — the Target page's *"Is it enough yet?"*, the Dashboard's *"Target progress"* bar and the Tonight planner's *"Plenty — try something new"* — all moved toward "plenty". **That is the exact failure this module was written to prevent, arriving from the other side:** its own docstring says reading a mosaic's total against an unscaled goal "tells the beginner they are done at a quarter of the light they need", and a crop past one native frame's area lands on `field_fulls_of_sky`'s `max(1.0, …)` clamp and hands a 3×3 mosaic the single-field goal — measured in the regression, **1.0 where 4.0 is right**. New pure `_newest_stacking_run(rows)` takes the newest row that is **not** a re-render (`run_options.derived_from_run_id`, the same rule as v0.438.10), falling back to the newest row of any kind when a target has nothing else — its source pruned from History — which is what it always did. **Costs nothing:** dropping the `LIMIT 1` is free because `idx_stack_runs_ts` covers the ordering (`EXPLAIN QUERY PLAN`: `SCAN stack_runs USING INDEX idx_stack_runs_ts`, **no sort step**) and the cursor is consumed lazily, stopping at row one on an unedited target and row two on an edited one. Nothing else moves: a target with no export, a single field (`max(1.0, …)` already flattens it), and the per-run `field_fulls` on the History trend — which genuinely wants each run's own canvas — are untouched. Tests +7 against a real `Project`, two red before with the measured values. No config, schema, on-disk, API-shape or default change.
- **v0.438.10** — 🟠 BUG, fourth slice of the same row (trust, PRIORITY 3), Builder-found by reading the "My best pictures" ranker against what `_apply_editor_to_run` actually writes, measured on the shipped scorer before a line was changed and verified red by a scratch revert: **the wall ranked a finished picture down for having been finished.** v0.438.7–v0.438.9 closed the three columns an export left **NULL**; this is the one it leaves *worse than silent*. An export combines nothing, so the writer records a literal `coverage_min = coverage_max = 1` to describe a single-layer raster — and `seestack.portfolio`, which is built so that a metric an entry does not carry *neither helps nor hurts* (`_score` renormalises over whichever are present), had that `1` **present** and read it as "one sub deep at the deepest pixel". Measured on the real scorer: a finished picture that is the best in the collection on every metric it actually carries scored **0.868 instead of 1.000**, and against a deeper rival **0.578 instead of 0.667** — i.e. the picture the owner edited, shares and pinned as a cover, on the one wall whose whole job is to find it. New pure `webapp.derived_light.stacking_coverage_max(run)` answers "this row's peak stacking depth, or 0 where it never stacked", **keyed on the row being a re-render and never on the value** — a genuine one-frame stack records 1 too, and there the number is true — and `gallery._best_pictures` feeds the ranker that instead of the raw column. Read-side only, like the rest of that module: no stored row is touched, and it heals every export already on disk. `seestack/portfolio.py` is unchanged — the bug was its input. Tests +6 (5 on the rule, 1 end-to-end on the wall), the end-to-end one verified red by a scratch revert, plus a drift guard reading `_apply_editor_to_run`'s own source so the rule is re-read if the placeholder ever stops being written; the existing wall fixture's export now carries the placeholder 1 the real writer emits rather than a stack's depth. No config, schema, on-disk, API-shape or default change.
- **v0.438.9** — 🟠 BUG, third slice (trust, PRIORITY 3): **the editor exports already on disk** answer about their light too. A fix at write time cannot reach a picture a live install finished last year, and nobody re-exports three years of edits to heal a column — so new `webapp/derived_light.py` (`with_inherited_light_facts`, `INHERITED_LIGHT_FACTS`) fills a derived row's *missing* facts from the sibling row the listing already holds. The read-side twin of `seestack.coverage_backfill`, and cheaper: nothing read from disk, nothing written. Total and identity-preserving — order kept, an ordinary stack returned as the same object, a recorded value never overwritten, a pruned source left exactly as it was — and it resolves an edit-of-an-edit down to the stack underneath with a cycle guard, because `options_json` is user-adjacent data. Wired at the three listing sites that show a finished picture: the run listing (`stack.py`), the Gallery listing and the "My best pictures" wall (`gallery.py`). Tests +10, red before, including a drift guard that reads `_apply_editor_to_run`'s own source so the write-time and read-time sets cannot diverge, and a wall test asserting the five-hour finished picture now outranks the ten-minute one. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.438.8** — 🟠 BUG, second slice (trust, PRIORITY 3): **the imaging log is one row per *stack*, not per `stack_runs` row.** An editor export is a re-render of a stack the file already describes — same night, same target, same subs — so a user who finished one picture got that night twice, and the duplicate *led*, because the log's within-a-night tie-break is the processing stamp and an edit is stacked later. `_collect_imaging_log` now skips a derived row while its source is still in the project, and keeps it when the source has been pruned from History (where the export is the night's only surviving record). The "is this a re-render, and of what?" test is new `webapp.run_options.derived_from_run_id`, spelled in the module that already owns `options_json` and matching `History.tsx`'s `derivedFromNote` clause for clause so the two cannot drift. Tests +4, red before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.438.7** — 🟠 BUG (trust, PRIORITY 1/3), found by reading the **imaging log** against what it serves and reproduced through the real export job: **an editor export forgot how long its picture had been exposed for.** `_apply_editor_to_run` carried the source run's *capture window* forward — with a comment arguing that an export is "the same light" — and carried nothing else, so every export the app has ever written has `total_exposure_s`, `calstat` and `transparency_ratio` NULL. The finished picture, the one the owner shares and pins as a cover, was the one row in the library that could not say how long it was exposed or what calibrated it: History and Gallery cards served `null`, and **"My best pictures"** (whose representative is the newest run with a preview, i.e. the export) ranked it over two of the four metrics `seestack.portfolio._score` blends. The three now carry. The other half of the change is the list of what it deliberately still does not: the pixel measurements (`noise_sigma`, `stack_fwhm_px`, `seam_residual`, `grain_ratio`), which an edit moves — and **`is_mosaic`**, which is read *behaviourally* by `editor._run_is_mosaic` and would make re-opening an edit trim a border off a picture Auto has already trimmed. Tests +4, red before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.438.6** — 🟡 BUG (trust + friendliness, PRIORITY 3), found in the same pass as v0.438.5 by reading the editor export panel's controls against what each one calls, and verified red by reverting the copy: **the "Add caption bar" checkbox said it bakes the nameplate onto "the shared picture", and has always also been passed to the *print* export.** One `nameplate` state in `Editor.tsx` drives three destinations — `exportShare` for the share JPEG, `exportShare` again for "Share to app", and **`exportPrint`** — and `submit_editor_print` bakes the same footer at the paper's own resolution on purpose. A share image is a post; a print is a physical object someone paid a lab for, and there is no undo on an unwanted caption bar across the bottom of it. The checkbox also sits directly under **Download full-res PNG**, which never gets a nameplate at all. The description now names both halves of its scope (*"onto the share image and the print file … The full-res PNG above never gets one"*). Frontend copy only — no behaviour, endpoint, config, schema, on-disk, API-shape or default change. Tests +1, red before, and not a string assertion: it clicks **Download print file** unticked and ticked and pins `exportPrint`'s `nameplate` argument both ways, so decoupling the toggle from the print would make the sentence false and the test red in one move. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.438.5** — 🟠 BUG (trust + friendliness, PRIORITY 3), the download-copy sweep on one of the four surfaces it lists as **untouched on any axis** — the print export — and verified red by a scratch revert: **the print refusal told a beginner that "another night or two of subs will get it there", which is the one lever that cannot work.** `webapp.pipeline.submit_editor_print` hand-wrote its own refusal instead of using `seestack.printexport.print_advice`, whose docstring, every branch of `bigger_print`'s copy and two tests all say the opposite — a print needs *pixels*, and another night of the same pointing adds none. The engine's copy was corrected long ago; this one never was. And the branch is the **designed landing place for a crop**: `print-sizes` is costed off the stored canvas and says so, so the ordinary way to reach the refusal is to crop in the editor and press the button the panel is still offering — a picture whose pixels were never the problem. New pure `print_refusal()` opens with `print_advice([])` verbatim so the offer and the refusal cannot drift again, then names the reachable lever: the **crop or resize** by name when the stack's own canvas would have printed (*"What you're exporting is 480×320 px — … cut it down from this stack's 1200×800. Take that out and it prints at up to 7×5 in."*, and deliberately no mention of Drizzle, because the pixels already exist), otherwise `bigger_print`'s existing nudge including its depth-aware half (the job hands it `field_fulls.samples_per_pixel_of_run`, as the endpoint already does), otherwise the opening sentence alone. Tests +6, one red before — the regression is on the **pipeline**, rendering a real crop recipe through a real run, with a `_promises_more_exposure` guard that looks for the claim rather than one wording. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.438.4** — 🟠 BUG (trust, PRIORITY 3–4, the v0.422.1 rejection-floor family one surface further out), Builder-found by reading `RejectionBadge`'s tooltips against `lone_outlier_min_depth` and verified red by a scratch revert: **the violet combine-method chip on History, Gallery and Compare promised outlier protection with no mention of the per-pixel depth every pass needs before it removes anything.** v0.422.1 established that floor and fixed the surfaces that make a *verdict* about one run (`rejection_reach` on the Stack form, `stackhealth`'s `rejection_blind` note, the `REJNEED`/`REJREACH` header cards). **This chip is deliberately not one of those:** it renders in a *list* from stored `options` alone, the run's real verdict (`rejection.reaches`) is read off the master FITS header in the per-run panel, and estimating depth from `n_frames_used / field_fulls` would use a canvas **mean** where `REJREACH` uses the **peak** pixel — so the chip could have contradicted the info panel one click away on the same card. It now states the method's **rule** instead, true of every run and unable to conflict with any verdict: min/max keeps its guarantee verbatim and gains *"needs 3 subs on a pixel to have that many to spare"* (scaling as **2k+1** for a top/bottom-k trim, the Stack form's own number), and κ-σ and drizzle-with-rejection share one sentence because they share one bound — *"a lone trail … only stands out far enough to be clipped once about 11 subs overlap on one pixel — on a mosaic that's the subs on one panel, not the total"*. It names the **run's own κ**: new `frontend/src/kappaMinFrames.ts` mirrors `stacker.kappa_min_frames`, which the frontend had been quoting in prose comments in four files without ever being able to compute (κ=1.5 needs 4, not 11), falling back to the app default on an unreadable κ exactly as `stackhealth._run_sigma_kappa` does. Drizzle with its clip **off** is untouched. Why the owner: he drizzles mosaics — `stackhealth` calls that "exactly the owner's case" — and Gallery/Compare are where he picks between pictures. Frontend-only, tooltip text plus one pure helper; every label byte-for-byte unchanged, so the Gallery combine-method filter facet and every label assertion pass untouched. Tests +9, eight red before, with `tests/test_kappa_min_frames_mirror.py` pinning the mirror through a shared case table in the `test_reject_pct_mirror.py` idiom. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.438.3** — 🟠 BUG (trust + friendliness, PRIORITY 3, the whole-canvas/measured-picture family on the *cards* this time), Builder-found by `scripts/agent-dogfood.sh --mosaic --editor` and verified red by a scratch revert: **the panel chip said `PANELS EVEN`, in green, on the run whose health panel calls a quarter of the same picture "about 1.4× grainier".** v0.406.1 knew about this exact collision — `seamsLabel` has taken a `grain` argument since then and its docstring names the untruth — but what it changed was the **help**, and the word *on* the chip stayed `Panels even`. `HintAnchor` does make that sentence tappable on a phone, so it is reachable; the cheaper failure beside it is that a chip is **read** far more often than it is asked. On the Target page the other half is said three more ways, so the chip is at worst redundant there — but on **Gallery** and **Compare**, the two surfaces where a beginner picks between two pictures ("Set as cover", the side-by-side), this chip is the only thing on the row that knows anything about the panels, and nothing else there mentions depth. The fix is the chip's own label, not a second chip: `flat` + `grain === "uneven"` now reads **"Sky even"** — the measurement that was actually taken, dropping the word *panels*, which a reader takes to cover everything a panel can differ in. **Shorter than the label it replaces, and that is a requirement:** both badge rows are `<Group wrap="nowrap">`, so a first attempt saying both halves outright turned History's row into `MIN-… | SKY EVEN, ONE PART TH… | 21 FRA…` — caught in a browser, not in jsdom, and now pinned by a length budget test. The depth half stays in the tappable help where v0.406.1 put it. Verdict, teal colour and help are untouched, and no element joins the badge row (AGENTS.md §1's "prefer a consolidation over a new card"). `check` + uneven, a `None` verdict, and Compare's comparative sentence are left alone with reasons recorded. Every single field, every evenly covered mosaic, every pre-measurement run and any older backend is byte-for-byte the chip it always had. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change, no threshold moved and no measurement changed. Tests +6, three red before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.438.2** — 🟠 BUG (trust + friendliness, PRIORITY 3, the same measured-picture family as v0.437.3–v0.438.1), Builder-found by reading `grainProjection` against its own `MAX_HONEST_EXTRA_HOURS` fence, reproduced in node before a line was written and verified red by a scratch revert: **the grain projection asked a beginner for the light their picture already has.** A stack measuring σ **0.0202** against a clean bar of **0.0200** printed *"there's a little grain left at 1.0 h (grain 0.020). About **1× the light in total — roughly 1 min more** — would bring it down to a clean-looking result."* Both figures are artefacts: the multiple is quoted at one decimal, and `(0.0202/0.02)² = 1.0206` **rounds to 1.0×** — the light already there — after which `extra = hours × (factor − 1)` is exactly **0** and `fmtHours(0)` returns its own `Math.max(1, …)` floor, printed as a plan. The grain it quotes, `toFixed(3)`, prints as **"0.020"**, i.e. the clean bar to the digit. **Reachable exactly where the owner's pictures land:** `factor <= 1` needs σ < 0.0205, and this module's own provenance note says his real deep stacks (271–787 frames) measured **0.015–0.020** — so it fires on the good ones, immediately above the bar those stacks set. **The fix is the fence the module already has, applied at the other end:** `MAX_HONEST_EXTRA_HOURS` exists because a projection is only worth printing while it is a plan someone could act on, and a projection whose multiple rounds to the light already there has nothing left to ask for — so it reads as the **clean** verdict, whose existing copy states that honestly ("more time from here mostly buys fainter detail"). One condition in the module's already-published precision (`sigma <= CLEAN_SIGMA || factor <= 1.0`), no new constant; `moreLightFactor`/`extraHours` come back `null` through the existing `quotable` gate, the same contract `beyondReach` uses at the top of the range. **The *level* moves and not just the copy because `nextBestMove` reads it** (`grainLevel`, v0.438.1): left at `"some"` this same target would have been told *"even the rest of one clear night would clean up the background nicely"* an inch above a card that had just declined to ask for any light — v0.438.1's exact pair, arriving through a rounding edge instead of a widened branch. Nothing else moves: `factor <= 1` is unreachable from the middling and grainy bands, σ ≤ `CLEAN_SIGMA` was already clean, no bar is touched, no processing reads any of them, and the first σ that asks for real light (0.0205 → 1.1×, 6 min) still asks in full. The reroute lands in the branch carrying the v0.437.3 mosaic scoping, so a hair-over-the-bar raster still says "across most of it" — pinned by its own test. Frontend-only. Tests +3, all three verified red by a scratch revert. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.438.1** — 🟠 BUG (trust + friendliness, PRIORITY 3, the same whole-canvas/measured-picture family as v0.437.3–v0.437.5), **found by the v0.437.8 dogfood probe's prescriptive-claims block on its very first run** — on the field sample *and* the mosaic, with **both cards inline**: **the coaching card promised *"even the rest of one clear night on this target would clean up the background nicely"* one inch above the readiness card's measured *"the background already looks clean at 1 min (grain 0.001) — more time from here mostly buys fainter detail rather than a visibly cleaner picture"*.** One reasons from integration time alone, the other has measured the picture. `grainProjection`'s own docstring already says its clean verdict "deliberately says more time now buys **faint detail** rather than a visibly cleaner background… it agrees with the 'keep going to pull out fainter detail' sitting directly above it" — but that reconciliation was written against the *galaxy/nebula* branch, and v0.429.2 (clusters) then v0.435.5 (every curated-easy target) widened the **easy/cluster** branch over the same rung afterwards without asking. `NextBestMoveInput` gains one optional `grainLevel`, taken from `cardGrainProjection(runs)?.level` — the level the card below actually prints, so the two cannot form different opinions about one picture — read **only** by the `integration` rung's easy/cluster branch, and changing the *reason* while leaving the lever: under a quarter of the goal more time is still the advice, and a test drives the whole ladder across every level asserting the rung that fires is identical with and without the measurement. An unevenly deep mosaic gets the family's usual scope, keeping both claims in the order they pay off ("across most of it the background already looks clean — so another pass or two evens out the thinner part, and elsewhere pulls out fainter detail"). `some`/`grainy`/no measurement/older backend and the whole galaxy/nebula branch are byte-for-byte what v0.435.5 shipped. Frontend-only, copy only; no endpoint, config, schema, on-disk, API-shape or default change. Tests +4, three verified red by a scratch revert. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.438.0** — ✨ NEW BEGINNER FEATURE (enjoy + understand, PRIORITY 3), the idea the Scout filed the same morning, built at the size and shape it was filed at: **"How far you've come" — the first picture you ever got of this object, beside the one you have now.** `/compare` has been a full bookmarkable A/B route since ~v0.150 (split divider, per-side provenance, plain-language noise/panel/nights verdicts) and v0.360.0 put a one-click entry point on the Target page — but it auto-picks *"my last one"*, the immediately previous run. That answers *"did another two nights help?"*, an increment, and increments are exactly what a beginner cannot see themselves improving at; the pairing that shows improvement is **first-ever vs latest**, and it is invisible from every screen because the first picture is at the bottom of History. New pure `pickFirstVsNow(runs)` implemented *through* `pickCompareWithLast`, so the two honesty filters (both sides have a picture; both are genuine stacks, not editor exports) are stated once rather than mirrored. Which run is "first" comes from the list's order (`ORDER BY timestamp_utc DESC`), the same choice the sibling makes — a re-stack of a back catalogue is a new run carrying old capture nights — while the **labels** still come from `pictureDateLabel`, i.e. when the subs were shot, per the 2026-08-30 date sweep's rule. **A link in the existing card, not a new card** (AGENTS.md §1's "prefer a consolidation over a new card"): it joins `CompareWithLastCard` in the Story group, and appears only when it is a genuinely different pair — with exactly two pictures the first one *is* the previous one, and the stand-down counts *comparable* runs rather than rows. Both links put "now" on the same side of the divider. Frontend-only, additive over fields the page already fetches; no endpoint, config, schema, on-disk, API-shape or default change, and no request added. Tests +9, three verified red by a scratch revert. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.437.8** — 🔧 INFRA (maintainability in service of not missing bugs), the `LEAD` the 2026-09-13 `…-q84vzj` run filed and sized at S, built where that lead's own last sentence points: **a dogfood pass now prints the Target page's prescriptive sentences as one block, so the contradictions that produced four of the last five findings land in the log instead of in a screenshot nobody crops.** `agent-dogfood.sh`'s "what the app SAYS about this mosaic" block is the **server-side** half (the panel map and the health notes, straight off the API); the cards that keep disagreeing with them — the readiness goal, `grainProjection`, `nextBestMove`, `integrationTrend` — are computed in the frontend, so no Python could ever print them. `PRESCRIPTIVE` in `scripts/dogfood_probe.mjs` reads them off the rendered DOM by `data-testid` (five cards gained one; none changed behaviour) and prints them together under *"what the Target page SAYS"*. **One thing the lead had not foreseen:** `NoticeBoard` keeps every note **mounted and hidden with CSS**, showing two inline and folding the rest behind "N more notes" — so each claim is tagged `inline` or `FOLDED`, which answers the 2026-09-13 note's own *"check what the page says when the other cards are quiet"* from the log rather than by eye. `tests/test_dogfood_probe_anchors.py` is the drift guard, in both directions: a renamed testid would otherwise leave the probe reporting CLEAN and silently printing a shorter paragraph, and the three browser-only cards can't be quietly dropped back to the half already covered. Tooling and one `data-testid` attribute per card; no endpoint, config, schema, on-disk, API-shape or default change, and nothing a user sees moves. Tests +2, one verified red by a scratch rename.
- **v0.437.7** — 🟠 BUG (trust + friendliness, PRIORITY 3, same mosaic frontier as v0.437.6 and found by the same trace): **the thin-stack cue was on the Gallery grid and on neither page where a beginner actually chooses between stacks.** A mosaic's frame count is not a depth — nine subs over a 3×3 is one sub everywhere, the per-pixel speckle `thinStackWarning` was corrected for on 2026-09-11 — but History's run card and Compare's side-by-side card each drew a plain `<Badge>{n} frames</Badge>`. History's badge row is otherwise **badge-for-badge the Gallery card's**, so the two pages answered "is this picture thin?" differently about one run, on the page where **"Set as cover"** lives; Compare's whole job is "which of these is better?". Both already receive the figure (`StackRun.field_fulls` for the integration trend, `GalleryItem.field_fulls` for the Gallery badge), so this is the shared `FrameCountBadge` dropped in at both sites — the message stays `thinStackWarning`'s, and three pages cannot phrase one picture three ways. It also closes the plainer gap the count-only badge left: a **one-frame single field** read *"1 frames"* with nothing beside it. Nothing removed and nothing hidden — a healthy run renders the identical `variant="light"` badge with the identical text, and the thin case keeps the count with the cue riding it. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change and no new copy. Tests +5 vitest, three red before on a scratch revert; honest about jsdom doing no layout, so they pin the cue rather than the row's width. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.437.6** — 🟠 BUG (trust + friendliness, PRIORITY 3, in the PRIORITY 1/4 mosaic frontier), Builder-found by running `samplesPerPixel.ts`'s own list of already-corrected surfaces over the tree (`auto_reject`, `rejection_reach`, `auto_stack_min_frames`, `perPixel.ts`, the Stack form — and **not** the one surface that ranks pictures against each other), and verified red by scratch reverts on all three layers: **the "My best pictures" wall scored and captioned a mosaic as if every sub had landed on every pixel.** Three of `rank_portfolio`'s four axes — integration 0.40, frames 0.25, peak coverage 0.10, i.e. **0.75 of the weight** — are facts about the *target*, while the fourth, σ, is measured on the finished pixels; so a thinly-shot raster was credited for depth on three axes and penalised for the same thinness on the fourth, and the "why it's one of your best" line repeated the totals (*"3.4 h · 500 frames"*, which on a 3×3 is ~23 min and ~55 subs anywhere you look). **The disagreement was one card away:** `GalleryItem`, in the same router file, has carried `field_fulls` since 2026-09-11 so its frame badge can turn orange on exactly that picture. **Measured on the bundled 2×2 sample** (4 panels at 6/6/6/3): the wall read 210 s / 21 frames / peak coverage **21** — every sub the target has, at the one corner where four panels overlap — against 58 s and 5.8 subs a pixel (`field_fulls` 3.63; the measured `coverage_median_depth` is 6.0, corroborating the scale to 4 %). Left alone that peak also *became* `max_coverage`, the yardstick every other entry is normalised against, at a depth no picture is at. `PortfolioEntry` gains one optional `field_fulls`; the two totals go through a new pure `portfolio.per_pixel_total` (the Python twin of `perPixel.perPixel`, same clamp), and `coverage_max` — already a per-pixel count, so not divided — is **capped** at what a typical pixel got, which on a single field is the identity. Yardsticks and both tie-breaks read the same corrected figures, so the sort can't undo the score. The caption keeps both totals and adds *"· about 51 min on each patch of sky"*. Byte-for-byte on a single field, an unreadable frame shape and an older backend. One additive response field, one LIMIT-1 frame-shape read the Gallery listing already pays for; no config, schema, on-disk, API-shape or default change. Tests +10, eight red before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.437.5** — 🟠 BUG (autonomy + image quality, PRIORITY 2/4, in the PRIORITY 1/4 mosaic frontier), Builder-found by tracing the v0.437.3 family forward through every *other* Target-page surface that answers "should I keep shooting this?", and verified red by scratch reverts on both halves: **on a mosaic that has gone sky-limited on its deep panels, the plateau card said *"this target looks sky-limited from here, so more subs won't help it much"* and then named a different target to point at, while the health note on the same page said *"grain only comes down with more light — so another night on that panel is what evens it out"*.** v0.437.3's pair disagreed about what more light *buys*; this one disagrees about whether to shoot at all, and acts on its answer — for a heavy mosaic user that is the app steering him off a raster with an under-shot panel in it. **And it is the one place nothing counterbalances it:** `cardGrainProjection` deliberately goes silent on a plateau (it assumes the ideal σ ∝ 1/√t curve, which a plateau is exactly where it fails) and `nextBestMove` is silent once the mean depth clears its deep bar, which a plateau needs. **Same mechanism, third currency:** `integrationTrend` fits its exponent from `noise_sigma`, one estimate over the **whole** canvas (`stacker._compute_noise_sigma`), so on unevenly deep panels the fit describes the part that got the most subs — the *time* axis was made per-pixel when `perPixelSeconds` landed, the σ axis had never been asked about. `RunLike` gains one optional `grain_verdict`, carried **per point** so the plateau branch reads it off the *deepest* run (the one the sentence is about), exactly as `grainProjection` reads it off the run it took σ from. Only that branch consults it; `improving`/`slowing` already prescribe more time and are pinned byte-for-byte, and `hoursNow`/`exponent`/`percentCutIfDoubled` are pinned equal to an even mosaic of identical depth. The sentence now gives both levers **in the order they pay off** ("another pass over it is the thing left worth shooting here. After that, a darker sky or a brighter target…"), and a new `unevenDepth` carries the scope out to the heading ("Most of this is as clean as your sky allows") and the footnote ("**After that,** try M27 …"). **Nothing removed:** the planner's pick, its observability line and the `/tonight` link all stay. Frontend-only, copy only; no endpoint, config, schema, on-disk, API-shape or default change, no threshold moved, no measured number changed — `grain_verdict` was already on every `StackRun` row both pages fetch. Tests +6, three red before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.437.4** — 🟠 BUG (friendliness + trust, PRIORITY 3, same mosaic frontier), same forward trace, verified red by a scratch revert: **the "💡 Nice work" coaching card said *"This is a solid result — plenty of subs went in"* above the health note's *"about 23 % of the picture has 3 subs where most of it has 6 … grain only comes down with more light"*.** Every figure that rung reaches on is a **mean over the whole raster** (`perPixel.ts` says so, and says why the mean is the right choice for surfaces that *report* depth), so a mosaic comfortably deep on average can hold a panel that is not — on the card whose whole job is naming the single highest-leverage next thing. Reachable on the owner's data, not on either sample: it needs the mean per-pixel integration between the short and deep bars with one panel measurably thinner, an ordinary mid-project state. `NextBestMoveInput` gains one optional `grain_verdict`, read **only** by that last rung, which keeps the praise and scopes it ("Across most of it this is a solid result… One part of this mosaic is thinner than the rest, though, and only more light evens that part out, so more passes over the same mosaic are what'll add depth from here") — a prescription that serves **both** endings the health note can print. **Deliberately not a new rung** (the ladder promises one lever, and `thin`/`locate` still win — pinned) and **deliberately still silent on a genuinely deep uneven mosaic**, where repeating the health note would be the duplication the thin-stack suppression exists to avoid. `kind` stays `"good"`, so `IntegrationTrendBadge`'s `ADD_TIME_KINDS` deference is untouched. Tests +7, two red before — one of them a **fixture guard** asserting the ladder really does land on `good` for that mosaic shape, so the behavioural two cannot pass for the wrong reason (AGENTS.md §8). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.437.3** — 🟠 BUG (trust + friendliness, PRIORITY 3, in the PRIORITY 1/4 mosaic frontier), Builder-found by reading the `--mosaic` dogfood pass's screenshots side by side and verified red by a scratch revert: **the "Is it enough yet?" card said *"more time from here mostly buys fainter detail rather than a visibly cleaner picture"* on the same page as *"about 23 % of the picture has 3 subs where most of it has 6, so that part looks about 1.4× grainier — processing can't fix that, grain only comes down with more light"*.** Both true of the region each measured; a beginner cannot hold them at once. The mechanism is v0.436.0's in another currency: `noise_sigma` is **one estimate over the whole finished canvas** (`stacker._compute_noise_sigma` on `result_image`), so on a mosaic with unevenly deep panels it is dominated by the part that got the most subs — a whole-canvas number making a claim about every part of the picture, the exact shape AGENTS.md §1 names as the open frontier. **Nothing new is computed or served:** `grain_verdict` (`stackhealth.grain_verdict`, what the `PanelSeamsBadge` already reads) is on every `StackRun` row the Target page already fetches, and `grainProjection` now reads it **off the run it took σ from** — deepest, not newest — so the two halves of one sentence cannot describe two pictures. **Only the clean branch's scope moves:** the verdict stays `"clean"` (the number is honest for most of the canvas; demoting it would be a second opinion where a scope was missing), every fact it carried survives, and it now closes with the health note's own prescription instead of its opposite. `some`/`grainy` untouched and pinned as such — they already prescribed more light. A single field, an evenly covered mosaic, an older backend and an unknown verdict string all keep the plain sentence byte-for-byte. Frontend-only, copy only; no endpoint, config, schema, on-disk, API-shape or default change, no threshold moved and no number changed. Tests +6 (5 `grainProjection.test.ts`, 1 `Target.test.tsx` pinning the *wiring*), three red before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.437.2** — 🟠 FRIENDLINESS (PRIORITY 3), the `LEAD` the previous run filed and sized at S, taken as filed: **the Tonight planner's "Add more to what you're shooting" table lost its last column to a target's own `safe_name`.** At 420 px the Target column read `Sample_Orion_Nebula_M42 — Sample: Orion Nebula (M42)` over three lines and pushed "Time up" out of the scroll container (header "T" over "u", values one character per line); the catalog table beside it read `M32`. Both are the same `TargetRow`, whose label printed `id — name` whenever the two differ — two genuinely different facts on a **catalog** row (`M31 — Andromeda Galaxy`), but on a **library** row `nightplan` sets `id=t.safe`, so it printed the display name and then the same name with its punctuation slugified by `make_safe_name`. New pure `tonight.targetRowLabel` changes the **already-targeted branch only**: the friendly name alone — what the Library tile and the Target page hero already print for that object, so the app names one target one way — with the catalog branch and every no-distinct-name fallback byte-for-byte as before. **Nothing is removed:** the safe name stays what it already was here, the row's link destination, and it is shown nowhere else in the app either. Checked rather than assumed: `rename_target` leaves `safe_name` alone on purpose, so the two really can diverge (`NGC_6888_SUB` vs `NGC 6888`) — and there the display name is the half a reader recognises. Frontend-only, copy only; no endpoint, config, schema, on-disk, API-shape or default change. Tests +4 vitest (one red before), and the route assertion that pinned the old label is updated *and* strengthened rather than dropped. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.437.1** — 🟡 BUG (friendliness + trust, PRIORITY 3), Builder-found by dogfooding the running app in a browser and verified red by scratch reverts on both sides: **the Tonight page said one night was 8.3 h and 5.9 h long at the same time.** The Dark-window card quotes the whole night (`plan_tonight` → `_find_dark_window`, unclipped); "Plan my week"'s first row quotes what is **left** of it, because `upcoming_dark_windows` deliberately clips a night already under way to "now" so the planner never offers darkness that has gone — and both printed it as *"N dark"*, in one column whose other rows are whole nights. The clip stays; the *word* was the bug. `DarkWindow.in_progress` (default False, set only by that clip) travels as `WeekNight.dark_in_progress`, and the new pure `planweek.weekDarkPhrase` says *"5.9 h left"* — the Dashboard's own wording for this number (`dark_minutes_left` → "About 2 h of dark sky left tonight"), so the app keeps one vocabulary. Scope checked rather than assumed: `next_observing_windows` prints clipped *times*, which are honest as they are; `best_months` never clips; `PlanWeekCard` is the only reader of the week's `dark_minutes`. One additive, defaulted response field; no config, schema, on-disk, default or API-shape change, and no number moves. Tests +5 (2 Python, 3 vitest), the two behavioural ones red before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.437.0** — 🎨 THE STANDING IA PRIORITY (owner 2026-08-08, "there are like 30 different things at the top of some of the pages and I have to scroll a fair bit"), **one slice, and the first one two consecutive measurements have actually asked for**: **the Tonight page was 10,430 px tall on a phone — 3.4× the next page in the app and 3.5× the 3,014 px "worst page" figure that banner quotes — because "Start something new tonight" drew every well-placed catalog object eagerly.** About twelve screens of scrolling, and the tail of a *ranked* table is by definition the worse-placed half of the sky. It is the same shape, and now the same number, as `LifeList.TODO_PREVIEW` (14,584 px, fixed 08-13): `FRESH_PREVIEW = 12` rows, then *"Show all 75 well-placed targets"* and a "Show fewer" to fold it back. It hid here for so long only because no dogfood pass had an observing site, so this table had never been drawn with rows in it (v0.436.1). **Nothing is removed** — the owner's one hard constraint: the remainder is one tap away, the type filter still narrows the whole list, the count says how many are waiting, and the existing "N more targets aren't up tonight" note is untouched. **Before → after, measured in the browser on the same data: phone 10,430 px → 3,578 px, desktop 7,245 px → 2,346 px**, and the pass reports "nothing overflowing, no console errors". Tonight is no longer the tallest page in the app (3,578 px against the mosaic Target page's 3,475 px — comparable, where it was 3.4× before). Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change, and no data fetched or dropped — this is what is *drawn*. Tests +2, one red on a scratch revert (the fold, the count, that one tap lists all 30, that it folds back, and that a ranking which already fits is offered no disclosure at all).
- **v0.436.2** — 🟠 BUG (friendliness, PRIORITY 3), found by the v0.436.1 dogfood site step on its first run and verified red by a scratch revert: **the Tonight planner's score column clipped its own number on a phone — 145 badges on one page, and no gesture could reveal any of them.** A Mantine `Badge` is `overflow: hidden; text-overflow: ellipsis`, so inside a table cell it contributes **no min-content width**: the last column of a six-column table squeezed to a **15 px box against the 20 px "92" needs** (worse for a three-digit 100), and because the clipping happens *inside* the badge, scrolling the table never reaches it. This is the identical mechanism v0.434.1 fixed on the Nights card four days earlier — it survived here only because the Tonight table had never been drawn with rows in it, which is exactly the hole v0.436.1 closed. `NO_SHRINK`/`NO_WRAP` are now `frontend/src/badgeFit.ts`, with the reasoning and both instances' measurements in one place rather than in whichever table happened to be measured; `NightsCard` imports them and is otherwise untouched. Applied to the score badge and the four advisory badges sharing the squeezed row — the rule is content-independent (`max-content` makes a badge ask for its own text, so the **table** grows and its scroll container scrolls, the one failure a swipe can undo), so it can only ever widen and never re-breaks on a longer label. **Measured after, in the browser: 145 clipped badges → 0**, and the whole pass now reports "nothing overflowing, no console errors". Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change. Tests +1, red on a scratch revert — and honest about its limits: jsdom does no layout, so it pins the production value on every badge the row draws; the browser is the measurement.
- **v0.436.1** — 🟠 INFRA (maintainability in service of not missing bugs), the `LEAD` filed with v0.435.0 earlier the same day: **a dogfood pass now gives its scratch install an observing site, so the whole "plan a night" half of the app is finally in front of a browser.** The bundled samples' FITS deliberately carry no `SITELAT`/`SITELONG`, so `_resolve_observer` answered `"none"` and **Tonight, the Sky Map's placement, the life list's "Up tonight" chip, the wishlist prompt, `/api/plan/closing`, `/api/plan/week` and `/api/life-list/nearly-there` were in their empty state on every pass ever recorded** — while v0.426.0, v0.430.0 and v0.433.0 all shipped into that half in one week. Built as the entry's shape (a), for the reason the entry gives: the site is `PUT` into the **scratch install's Settings**, never written into the sample's headers, because a header location is something the planner *plans from* — a sample claiming a site would tell a real owner elsewhere which targets are up, computed for the wrong hemisphere. `DOGFOOD_SITE="lat,lon"` moves it (default 40.0, -2.0 — a round mid-northern latitude, obviously synthetic), `--no-site` skips it, and `--empty` never sets one, because a first-run app has no site and that empty state is what that pass exists to measure. The pass prints `location_source` and the row count, so a silent failure cannot pass for the old empty state. Sample pixels bit-identical (nothing shipped changed at all — tooling and AGENTS.md §7 only). **It paid for itself on its first run:** `/tonight` came back at **10,430 px on a phone**, 3.4× the next-tallest page and 3.5× the "worst page" figure the standing IA priority quotes, with **145 clipped score badges** — the v0.434.1 bug class, on the one table that fix could not have seen. Both filed and fixed below (v0.436.2, v0.437.0).
- **v0.436.0** — 🟠 BUG + PRIORITY 2 (autonomy), the `LEAD` the previous run filed and sized as copy — it was a real contradiction: **two screens disagreed about whether this picture has the subs for Drizzle, because they counted in different units.** The editor's print nudge closed with *"re-stacking with Drizzle (super-resolution) switched on, which pays off when you have plenty of subs"* on **every** picture, `bigger_print` being handed a paper size and nothing about the run; on the bundled 2×2 mosaic (~6 subs on each part of the picture) the app's own Stack form answers that re-stack with *"Consider turning Drizzle off for this stack."* Worse, the Stack form's **own** print panel carried a comment promising it could "never recommend the thing it would then warn against" while gating on `est.n_frames`, the target-wide total, where `drizzleTooFewHint` beside it gates on `perPixelSamples`: identical on a single field, and on the owner's raster the total clears the bar hundreds of subs before any pixel does. The bar is now one number — `drizzle_path.DRIZZLE_MIN_SAMPLES_PER_PIXEL`, mirrored once in `samplesPerPixel.ts` with a `test_drizzle_bar_mirror.py` drift guard like the other nine — and both surfaces read it **per pixel**: the panel via `perPixelSamples`, the nudge via new `field_fulls.samples_per_pixel_of_run` (the run's canvas ÷ its native frame with drizzle divided out, the same `field_fulls_of_sky` four other surfaces use, plus one `LIMIT 1` frame row — no FITS read, so `print-sizes` stays as cheap as it promises). Below the bar the sentence names the shortfall and orders the two steps — *"…this one has about 6 subs, against the ~100 it wants before it pays off. So keep shooting this target first, then re-stack with Drizzle switched on."* — and above it, or whenever the depth is unknowable (no canvas dims, no measured frame shape, an older run), it is byte-for-byte what it always said. `bigger_print`'s new argument is keyword-only and defaults to today's behaviour; the mosaic branch and `_print_plan` are untouched. No config, schema, on-disk, API-shape or default change. Tests +14 (5 `test_printexport`, 5 `test_field_fulls`, 3 `tests/webapp/test_editor.py`, 1 mirror) and +2 vitest; three fail-before, each verified by a scratch revert — and the Stack fixtures were handing the form two frames beside a 250-frame estimate, which is why the old gate passed. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.435.5** — 🟠 BUG (friendliness + trust, PRIORITY 3), Builder-found in a dogfood screenshot of the bundled M42 sample and verified red by a scratch revert: **"To make this even better" asked for "another clear night or two" two inches above a badge saying the target "usually looks good in well under an hour", with a goal of ~2 h printed between them.** v0.429.2 closed exactly this contradiction for the **Cluster** bucket and quoted the badge sentence in its own comment — but those words are `target_difficulty`'s **easy** verdict, which every *curated-easy* nebula and galaxy prints too (M42, M31, the Blue Snowball, the Cat's Eye), and `nextBestMove`'s integration rung only ever asked the object *type*. So the fix keyed on one of the things that earn the badge and missed the rest: on the sample the page carried three figures about one question and a night or two is several times the whole 2 h goal. The rung now asks `goalDifficultyFactor(difficulty) < 1` alongside the Cluster test — the very function the goal these bars are fractions of is scaled by, so the coaching line and the readiness card beside it cannot form different opinions about one object, and no new constant or threshold is introduced. `difficulty` was already threaded to both call sites by v0.429.2's own plumbing, so the change is contained to the shared helper. The Cluster sentences are byte-for-byte what they shipped (the subject is factored out, not reworded), and a **moderate**, **challenging**, un-curated or absent verdict keeps *"Galaxies and nebulae reward hours, so another clear night or two"* verbatim — M33's badge really does say "several hours". Frontend-only, copy only; no config, schema, on-disk, API-shape or default change. Tests +3 in `nextBestMove.test.ts` (the M42 case red before; plus the challenging/moderate/un-curated/absent side, and a byte-for-byte pin on the cluster wording).
- **v0.435.4** — 🟡 BUG (friendliness + trust, PRIORITY 3), Builder-found by the `--mosaic` dogfood pass reading the app's own sentences side by side as AGENTS.md §7 asks, and verified red by a scratch revert: **the panel-map card described a 30-second shortfall as "a few minutes", two inches above a note that called the same gap "about 30 s".** `mosaicmap._verdict_text`'s `behind` branch fires for *any* gap under `THIN_MIN_SHORTFALL_S` — anywhere in (0, 5 min] — and closed with the fixed phrase *"It's only a few minutes' difference at this stage"*, true only at the very top of that range. On the bundled 2×2 sample it read *"about 30 s there against 1 min on a typical panel. It's only a few minutes' difference"*: two figures of its own, then a third contradicting their subtraction. The half-fix that made this visible is the one the `stackhealth` `grain_uneven` note already carries — it quotes this very clause in its own comment as the sentence it stopped agreeing with, and says *"it's only about 30 s behind"* — so since then one picture carried two answers to "how far behind is it?" on one page. The branch now names the gap it measured (`median_s − behind.exposure_s`) through the same `sharecard.format_duration` and closes in the health note's exact words, so the app keeps one vocabulary for how long an integration is; a sub-second gap drops the figure rather than printing *"about 0 s behind"*. Advisory copy only — no threshold moved, no config/schema/on-disk/API/default change, and the `thin` and even-mosaic branches are byte-for-byte. Tests +2 new / +1 tightened in `tests/test_mosaic_map.py`, all three red before the fix.
- **v0.435.3** — 🟠 BUG (PRIORITY 1, the editor's preview↔export parity), Builder-found by measuring the open frontier AGENTS.md §1 names — scale-dependent parity on a mosaic-size canvas — and verified red at all three layers by scratch reverts: **Noise reduction's *bilateral* method leaves visibly more grain in the live preview than in the picture it saves, and nothing said so.** The proxy is a **stride**, not an average, so it carries the full-resolution grain at full amplitude while the physically-matched window has far fewer samples to average it with — the export's 2.0 px sigma gathers ~25 pixels, a step-4 proxy's 0.5 px sigma about 1.5. Measured against the noiseless truth (a change-based metric answers the wrong question and got the sign backwards first time): grain left in the preview ÷ grain left in the export runs **1.10 → 2.10** across strengths 0.45–0.95 and proxy steps 3–6, i.e. at the top of the slider on a mosaic the preview shows **twice** the grain the saved file will. **The direction is the dangerous one** — someone who cannot see the smoothing raises the strength until the preview looks clean and saves a picture smoothed twice as hard — and the op's own copy invites the trip (*"TV and bilateral are alternatives worth trying on heavier noise"*). Wavelet (the default) and TV set their threshold from the grain they are handed, match their export within 3 % at every step, and are deliberately never flagged. No arithmetic closes it (you can match the physical patch or the noise reduction, not both on a strided proxy), so it takes the shape `sharpen_understates_on_proxy` and `deconv_understates_on_proxy` already established: pure `denoise_understates_on_proxy` + `denoise_preview_understates` on the histogram + `denoiseUnderstatesCaption`. The rule is `strength / scaled_sigma >= 0.8` because neither term separates the grid alone, and 0.8 sits in a measured gap (every ≥1.10 cell scores ≥0.83; every one below scores ≤0.75). `bilateral_sigma_spatial` is now one function the render and the rule share; the value it returns is unchanged at every scale, pinned including the 2.0 the export uses. One additive boolean; no config, schema, on-disk, default or API-shape change. Tests +12, including the sweep's other clean result pinned rather than merely recorded — `detail.chroma_denoise`, the op behind the owner's worst reported mosaic result (v0.225.0), previews what it exports within 10 % and had no parity guard at all. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.435.2** — 🟠 TEST ROBUSTNESS, found when this branch's CI went red on a test the same commit passed locally: **`test_a_broken_project_doesnt_500_the_dashboard` patched `Project.open` process-wide and raised on *call number one*.** The app under test runs a job worker and a watcher thread, so any background open consumes that failure — both targets are then readable, both outages reported, and the test fails `2 == 1`. Red once on CI, never on `main`, and green nine times locally. It now breaks a **named** project instead of an ordinal one, which removes the race rather than hoping the ordering holds and asserts more than the ordinal did (*which* project is the broken one, and that the healthy one was still read); verified still armed by making the endpoint re-raise instead of skipping. The rule, for the next test: **a monkeypatch keyed on call order is a race whenever the thing patched is reachable from a thread the test did not start.**
- **v0.435.1** — 🟡 FRIENDLINESS (PRIORITY 3), found in the same dogfood pass and verified red by a scratch revert: **the Dashboard's "Your first image" card stopped telling someone with a finished, saved picture that the next thing to do was step two.** On the bundled sample — the app's own first-run path, which ships pre-solved and which the Dashboard offers a "Stack it" button for — the card read **"5 of 6 done"** over five struck-through lines and led with *"**Next:** Plate solving (ASTAP) is how AstroStack recognises the patch of sky in each sub…"*. `firstImageNextStep` took the first unticked step, and the ticks are **not monotonic**: `solve` measures *setup* (is ASTAP installed?) where the steps around it measure *outcomes*. The obvious repair — "the first unticked step after the last ticked one" — is wrong, and a test caught it: `checked` ticks from QC, which grades a sub with **no plate solution at all**, so a real first-timer with no ASTAP sits at `[frames ✓, solve ✗, checked ✓, …]` and solving genuinely is their next step. Each step therefore declares `passedWhen` — the keys whose completion *proves* it was walked past, `solve` being provable only by `stack` and beyond — and "next" is the first unticked step nothing proves they overtook. `firstImageSkippedSteps` names the rest and `firstImageLeadText` words both cases. **Nothing is hidden**: the skipped step stays listed, unticked and linked, and the ASTAP readiness banner that owns that fact is on the same screen. Frontend-only. Tests +9, four fail-before; one existing assertion **rewritten, not weakened** (it pinned the very behaviour the dogfood pass photographed as wrong). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.435.0** — 🟡 FRIENDLINESS / TRUST (PRIORITY 3), Builder-found by dogfooding rather than from the backlog: **the Tonight page stopped promising something the user's own library disproves.** With the bundled sample loaded and stacked — **27 plate-solved subs**, a Library full of "Solved" badges — the page still said *"it reads your location automatically from a plate-solved Seestar frame — so once you've solved some subs it'll just work"*. It had not worked and no amount of solving would: those frames carry no `SITELAT`. `detect_site_from_library` returned `None` for three genuinely different situations — no frames, frames with no site header, frames nothing could read — and the advice differs completely between them (more subs / only Settings / neither). New `site_location.SiteProbe(site, reason)` + `probe_site_from_library` is the **same walk**, counting what it touched, with `"unreadable"` claimed only when *every* probed path failed; `detect_site_from_library` and `detect_site_cached` become one-line wrappers, so all fifteen existing callers are byte-for-byte unchanged. `_resolve_observer_detail` carries it to `GET /api/plan/tonight` as an additive, always-present `location_reason` (`null` = nothing to explain). `frontend/src/siteUnknown.ts` owns the wording so the surfaces can't drift: the header case says more of the same won't help and points at Settings, the unreadable case points at the storage and **withholds** the Settings link, and an older backend / `null` / an unknown value falls back to today's exact sentence. No FITS keyword reaches the screen. Additive only — no config, schema, on-disk, default or existing-response-shape change. `detect_site_from_library` stays **the** walk (it gained an optional `_stats` accumulator) because an earlier shape that made it a wrapper left **ten monkeypatches across five test modules patching a function nothing called** — nine of them still green, including the one that raises to prove the probe does not run. Tests +14, four fail-before on scratch reverts. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.434.1** — 🟠 BUG (friendliness, PRIORITY 3), Builder-found by dogfooding the **mosaic** sample in a real browser and verified by reverting the fix: **a night's one-word verdict rendered as "SH…" on a phone, and no gesture could reveal it.** The Nights card on the Target page exists to put `sharp` / `soft` / `hazy` beside each night, under copy that tells the reader to act on it (*"Spotted a soft or hazy night? Set it aside"*) — and a Mantine `Badge` is `overflow: hidden; text-overflow: ellipsis`, so inside a table cell it contributes **no min-content width**: the column squeezed to nothing and the word was ellipsised *inside the badge*, where scrolling the table can never reach it. Measured at 420 px on the mosaic sample: the verdict `sharp` drawn **29 px wide against the 36 px its text needs**, while the first column wrapped "16 Nov 2024" over three lines and stood the rows at **70 px** against 31 px on a desktop. The fix is `min-width: max-content` on every badge the table draws plus `white-space: nowrap` on the night cell — so the **table** grows and its scroll container scrolls, which is the honest failure for a table too wide for a phone and the only one a swipe can undo. Content-independent: it follows whatever the label says rather than a width picked against today's three words. **Measured after:** nothing clipped, rows 31 px, the mosaic Target page **3,447 → 3,370 px** on a phone, the table at 497 px inside its 420 px container and the body still not scrolling sideways. **And the durable half — the probe's own blind spot is closed:** `scripts/dogfood_probe.mjs` skipped this for four passes because its overflow check excludes `text-overflow: ellipsis` as *deliberate* truncation, which is right for prose and wrong for a badge, since Mantine ships that property as component style. A new **CLIPPED-LABEL** probe checks badge-shaped anchors only, and is proven armed rather than trusted: reverted, it reports `29px box vs 36px word — "sharp"`; fixed, it reports nothing, and across 23 routes at 420 px it found exactly that one hit (the other clipped text app-wide is a target name on a tile, an object name on a tile and a logger name in the log table — each a truncated *name* with a full value elsewhere, which is the exclusion working). Frontend + tooling only; no endpoint, config, schema, on-disk, API-shape or default change. Tests +1, verified red by a scratch revert — and honest about its limits: **jsdom does no layout, so it pins the two production values rather than the pixels**, which is what stops a silent revert; the browser is the measurement.
- **v0.434.0** — 🟡 FRIENDLINESS (PRIORITY 3), the **eleventh slice** of "a Tooltip is invisible on the device the owner actually reads this app on", and it corrects the tenth's own closing claim: **the app's two maps — the mosaic panel grid and the imaging calendar — answer a tap.** Every earlier slice converted a *chip*; these two are *grids*, where every cell carries its own number and the picture says nothing without them. `MosaicMapCard` **does exist** and did on the day the tenth slice recorded that it did not (`frontend/src/components/target/MosaicMapCard.tsx`, PR #804, 2026-09-09) — so the card the owner, a heavy mosaic user, reaches to ask "which corner is behind?" answered on hover only, while the record said it had been checked; it takes `HintAnchor` as the chips did, but with a **roving `tabIndex`** over the grid rather than one stop per cell — the engine allows 24 panels a side and this owner shoots wide ones, so the chip precedent would put dozens of tab stops on the busiest page. The Dashboard's **imaging calendar** was on no list at all and is the harder half: ~370 cells, each imaged night's date/hours/targets on an 11 px square, hover-only. `HintAnchor` is the wrong tool there (a tab stop per night would put a hundred on the Dashboard), so the grid gets a **roving `tabIndex`** — exactly one night reachable, arrow keys walking the rest through new pure `activityCalendar.nightDates`/`stepNight`, stopping at either end rather than wrapping — and the answer in a **read-out sharing the legend's own row**, so no page gets taller; `role="grid"`, which it never earned, becomes `role="group"`. Hover is byte-for-byte what it was. Frontend-only: no endpoint, config, schema, on-disk, API-shape or default change. Tests +10, the two behavioural ones verified red by restoring the plain `Tooltip`. The class is now clean by enumeration: a scan of every non-test `.tsx` leaves five non-control anchors, each checked and each correct.
- **v0.433.0** — 🌟 NEW BEGINNER FEATURE (PRIORITY 2–3, the "plan" pillar), Builder-found by dogfooding the **first-run** app (`agent-dogfood.sh --empty`) rather than from the backlog: **"Up tonight" on the life list — which of the 110 can I actually shoot this evening?** The page's own headline says *"pick one and point the scope at it tonight"* and then draws M1…M12, an order chosen in the 1770s: **eight of those twelve are summer objects** (M4/M6/M7 in Sco, M8 in Sgr, M9/M10/M12 in Oph, M11 in Sct), so a northern owner opening it on a January evening is shown a screenful of sky they cannot touch. Measured on that night from London, **95 of the 157 bundled objects are shootable and 62 are not**, and nothing on the screen said which. New read-only `GET /api/life-list/tonight` asks `nightplan.well_placed_tonight` — the *same* dark-window/altitude/Moon blend behind the Tonight page, the wishlist nudge and the nearly-there card, so a life-list tile and a Tonight row can never disagree about one object on one night — and returns **ids only** (`{ids, location_source, min_altitude_deg}`), best-first, because the page already holds every name, blurb and thumbnail and a second copy could only drift. Its own route because it is an ephemeris pass (**0.31 s warm over the whole catalog, measured**) where `GET /api/life-list` is a registry walk. **One more chip in the `SegmentedControl` that was already there** — not a card, not a banner — and absent unless the sky can answer (no location, polar summer, nothing clearing the floor, or a backend without the route, whose failure is swallowed to `null` rather than becoming the page's error card), so a fresh install sees exactly today's three. In that one view the pure exported `applyFilter` replaces catalog order with the planner's ranking, and *only* there; `effectiveFilter` falls back to "All" if the answer goes away while it is selected; and the empty-half copy gained a season case, because *"You've got every one of these"* would have been a lie. Additive and read-only: no config, schema, on-disk, default or existing-response change, no project DB read and nothing written (pinned). Tests +9 Python / +10 frontend; **three Python tests verified red by mutation** (hard-coding the floor, sorting the ids) and the ordering claim red on both sides by dropping the sort. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.432.0** — **the full Moon, drawn to scale on your picture** (PRIORITY 3, beginner feature): the scale bar's own sentence (*"about 2.5 full Moons wide"*) as a faint disc at the Moon's true angular size, on screen (`AnnotatedImage`, bottom-right) and baked into the shared JPEG (`skymarks._moon_disc_box`, under the bar). `ScaleBar.moon_fraction` is **derived from** the bar's `fraction`, so it follows the auto-edit crop and a North-up save's re-basing for free and needed no new response field. Self-hides past `MOON_DISC_MAX_SHORT_FRACTION` (half the short side) rather than clamping — the sentence already answers a field that tight. Off by default; nested under History's "Scale & compass" and offered only where it fits, so the Save/share menu gains no item and the Target hero is unchanged. `tests/test_moon_disc_mirror.py` pins screen against file. Tests +36. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.431.1** — infra/trust: **the ninth hand-mirrored engine constant gets the drift guard the other eight have.** `weightingHint.ts`'s `WEIGHTING_MIN_MAX_MIN_FRAMES = 3` is the engine's `weights_applied` gate, quoted verbatim in the caution the Stack form and the Settings defaults both show, and nothing pinned it — a stale copy would tell a beginner their quality weighting is ignored on a stack where it is honoured, or stay silent on one where it is not. `tests/test_weighting_hint_mirror.py` pins the literal to `stacker.MIN_MAX_MIN_FRAMES` **and** pins that constant to `combine_method`'s own behaviour across the boundary (drizzle included), rather than to another copy of itself; both halves verified red by scratch edits. `combine_method` also stops spelling its gate `n >= 3` twenty lines above the constant that names it — the sigma-clip floor beside it deliberately stays a literal, since `DRIZZLE_REJECT_MIN_FRAMES` is a different claim that shares the number. Tests +2; no behaviour change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.431.0** — PRIORITY 2–3 (autonomy + friendliness), found by dogfooding the Target page rather than from the backlog: **"is it enough yet?" stops quoting M31 and M33 the same 6 h.** `readiness.ts` admits in its own comment that its per-type table "can't tell a bright emission nebula from a faint one"; `seestack/target_difficulty.py` exists precisely because it can, and the Target page has been printing its verdict as a badge beside the contradicting number all along ("usually looks good in well under an hour" over "3.0 h of ~6 h — a solid start"). A new `GOAL_DIFFICULTY_FACTOR` (easy ×0.5, moderate ×1, challenging ×1.5) applies the **curated** half of that verdict — never the "clusters are uniformly easy" type rule, which only restates the 1.5 h Cluster bucket — via a derived `DifficultyHint.curated` flag. Threaded to every surface that quotes a goal (readiness card, `nextBestMove`'s rungs, Dashboard progress, "Point here tonight", the Tonight row, mosaic effort), because a sharpened goal on one screen and a coarse one on the next is the same bug with the seam moved — and that threading found a second instance: an already-targeted Tonight row had been dropping the difficulty a catalog row of the same object carries. Additive and conservative everywhere: no verdict, an un-curated one, a user-set goal or an older backend all leave the goal exactly where it is today. Tests +8 Python / +9 vitest; five verified red by scratch reverts. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.430.1** — the surfacing half of v0.430.0 (PRIORITY 2–3): **the last week of a season reaches the screen the owner was already looking at.** The whole premise of "Shoot these before they're gone" is that nobody goes looking, so answering it only on the Tonight page serves the same person `best_months` already served. `ClosingSeasonNote` — one line and a link, ranked `advisory` — joins the Dashboard's existing `NoticeBoard` (inside the grouping, not one more always-on banner) for the narrow case that cannot wait for somebody to decide to plan: a target whose season ends **this week**. One constant, `CLOSING_URGENT_WEEKS`, decides "urgent" for both the note and the Tonight card's "Last chance" badge, so the two surfaces cannot drift apart about which targets those are. Self-hiding on an older backend, on a failed fetch, and most of the year. Tests +6 vitest. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.430.0** — 🌟 NEW BEGINNER FEATURE (PRIORITY 2–3, the "plan" pillar), Builder-found gap: **"Shoot these before they're gone" — the targets whose observing season is ending, before it ends.** `best_months` (v0.174.0) answers the seasonal question for *one* target, on the Target page, for somebody who went looking — and nobody goes looking, so a season closes quietly and the owner finds out months later that the autumn target he had three hours on is gone for a year. New pure `nightplan.season_closing` samples one night a week for eight weeks (one `_find_dark_window` plus one vectorised `_observability_batch` per sample, so the cost scales with the horizon and not with the library, exactly like `plan_week`) and names the library targets that are usable tonight and whose **last** usable sample is not the final one — the *last* sample, so a target that dips for a week and comes back cannot be reported as leaving. Whole nights, `best_months`' anchoring rather than `upcoming_dark_windows`' clip-to-now, pinned by a test that the answer at 21:00 and at 03:00 is identical. Silent when a target is not usable tonight (it has not arrived), and silent in polar summer (that is the nights, not the targets). `GET /api/plan/closing` (registry-cached, date-bucketed) and a self-hiding `ClosingSeasonCard` on Tonight above "Plan my week", each row naming what you already have on it — a target ten hours deep can be let go, a barely-started one cannot — tie-broken by `noise_gain_from_more_time` so it agrees with "Worth more time". Tests +10 engine / +4 API / +12 vitest. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.429.4** — 🟠 BUG (autonomy + image quality, PRIORITY 2/4), Builder-found on the walk-away path and pinned by a scratch revert: **a mosaic whose *readable* subs lie one deep on each panel was published as the target's newest picture.** v0.415.0 taught the minimum-frames floor to ask a pixel rather than a count (`_auto_stack_panel_depth`), but it measures the frames the **database** lists; the next guard, `_auto_stack_readability_hold` — the only one that asks whether those files are on disk — asked the floor of a count again (`readable < min_frames`). So between them the two guards covered neither case on a mosaic. Reproduced: two subs on one panel and one on a second, floor 2, one file of the deep panel off-line → the subs that remain are one per panel, single-frame colour speckle everywhere, and nothing held it (no earlier run's `n_frames_used` to catch it either). The hold now keeps the *readable* subs' pointings on the single `stat()` pass it already made and compares `typical_panel_depth` of that subset to the floor — monotone (a panel count can never exceed the total, so it can only ever hold more), byte-for-byte on a single field, and honouring the `min_frames <= 1` opt-out. `panel_depth`/`panels` ride on the hold record and on `AutoStackHoldOut` (defaulting to 0 = unknown), so the Jobs line (`heldForFilesLine`) and the Target page's `AutoStackHoldNote` (`holdReasonSentence`, `setAsideOutcomeSentence`) stop saying "thinner than the picture you already have" about a target that may have no picture. Tests +3 Python / +1 API / +4 vitest, one fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.429.3** — 🟠 BUG (friendliness + trust, PRIORITY 3), Builder-found in a dogfood screenshot and verified by a scratch revert: **"Worth more time" was ordered by the opposite of the number it prints.** Both cards that render `/api/plan/best-tonight`'s no-location picks head them *"ranked by how much another hour on each would improve it"* and print that percentage on every row — and the sample library listed **77 %** above **87 %**. `_depth_component` saturates at `_WORTHWHILE_NOISE_GAIN` (15 %), which every target under ~2.6 h of integration clears — most of a beginner's library — so on that path *every* pick scores exactly 100.0 and `_depth_only_picks`' `-hours_captured` tiebreak became the entire ranking: deepest first, i.e. the target that gains least on top, on the one card whose whole job is "which of these should I point at". The tie now breaks on the **unsaturated** `noise_gain`, so the printed percentages descend. The saturation itself is untouched and correct — it exists to stop an empty target dominating a well-placed one on the `sky × depth` path above, where the sky term still separates them; this path has no sky term. The placed path's own `-altitude_now_deg` tiebreak is unchanged. Engine-only; no config, schema, on-disk, API-shape or default change. Tests +1 (`test_the_worth_more_time_list_is_ordered_by_the_number_it_prints`), failing before with the exact reversed order, and asserting the monotonicity as a property across eight depths spanning the saturation point, not three hand-picked hours.
- **v0.429.2** — 🟠 BUG (friendliness + trust, PRIORITY 3), Builder-found by reading two modules that answer "how long is enough?" and verified by a scratch revert: **the "To make this even better" coaching line told every object it was a galaxy or a nebula, and judged it as one.** `nextBestMove`'s two time rungs (`SHORT_INTEGRATION_S` 1 h, `DEEP_INTEGRATION_S` 3 h) are not independent constants — they are `readiness.ts`'s own ladder boundaries (0.25 and 0.75 of the goal) evaluated at its **4 h** default, so they were right for a nebula and silently wrong for every other bucket. A star cluster (goal 1.5 h) at 50 min was "nearly there" on the readiness card and *"add more time — **galaxies and nebulae** reward hours, so another clear night or two"* two inches below it, under a badge reading *"usually looks good in well under an hour"*; a galaxy (goal 6 h) at 1.2 h was "a good start" on the card and *"a solid result — plenty of subs went in"* here. Both bars now come from `goalHoursForType` — the same per-type goal the readiness card and `mosaicEffort` already judge against — and the cluster bucket, the one the app's own `target_difficulty` calls "uniformly easy… need no integration to look good", gets a sentence that is true of it. `Target.tsx` passes `identity.data?.type` at **both** call sites (the badge and `coachKind`, which mirrors it). Omitting the type is the `Other` bucket's 4 h, i.e. today's 1 h / 3 h ladder bit for bit, so every caller without a catalogue match is unchanged. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change. Tests +5 vitest, **all five fail before** (checked by reverting the two behaviour lines in a scratch copy; the 22 existing cases still passed there, so the new claims are genuinely new) — including the property the other four are instances of: the rung this ladder picks and the level the readiness card prints agree on every bucket at every depth, mosaic included.
- **v0.429.1** — 🟡 FRIENDLINESS (PRIORITY 3), the **tenth slice** of the "a Tooltip is invisible on the device the owner actually reads this app on" entry, closing its named list: **the life list's still-to-shoot tiles and the best-months strip give up their sentences to a tap.** Both are the fifth slice's class — an anchor with *no behaviour at all*, where the tap does nothing and the words are simply not written on a phone. `LifeList`'s uncaptured tile carries `item.blurb`, the only sentence saying what the object *is*, across the whole half of that page where a beginner decides what to point at next; `BestMonthsStrip`'s twelve heat cells each carry that month's own numbers (*"up ~5.3 h in the dark, peaks 45°"*) — the visible verdict says *which* months, only the cells say *how good*. One `HintAnchor` line each. **The other two on the list are closed as non-defects, checked not assumed:** `ImageLightbox`'s six bare-icon anchors are category (b) — every tooltip is word-for-word its own `aria-label`, so nothing is being withheld and a `HintIcon` apiece would add six elements to a toolbar against the standing IA priority; and **`MosaicMapCard` does not exist**, a name that has sat on the list since the seventh slice. **No page got taller, measured** (`agent-dogfood.sh --empty`, before and after): `/life-list` identical to the digit at 2,779 px phone / 1,224 px desktop, because `HintAnchor` clones its child rather than wrapping it. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change. Tests +2, **both verified red** by restoring the plain `Tooltip`.
- **v0.429.0** — 🟡 FRIENDLINESS / TRUST (PRIORITY 3), the 2026-08-26 idea plus one instance of the bug it predicted, found shipping: **a target named `Sh2-155 – Cave` or `Gómez's Hamburger` stops printing a row of hollow boxes on every picture you share.** All nine modules that burn text into pixels draw with Pillow's bundled Aileron subset, which — probed character by character against its own `.notdef` — has **no glyph** for `—`, `–`, `×`, `→`, `≈`, a no-break space, all of Greek, or **any accented Latin letter**; and a target is named by its folder, so that text is the owner's. `tests/test_drawn_text_glyphs.py` has guarded *our* copy since v0.282.1 and says in its own docstring that it cannot guard the user's data — a test can't, a transliteration can. New pure `seestack/render/glyphs.py::safe_for_default_font` draws what the face can (**measured** against the real face, not a hard-coded list of what is missing), then transliterates what it cannot (`ω Centauri` → `omega Centauri`), then folds accents (`Gómez` → `Gomez`), and then **keeps the character** — a Cyrillic or CJK name survives byte-for-byte, because a box is bad and deleting somebody's target name is worse. Wired in before each renderer measures anything, so a shrink-to-fit sizes the string it draws. **Two live instances, neither imagined:** the app's own sample target is called `Sample: M42 mosaic (2×2)` (`webapp/sample_data.SAMPLE_MOSAIC_TARGET_NAME`), so every nameplate, keepsake and montage tile of the target a new install is invited to load baked a box into the middle of its own name — found by dogfooding; and `lifelistcard.grid_subtitle(n, n)` — *"The whole list — every one of them."* — drew an em-dash box on the poster a beginner sees the moment they finish the Messier list, missed because that builder was never added to the existing sweep; copy fixed and the builder (plus the whole bundled object catalog) added. Tests +41, including **twelve renderer pins that compare pixels** — all twelve verified red by a scratch revert — and a drift guard, proven armed by mutation, that fails on a tenth text-drawing module written without the net. Engine-only; no config, schema, on-disk, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.428.2** — 🟡 FRIENDLINESS (PRIORITY 3), found by opening a dogfood screenshot at full size rather than by reading the route: **the mosaic Target page said "about 4 fields of sky" and "(3.63-field mosaic)" about the same number, two inches apart.** The "even better" ladder and the thin-stack warning both go through `perPixel.fieldsOfSkyLabel`, whose docstring rounds to a whole field because *"the precision is spurious (the canvas includes its uncovered corners) and 'about 4.3 fields of sky' reads as a measurement rather than the rough scale it is"*. The "Is it enough yet?" chip beside the picture had its own hand-rolled `fieldFulls.toFixed(2).replace(/\.?0+$/, "")` — the same class `readiness.fmtGoal` was added to stop for the *hours* ("printing it raw is a real friendliness bug"), left unfixed in the parenthesis directly after them. The chip now uses the shared helper (*"goal ~14.5 h (about 4 fields of sky)"*), while the **tooltip keeps the exact multiplier**, where it is the arithmetic rather than a label, reworded to plain words and to close on the figure the chip shows. Single-field targets and user-set goals render exactly as before. The existing rounding regression is re-stated for the scale beside the hours (plain phrase asserted, `3.63-field` and `14.526…` both asserted absent, tooltip multiplier still reachable); **it fails before**. Frontend copy only. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.428.1** — 🟡 BUG (trust + friendliness, PRIORITY 3), Builder-found and pinned by a scratch revert: **the sky-brightness card said "compared with your other 3 nights" when two of them were others and the third was the night it was reporting.** "Was last night unusual for you?" is asked three times in this app, and two say the rule out loud — `session_recap._typical_other_fwhm` (*"Leave-one-out, so a night is never compared against itself"*) and `activity_calendar.off_night` (*"so the latest night is never its own yardstick"*). The third, `qc.sky_quality.sky_brightness`, took its baseline over **every** night including the reported one. Two measured consequences: on an **odd** night count a night that *is* the median is its own baseline, so the ratio is exactly 1.0 and the verdict is *"typical"* by construction (600/3000/**1000** ADU read typical; against its own two others it is 0.56× — *darker than usual*); on an **even** one it drags the yardstick toward itself (1000/1000/1300/**1310** read 1.14× *"typical"*, where the three others give 1.31× — *"about 31% brighter … expect a flatter, washed-out result"*, which is the picture the card exists to explain). `baseline` is now the median of the others and `nights` is how many those are — what its own comment always claimed, and what both sentences count, so the off-by-one goes with it. `MIN_NIGHTS` still gates on the total, so the card appears on exactly the targets it did. **And the date reads like a date:** `SkyBrightnessNote` printed the raw `2026-07-23` where every other night label in the app goes through the shared `formatNightDate` — the one date on the Target page that didn't look like one. Tests +5, **three fail before**; two existing `nights` assertions re-stated for the corrected meaning, neither loosened. No endpoint, config, schema, on-disk or API-shape change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.428.0** — 🟠 BUG (trust + friendliness, PRIORITY 3), Builder-found by reading two modules that explain the same thing and verified by reverting the fix: **a night lost to solid cloud was reported as "your stars were soft — check your focus".** Auto-grade flags a clouded sub on **star count** — its own reason text is *"far fewer stars than typical (120 vs 404) — likely cloud"*, and `_METRICS` calls it "≥30% of the stars gone: cloud, not detection jitter" — but `session_recap._REJECT_BUCKETS` had `star_count` in the **soft** row, next to FWHM and eccentricity. So on one night, from one set of `auto:grade:star_count` rejections: the run's "why were frames left out?" panel said **"Cloud, haze or moonlight — a clearer, darker night will keep more of them"** (`webapp.rejection_summary`, which had it right), while the Nights card and the session recap said **soft**, advising *"check focus (and dew on the lens)"* — and, because the one-word **hazy** verdict counts only the `cloudy` bucket, the night could never reach it: a yellow "soft" badge sat beside a one-click **Set aside** over a night nothing could have been done about. Two private copies of "which metric means what" were the cause, so the fix is to delete one: `seestack.qc.grading` — the module that both writes the reason and explains it in words — now owns `CLOUD_METRIC_NAMES` / `SEEING_METRIC_NAMES` / `metric_cause()`, and both surfaces resolve through it, keeping only their own bucket *names*. An unknown metric answers `None` rather than defaulting, so a future metric can't be quietly filed under the wrong cause. `livesession._conditions` buckets the same way, so the live "how is tonight going?" line said *"Mostly soft stars — worth re-checking focus"* **while the owner was still outside**, on a night that was clouding over. Tests +42 (`tests/test_reject_cause_agreement.py` drives both mappings from grading's own metric list, across all three namespaces and both spellings), **six fail before** on a scratch revert. Pure mapping change: no config, schema, on-disk, API-shape or default change, and every other reason string buckets exactly as it did. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.427.1** — PRIORITY 2/3 (autonomy + friendliness), the surfacing half of v0.427.0: **the rescue reaches the screen the beginner is already on when the solve fails.** The Jobs page's follow-up after a mostly-failed "Check & locate" has always answered *"should this happen automatically from now on?"* (a link to the `astap_bootstrap_solve` switch) — not the question the reader has, which is "locate **these**". New self-hiding `frontend/src/components/TryHarderButton.tsx` now sits under that nudge: it asks `reject-summary.deep_rescue_offered` (the engine's own gate) and renders **nothing** until the answer is yes, so a target that has never been solved, a still-loading or failed read, and an older backend all leave the card as it was. `qcSolveNudge`'s sentence now *describes* the capability with **no** imperative — it is a pure function of the job result and cannot know whether the button below it rendered, and the nudge fires at a 50 % miss rate where the rescue needs eight subs, so a "press the button below" would point at nothing; a test pins the absence of the imperative. The Settings link stays — the two answers do not replace each other. Shares the Target page's `["reject-summary", safe]` key, so the likely next navigation costs no extra read. Frontend-only. Tests +9, two verified red by a scratch revert. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.427.0** — 🌟 NEW BEGINNER FEATURE (PRIORITY 2, autonomy), the 2026-07-23 entry "Try harder to locate these": **the faint-field rescue is a button on the Target page instead of a switch in Settings you have to know exists.** On a faint target most subs never plate-solve, so the stack is the handful that did — and the cure has existed and been measured since v0.184 (`seestack/solve/bootstrap.py`: integrate the un-located subs into one deeper image, solve *that* once, propagate the position back), reachable only via `astap_bootstrap_solve`, off by default, while the un-located bucket's advice was "Run Plate Solve" — the very ladder that already failed on all of them. New `POST /api/targets/{safe}/rescue-unsolved` → `pipeline.submit_rescue_unsolved` runs **only** the rescue (`run_qc=False, run_solve=False, bootstrap_solve=True`), which needed the bootstrap block moved out of `run_qc_and_solve`'s `if run_solve:` — a no-op for all four existing callers. **The entry's real-data gate dissolves rather than being crossed:** routing the button at the measured bootstrap instead of a new ASTAP sensitivity profile means no flag is picked blind and the default ladder is untouched. **"Try *harder*" presupposes a first try** — the offer is the server's own `rescue_is_worth_offering(n_solved, n_unsolved, n_tried_and_failed)` on an additive `reject-summary.deep_rescue_offered`, built on `rescue_would_engage`, which is now the gate `bootstrap_solve` itself decides with; without the third term a freshly-scanned target with solving off would be offered a *propagated* position where the plain solver would give each sub its own verified one. Where offered it **replaces** "Run Plate Solve" rather than adding a second button (Plate Solve stays on the page itself — nothing removed). New pure `Project.count_solved` / `count_accepted_unsolved_tried`; `bootstrap_reason` on the summary and `Jobs.tsx::rescueUnsolvedNote` so a button-pressed job never ends on a bare "done". Tests +24, every production change verified red by a scratch revert. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.426.1** — 🐛 BUG (trust, PRIORITY 3), Builder-found and verified by reverting the fix in a scratch revert: **your imaging log was ordered by the afternoon each stack ran, under a comment claiming it put your most recent night on top.** `imaging_log.py` opens by explaining that the nights lead under "Shot" and the processing stamp sits at the end under "Stacked" — but `_collect_imaging_log` still sorted on `r.date`, the processing stamp, so the file's leading column was not monotonic and a **Reprocess everything** (which re-stamps every run within minutes) put the whole log in an order unrelated to when anything was shot. New pure `imaging_log_sort_key` → `(night, stacked)`, applied by `build_imaging_log_csv` itself so one place owns both the columns and the order; a run with no recorded night (schema < 18) falls back to its processing date, the same rule `pictureDateLabel` uses on screen, so the order follows the date each row *displays*; two re-stacks of one night tie-break on the stamp. **Not** the shipped "never flip a *sort* to capture time" rule, which is about lists of **runs** (History, the Library tile — both untouched); this is a list of **nights**, and the distinction is now in the docstring. Row order only — no column moved. Tests +6, one fails before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.426.0** — 🌟 NEW BEGINNER FEATURE (PRIORITY 2, autonomy), Builder-found gap — the sibling of v0.404.0's auto-stack offer for the *other* switch the walk-away chain waits on: **the Dashboard says when your pictures were stacked but not finished, and offers the one switch that finishes them.** `auto_edit_on_autostack` has shipped on since v0.395.0 but reaches only a *fresh* install (an install that has ever run carries an explicit `false` no upgrade may overwrite, §9), so the sequenced outcome of turning Auto-stack on is a chain that stacks every target overnight and stops one step short of the picture — a linear master, flat and dark, with nothing on any screen saying why (the one surface that mentions auto-editing, `LatestPictureCard`'s per-target opt-out, renders only on a run that *was* auto-edited). New pure `overnight.auto_stack_tallies` reads `(auto_stacked, auto_edited)` off the **same** `newest_scan_summary` read `needs_a_look` already makes, surfaced as two additive `0`-defaulted fields on `/api/last-night`; `autoEditNudge` fires on the *difference*, so a target finished by its own per-target preference counts as finished and a scan that stacked nothing says nothing. The trap worth carrying forward: `_pipeline_body` writes `auto_stacked` as a **list of safe names** and `auto_edited` as a **count**, so `_tally` accepts both shapes — a list through `int()` would have kept the note silent for ever with nothing failing. Tests +22. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.425.1** — 🐛 TWO BUGS (PRIORITY 3, friendliness), Builder-found by dogfooding the running app on the surface v0.424.4 had just made the default, and both invisible to a code read: **the offline Sky Map opens on your newest picture, and a star's name is no longer painted over by the star.** (1) `OfflineSky` opened its camera at `[0, 0, 0.1]` — RA 270°, Dec 0°, 70° across — *whatever the user had shot*, and the backdrop is sixty bright stars over the whole sphere, so the screenshot is a black rectangle with four specks while the badge says *2 images*. "Real sky (online)" has never done this: `AladinSky` centres on the newest picture at six picture-widths. New pure `initialSkyView` does the same, clamped into the viewer's own `[OFFLINE_FOV_MIN, OFFLINE_FOV_MAX]` zoom range so the first scroll can't jump to an edge; with no pictures it opens on the **brightest star in the catalogue the viewer is already drawing** (so it can never aim where the backdrop has nothing), and with neither it returns the old fixed view exactly. Non-finite coordinates are skipped rather than aimed at, Dec is clamped off `OrbitControls`' gimbal singularity, and the aim is decided **once on first render** so a refetch can't yank the view out of where the user dragged it. (2) `StarLabels` centred each name on its star, so the dot was painted through the middle of the word — "Rigel" read as `R∎el` magnified off the screenshot. The span now steps 12 px **below** the star. One fixed offset suffices because three.js sizes an attenuated point from the *viewport height* and not the field of view — now `starPointDiameterPx`, reading the named `BRIGHT_STAR_POINT_SIZE` the material uses. Verified in the running app before and after (`agent-dogfood.sh --build --no-stack`), not only in the suite. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change. Tests +9, five verified red by a scratch revert. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.425.0** — 🌟 NEW BEGINNER FEATURE (PRIORITY 2–3, autonomy + friendliness), the 2026-07-25 "Features that serve real workflows" entry: **a plateaued target now names the fresh one to point at instead.** The sky-limited verdict has ended on *"a darker sky or a brighter target will do more than extra time on this one"* since v0.207.0 — the right advice, and a dead end: it names the move and leaves a beginner to work out *which* brighter target, on a page with no answer, while the planner that answers exactly that (`/api/plan/suggest`, the showpieces he has not shot that are well-placed tonight) sat two navigations away on the Dashboard. `IntegrationTrendBadge` now asks it for its own best pick and prints it under the sentence — *"Try **M27 · Dumbbell Nebula** on your next clear night — Climbs to 64°, up about 7 h tonight. Moon out of the way. See what else is up →"* — through `suggestionHeading`/`describeSuggestion`, the same two pure helpers the Dashboard card renders, so the two surfaces cannot drift into two descriptions of one object. **The request is gated on the verdict, not on the page:** `enabled` on the *same* boolean that decides whether the component returns `null`, computed before the query so the two cannot disagree — an ordinary target, and a plateaued one whose verdict an add-time nudge is suppressing, issue nothing at all, asserted by two tests on the planner call rather than on the rendering. It shares `["suggest-targets"]` and the 60 s stale time with the Dashboard card. Every way it can have no answer — no location, no dark window, nothing new well-placed, a failed call, an older backend — leaves the verdict rendering exactly as it did before. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change. Tests +5, one verified red by a scratch revert; the file's harness gained the `QueryClientProvider`/`MemoryRouter` its six existing cases now render inside. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.424.4** — ⭐ BUG (friendliness + the LOCAL policy), the `READY` entry the owner answered 2026-09-11: **the Sky Map opens on the built-in star map instead of the one view that fetches sky imagery from the internet.** `initialSkyMode` (`frontend/src/routes/Sky.tsx`) fell through to `"online"`, so **"Real sky (online)"** — whose `AladinSky` pulls DSS2 tiles from CDS — was what loaded the first time he opened Sky Map on any device, and he said plainly that *"that mode that pulls imagery i am not a huge fan of"*. It also sits the wrong way round against AGENTS.md §1's local rule: the fetch is the browser's rather than the install's, which is why the 2026-09-08 sweep passed it, but defaulting to the only view that reaches out is against its spirit. The fall-through is now `"offline"` — the like-for-like swap, the same drag/zoom sky with his own pictures placed on it, minus the network. **Nothing removed** (his one hard constraint): all three modes stay on the switch, `MODE_KEY` still remembers whatever anyone picks, and `?view=online` still wins, so deep links and the Dashboard's "My map" line are unaffected. The online mode's own hint now names it as *"the only view here that fetches anything from the internet"* rather than the softer "(needs internet)". Frontend-only; no endpoint, config, schema, on-disk, API-shape or backend default change. Tests: the three `initialSkyMode` cases that pinned `"online"` re-pinned on `"offline"`, plus a new one asserting the three ways `"online"` is still reachable (stored, `?view=`, and the fall-through's absence) — fails before.
- **v0.424.3** — 🟡 the client half of the same lead (PRIORITY 1/3, "clunky controls"): **the Stack form's advice panel stops blinking out on every knob nudge.** Every control on the form is in the estimate's query key — it has to be, the answer differs for each — and *everything* under the form is derived from `estimate.data`: the sizing line, the time estimate, the memory verdict and its one-click fix, the print plan, the per-pixel cautions, the rejection-reach note, the drizzle nudge. With no placeholder they all went `undefined` together for the length of the request, so dragging the κ slider blanked the whole block and brought it back, once per tick. v0.424.2 made that ~130 ms instead of ~1 s; a fast answer that still blanks the panel first reads as a flicker rather than as a form keeping up, so the two belong together. **Not a bare `keepPreviousData`:** react-router does not remount this route when only `:safe` changes, so walking from one target's Stack page to another's would leave the first target's frame count and canvas size under the second one's title — showing the knob values you moved away from a moment ago is honest, showing another target's is not. New `frontend/src/stackEstimatePlaceholder.ts` owns that rule (`estimateIsForTarget`) and the query-key constant the four `invalidateQueries` calls now share. Frontend-only; no endpoint, config, schema or default change. Tests +7 vitest (5 on the predicate — including the other-target and not-yet-a-target cases — and 2 on the real form: the sizing survives a sigma-clip toggle and is *replaced* when the new answer lands, and a first visit still shows nothing at all). The first of those two verified red by deleting the `placeholderData` line.
- **v0.424.2** — 🟡 PERFORMANCE / friendliness (PRIORITY 3), the measured `(b)`+`(d)` half of the `/stack-estimate` lead: **the Stack form stops rebuilding the canvas for knobs that cannot move it.** Nine query params, and only `mosaic_canvas` reaches the canvas — every other one (the drizzle scale, κ, the min/max count, Auto) changes the *peak* or the *rejection answer* off a canvas it cannot touch, and yet each is in the query key, so on the owner's biggest target every nudge re-read one WCS per sub to refresh a sentence. New `webapp/estimate_cache.py` holds the `StackCanvasBasis` per `(project, canvas mode)` and **revalidates it on every lookup** against `Project.frames_fingerprint()` — `SELECT *` over the whole frames table, hashed — so the staleness trade the entry's own `(b)` was warned off does not apply: a new sub, an accept flip, or a re-solve that rewrites one `wcs_json` to *the same length* all miss, by construction rather than by a column list somebody has to keep in step. Measured on the entry's own shape (9-panel, **5,477** synthetic solved subs, this box): a warm lookup is **129 ms** against the **1,007 ms** the uncached path costs every time (a cold one pays both, 1,116 ms); `/rejection-outlook`, which the Target page fires on every load, rides the same held basis. A failure ("nothing solved yet") is never cached, so a target answers on the request after its first solve. The `(d)` shape the entry leads with — splitting the rejection answer out — turned out not to be available: `min_max_reject*`, and `auto_reject`/`sigma_kappa` through `_resolve_auto_reject`, all move the peak. Pure optimisation: one test asserts the whole warm response is byte-identical to a cold one, and the two staleness tests were verified red by deleting the fingerprint comparison. Tests +15 (`tests/test_project_fingerprint.py`, `tests/webapp/test_estimate_cache.py`). No config, schema, on-disk, API-shape or default change; nothing persists, so an upgrade and a restart are indistinguishable from it.
- **v0.424.1** — PRIORITY 1 (the editor), the surfacing half of v0.424.0: **the measured blown core reaches the note a beginner is actually reading.** `blownCoreCaption` only ever rendered inside the op panel, under `if (selectedOp.id !== "tone.stretch") return null` — so a user who opened the editor on an auto-seeded recipe (v0.390.0), read *"This picture was auto-edited"* and looked at a white blob where their galaxy core should be was shown nothing unless they thought to click "Stretch". Both Auto notes now carry the same nudge, through one shared `BlownCoreNudge` (the op panel's copy moved into it — one definition of the sentence and the button, not three), rendered *inside* the note rather than as another card. The op it is about is not guessed: new pure `blownCoreStretchOp` mirrors the server's own fallback (`solve_highlight_protect` with no uid → the recipe's first `tone.stretch`), stands down when a *second* Stretch is selected, and says nothing when the Stretch is switched off. The solve is asked for only while a note is up **and** the first preview has rendered, so it never competes with the picture the user is waiting for — pinned by a test that fails if the endpoint is called on a recipe with no note. Frontend-only; no endpoint, config, schema, on-disk, API-shape or default change. Tests +8 (one of them v0.424.0's per-channel colour invariant, a commit late), one fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.424.0** — ⭐ PRIORITY 1 (the editor), the 2026-08-06 measured entry: **"Hold back highlights" starts working on the frames it exists for.** The shoulder ran *before* the midtones transfer, and on a frame whose sky sits far below the 99.5th-percentile ceiling the transfer collapses (`m` → its 1e-3 floor) and squashes the shoulder into the last **0.0004** of the display range — the slider moved its knee 0.70 → 0.25 and the finished picture did not change (blown fraction 8.65 % at strength 0, 0.5 *and* 1.0, identical to three decimals). New `_reanchor_highlights` runs **after** the tone curve, in display space: the sky's own ceiling (median + 6σ) and everything below it is untouched bit-for-bit, the mid-tones are compressed into what is left, and the shoulder is expanded onto a reserved `_HIGHLIGHT_HEADROOM_MAX` × strength (0.20 at full). It declines whenever there is nothing to win or no room to win it in — strength 0 (so every default render in the app is byte-for-byte historical), a shoulder that already has room (an ordinary compact-core frame, measured: 0.20 unaided), or a sky already at the knee. **Not the lever the 2026-08-06 prototype stood down on** (that one repositioned the *knee* and measured that the band above it still crowded into 0.15 % of the range — this is that residual), and its "unreachable on 16-bit data" finding needed refining: the collapse is driven by `(p99.5 − sky)/σ_sky`, not `max/sky`, so a broad core over 0.5 % of the frame reaches it at an ordinary 16-bit peak. Measured on 16-bit-realistic scenes, as distinct 8-bit levels across the core at full strength: **3 → 9** (64 k peak, 40 px core), 8 → 18, 22 → 27, and unchanged or declined where the old path already had room. The "from your image" button and the passive auto-edit highlight telemetry both stop self-hiding on exactly these frames. Tests +11, four fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.423.0** — 🌟 NEW BEGINNER FEATURE (PRIORITY 3, friendliness — the standing "audit every screen for jargon" item): **the glossary reaches the app the owner actually runs.** `docs/glossary.md` has explained FWHM, drizzle, sigma clipping and twenty-odd other words in plain language since the desktop days, and the web app has never been able to show one of them: `docker/Dockerfile` copies `frontend/`, `seestack/`, `webapp/`, `pyproject.toml` and `README.md`, so a file in `docs/` is in every checkout, every test run and every CI job and **absent from the only build the owner installs** — reachable solely from the historical PySide6 GUI's F1 key. Moved to `seestack/data/glossary.md` (package-data `data/*.md`), parsed by a new pure `seestack/glossary.py` into `(intro, terms)` with a stable typeable anchor each (`_slugify`: a *spaced* slash separates synonyms, a bare one is part of one name, so `"Cache (Stage 1 / Stage 2)"`→`cache` and `"Min/max rejection"`→`min-max-rejection`), served by `GET /api/glossary` (`webapp/routers/glossary.py`, `lru_cache`d — it is a file inside the image), and rendered at **`/glossary`** with a search box that reads the explanations as well as the names, so "satellite" finds sigma clipping. Deep-linkable: `FrameColumnGuide` now ends with a link to `/glossary#fwhm`, which is where the desktop table's own tooltip used to say "see the glossary". No markdown dependency — `glossaryMarkdown.tsx` renders the four constructs the file uses and nothing else, every span a React child, so there is no path from the file to raw HTML. **The content was refreshed, not just moved**, because a reference page that teaches a control the app no longer has is worse than none: the Gaia colour-calibration mode (retired v0.418.0) is gone, ASTAP is described as bundled rather than "download it", the cache entry points at the Storage page instead of "the GUI", and the desktop-only Conservative/Balanced/Aggressive presets — which this app does not have — are replaced by **Auto-grade**, the thing that actually answers that question here; nine terms the web app says out loud and the file never defined were added (integration time, seeing, dithering, panel depth, linear vs display-space, recipe, SCNR, master dark/flat/bias, hot pixel, noise σ, auto-stack, incoming folder). One nav link, in the existing **System** group. **Deliberately no alias list**: every spelling of a term is a substring of its own heading, so the page's substring search finds it already — an alias branch would have been a rule only a synthetic fixture could exercise. Additive throughout: new endpoint, new route, no config/schema/on-disk/API-shape/default change. Tests +14 Python (`tests/test_glossary.py`, `tests/webapp/test_glossary.py`, and two in `tests/test_image_contract.py` — the packaging one verified red by reverting the `data/*.md` pattern) / +34 vitest. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.422.2** — 🟠 the same claim on the **walk-away** surface, which is the one a beginner does not have to open: the Jobs card's "Process target" result. `rejectionNote`'s docstring says it is "kept honest and consistent with the engine's `stackhealth.py`", so after v0.422.1 it was the copy disagreeing. Two fixes: the min/max guarantee is **withheld** below the per-pixel floor (new mirrored `MIN_MAX_MIN_SAMPLES`, guarded against `MIN_MAX_MIN_FRAMES` by `tests/test_min_max_floor_mirror.py`) instead of being softened — retiring a test that pinned *"only 1 sub stacked, AstroStack dropped the brightest and darkest value at each pixel"*, which cannot be true; and *"Because only N subs stacked"* stops naming the **target's total**, the v0.419–v0.421 substitution in a sentence those four runs walked past. The panel depth is what chose the method (`_resolve_auto_reject`, as v0.399.1 fixed on the Stack form) and what the guarantee is about. Measured on the mosaic sample this run dogfooded: 21 subs, ≈3.6 field-fulls, depth ≈6 — the card said *"only 21 subs stacked"*. Reads the same `field_fulls` the thin cue two lines above already gets, so no new request and no new field; single field and older backend byte-for-byte identical. Tests +6, three fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.422.1** — 🟠 BUG (image-quality / trust, PRIORITY 3–4), Builder-found and reproduced on the accumulator itself, from the "a whole-canvas claim a per-pixel number contradicts" class: **the min/max drop has a floor of its own — three subs *on a pixel* — and the finished picture was the one surface that did not know it.** `MinMaxRejectAccumulator` averages 1–2-sample pixels in verbatim ("can't spare two"), verified by running it (a pixel covered by 10 and a 1000-ADU trail comes out **505**; covered three times, **10**) — yet `stackhealth` praised every `min-max-reject` run with *"Dropped the brightest and darkest value at each pixel, so a lone satellite or plane trail can't show up in your final image."* Reachable on the owner's shape: `auto_reject` sizes the method from the thinnest *substantial* panel, so a mosaic part-way through its panels records the mode while half its canvas is 1–2 deep. `lone_outlier_min_depth`'s own docstring names the three surfaces that "must never disagree"; `rejection_reach` (the Stack form, pre-run) and `REJNEED`/`REJREACH` (the master's header) already answered min/max correctly — `stackhealth` called `kappa_min_frames` directly and excluded the mode. It now reads the shared helper and admits min/max to the `rejection_blind` note under the same two provable claims (`coverage_max < 3` → nowhere; `coverage_median_depth < 3` → over at least half), with its own reason ("before there is a brightest and a darkest it can spare") and **no `action`**, because no switch helps — more subs is the only fix. The praise stands down when the note fires (one picture, one answer); nothing removed, and a genuinely trimmed run keeps its sentence verbatim. History's chip gains the same qualifier on a 0 % min/max drop that the κ-σ branch already had. Advisory copy only — no config/schema/on-disk/API/default change, no threshold moved, κ-σ and drizzle wording byte-for-byte. Tests +6, three fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.422.0** — 🌟 NEW BEGINNER FEATURE (PRIORITY 2–3), the Scout's "Shoot the Moon tonight" idea filed the same morning: **the app plans a Moon *session*, not only a Moon nuisance.** The owner shoots the Moon — the whole `seestack/video` lucky-stacking workflow and the Moon & Sun page exist for it — but the Moon appeared in the app only as *interference* to a faint target and as a *stacking input* once a capture was already on disk; to learn whether tonight was any good for it you opened another app. New `nightplan.moon_shoot_tonight` answers **when** (the widest stretch the Moon is above `MOON_SHOOT_MIN_ALT_DEG`=20° while the Sun is down) and **what it will look like** — the one counter-intuitive fact about lunar imaging, which runs opposite to a beginner's instinct: a **full** Moon is the *worst* night for surface detail, because sunlight then comes from behind you and nothing casts a shadow, while a crescent/quarter/gibbous throws long shadows along the terminator. Four bands (`_moon_shoot_verdict`, pure). It goes **into** the Tonight page's existing Moon card, not beside it (a chip + one line + a link to Moon & Sun), per the standing "prefer a consolidation over a new card". Self-hides — `None` — when the Moon never clears the floor or does so for under 30 minutes, both measured on real London nights (2026-01-03 up 18:38–06:38 peak 63° → `flat`; 2026-01-25 up 16:35–22:35 peak 53° → `great`; 2026-01-21 above 20° for 15 min → declined; 2026-01-15 never → silent). **No libration, no terminator longitude, no network** — and no second ephemeris path: the illumination and waxing sense are passed in from what `plan_tonight` already computed, and `_widest_true_run` was lifted verbatim out of the dark-window scan so the two cannot drift. One additive `NightPlan.moon_shoot`, `None` by default. Tests +27 Python / +8 vitest, the endpoint pair and all eight frontend ones verified red first. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.421.0** — 🟠 the seventh instance of the per-pixel/target-total substitution, and the first that left one surface *disagreeing with another about the same picture*: **the thin-stack cue reaches its other three surfaces on a mosaic, not just the Target page.** `thinStackWarning` exists for the owner's "gibberish" case, and v0.419.1 made it read a run's own `field_fulls` — but only at the Target page's call site. Its three others still passed the bare count: `FrameCountBadge` on the **Dashboard** strip and the **Gallery** grid (whose own docstring says it is there "so a single-sub stack can't masquerade as a good picture"), and `processTargetSummary` on the **Jobs** page — the walk-away path, i.e. where the owner actually meets a thin mosaic. Nine subs over a 3x3 raster is one sub everywhere: the Target page called that picture a single sub while the front page badged it a plain violet "9 frames" and the job reported a green "Stacked 9 frames". Neither listing carried the figure at all, so the fix is one additive `field_fulls` on `GalleryItem`, `RecentStack` and the stack job's result dict, each from the same `webapp.field_fulls` helper the History listing uses (one `LIMIT 1` frame-shape read per target, not per run); plus `drizzle_scale_of`, so the job — which holds its options as a dict — shares one definition of "was this drizzled" rather than re-serialising. Tests +9 Python / +9 vitest, **all thirteen of the new behavioural ones verified red first** by stashing the production files. No config, schema, on-disk, API-shape or default change; every field is `None`/absent on a single field and on an older backend, which reads as today's behaviour exactly. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.420.0** — 🟠 the same substitution one page *upstream* — the pre-run **Stack form**. Every caution there is a claim about the samples on **one pixel** (drizzle fills an output pixel from the dither-phased samples that hit it; κ-σ estimates each pixel's spread; a min/max trim of `k` needs `2k+1` frames *per pixel*), and four were computed from `solvedAccepted`, the **target's** total — 25 vs 225 on the owner's 3×3. The asymmetry is the bug: the *nudge* toward drizzle already stands down on a mosaic (`!estimate.data.is_mosaic`), while `drizzleTooFewHint` fires below 100 **frames**, so a nine-panel raster at 225 subs sailed past it and the form said nothing while drizzle spread 25 samples a pixel across a finer grid — reached the ordinary way, via **“Reuse settings”** from a single-field run. Also `sigmaKappaLargeHint` (urging a *tighter* κ≈2.5 because “the per-pixel spread is very well measured”), `minMaxKTooHighHint` (whose sentence already said *“frames per pixel”* and then quoted the total) and `minMaxRejectHint` (3–11 frames, so a 54-sub mosaic 6 deep is inside κ-σ's blind band on every pixel and outside the window on the total). Fixed by serving `panel_depth` at the **top level** of `/stack-estimate` — the same `auto_reject_depth` its own `rejection_reach`/`auto_reject_resolved` answers use, not a second definition — and one shared `frontend/src/samplesPerPixel.ts` (`samplesPerPixel` / `spreadAcrossPanels` / `samplesPerPixelPhrase`). Mosaic copy names both figures (*“about 25 subs on each patch of sky (225 in total, spread across the mosaic)”*); single-field wording is byte-for-byte unchanged, as is an older backend. +19 tests, 8 of them red before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.419.1** — 🟠 the same substitution one surface further out, verified the same way: the Target page's **"💡 To make this even better"** ladder and the **thin-stack warning** asked per-pixel questions (`THIN_STACK_MAX_FRAMES` 4; `SHORT_INTEGRATION_S`/`DEEP_INTEGRATION_S` 1 h/3 h) of the target's totals. Nine subs over a 3×3 is one sub everywhere and the warning stayed silent because 9 > 4 — while v0.415.0's `auto_stack_min_frames` *holds that very mosaic back*, so the two surfaces disagreed about one picture; and a 12×8 raster at 3 h (under two minutes a panel) returned `null`, "genuinely deep and healthy". Fixed with a shared `perPixel.ts` (`canvasFieldFulls`/`perPixel`/`spansMoreThanOneField`/`fieldsOfSkyLabel`) that `integrationTrend` now shares; the **locate** rung is deliberately left on the honest session counts. Mosaic copy names **both** figures and the spread that reconciles them. Not wired to the Gallery/Dashboard/Jobs surfaces, which would need a per-target read on endpoints that iterate every target — recorded as a decision. +17 tests. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.419.0** — 🟠 a verified bug I reproduced myself, from the *"surfaces that report depth"* rotation brief the 2026-09-10 `dg6420` run handed forward: **`integrationTrend` fitted its noise-vs-time falloff against each run's `total_exposure_s`, so a mosaic whose canvas *grew* read as one whose noise had stopped falling** — a 2×2 raster at 0.5 h a panel followed by a 3×3 at 0.5 h a panel has 2.25× the total light and identical grain, and `IntegrationTrendBadge` put *"more subs won't help it much"* on the Target page of a mosaic a few subs deep everywhere (it also silenced `cardGrainProjection`). Fixed by fitting against **per-pixel** integration — a new `perPixelSeconds()` divides each run's total by an additive per-run `StackRunOut.field_fulls` (`webapp.field_fulls.field_fulls_of_sky` on that run's own canvas; `native_frame_shape` split out so the listing reads the native shape once, not once per run). The sentence still names the target's **total** hours. Bit-for-bit unchanged wherever two runs share a canvas — every single-field target — and pinned as such. +15 tests. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.418.2** — 🟠 the **third and final** part of the fourth external audit's "fixtures that cannot exhibit their bug" entry, closing it: **the v20/v21 migration tests passed with their migration steps deleted outright** (reproduced first). Two problems, and the entry named one. Named: an additive nullable-column migration and the runtime `_reconcile_table_columns` net produce the same schema, so `_disable_the_runtime_backfill` switches the net off and leaves `_migrate_schema` as the only thing that can pass. Unnamed, and where the durable value is: a fixture built from today's `SCHEMA_SQL` **tracks** it, so a forgotten `ALTER` could never make this file red — the fixtures are now **frozen DDL literals** (`_V20_FRAMES_SQL`, `_V21_FRAMES_SQL`, `_V20_STACK_RUNS_SQL`) and `_assert_tables_are_fully_migrated` checks every authoritative column arrived. Verified against three scratch reverts: the v21 step deleted, the v22 step deleted, and **a new `SCHEMA_SQL` column with no migration step** — the v0.119.8 live-install brick, red in this suite for the first time. Tests-only; nothing weakened. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.418.1** — 🟡 FRIENDLINESS (PRIORITY 3) + §9, a bug from the fourth external audit reproduced and closed: **the editor and the Stack form offered a colour-calibration mode the image cannot run and the owner has declined.** `color_calibration_mode="gaia"` imported an `astroquery` that is in no dependency list and absent from the image, the broad `except` swallowed the `ModuleNotFoundError`, and the solve silently became gray-star — and it was a CDS **network** call, which AGENTS.md §1 declines as standing policy. Reproduced by restoring the old dispatch: `Gaia calibration failed (No module named 'astroquery')`. The option is gone from `_MODE_CC`, the StackOptions descriptor and the historical `stack_dialog` combo; `calibrate_color` answers a stored `MODE_GAIA` with the gray-star solve **and stamps `GAIA_RETIRED_NOTE`** so the editor's read-out says what ran, and nothing imports `astroquery` any more. **The §9 half is the load-bearing one:** removing an enum choice makes `validate_stack_options` *reject* a value an old `default_stack_options` legitimately holds — a 422 on every Stack submit and on the auto-stack chain — so new `RETIRED_OPTION_VALUES` + `normalise_retired_option_values` translate it at the four places it surfaces (both chokepoints, the form merge, the settings write), while a genuinely wrong value is still refused. Tests +8, **all eight fail before**, verified by three scratch reverts — one rewritten because the pre-fix broad `except` swallowed the assertion and it *passed on the bug*. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.418.0** — 🟠 INFRA / upgrade-safety (AGENTS.md §8 "green means the checkout passed, not that the owner's install works"), the `READY` entry from the fourth external audit: **CI now builds and runs what the owner installs, not only the checkout.** A third `image` job does `docker build --target frontend -f docker/Dockerfile .` (cheap — stops before the ASTAP download) and then a Python smoke that copies *only* what the Dockerfile copies, `pip install`s it **non-editably** and imports `webapp.main` / `webapp.sample_data` / `seestack.nightplan` from `cd /` — the three properties `pip install -e .` at the repo root can never test (package-data that never reached the wheel, CWD-dependence, a tree that is importable anyway). **Plus `PySide6` out of the base `dependencies` into a new `gui` extra**, so the image's own `pip install .[web]` stops pulling ~650 MB of Qt it never imports — measured with a `--dry-run` resolve (zero PySide6/shiboken, where the old pyproject installed them); `agent-setup.sh` and AGENTS.md §7 move to `.[dev,web,gui]`. And three smaller ones from the same audit: `npm install` → `npm ci` with the lockfile copied unconditionally, the dead `ENV ASTROSTACK_PORT` dropped, and compose's `/data` bind given `create_host_path: false` so a mistyped `ASTRO_DATA` fails loudly instead of booting on an empty library. Tests +9 (`tests/test_image_contract.py`), **seven fail before**, each verified by a scratch revert — including one rewritten because the obvious version *passed on the bug*. No config, schema, on-disk, API or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.417.1** — 🟠 two fixtures from the fourth external audit that **passed on the bug they name**, each now verified red against a scratch revert of the production fix. `displayspace.assert_shadow_clip` replays the pre-A1 `_sky_mode` histogram and requires the clipped-zero bin to *win* it (the old guard only said the clip was *present*), and `test_the_sky_stays_put_at_every_stack_depth` — which had drifted onto a hand-rolled `clipped_fraction > 0.005` instead of the shared guard — carries an explicit `exhibits_a1` flag, the measured boundary being between 0.001 and 0.0008. `test_a_ragged_mosaic_still_gets_its_fringe_trimmed` now asserts the exact rect `(5/400, 5/400, 395/400, 395/400)` rather than a `0.90 < kept < 0.99` window the reverted rule's 0.902 sat inside. Tests-only: no engine, webapp, frontend, config, schema or on-disk change.
- **v0.417.0** — ⭐ 🔴 PRIORITY 1, the **remaining two halves** of the fourth external audit's "owner hits this first" entry, closing it: the same over-trim note on the **Target page** (`OverTrimmedTargetNote`) and the **library-wide count on the Dashboard** (`OverTrimmedNote` over a new `GET /api/over-trimmed-pictures`), so the question "*which* of my pictures is this?" has an answer without opening every target. Both read one server-side verdict — new `webapp/stale_crop.py` + `…/editor/crop-health`, factored through `editor.crop_health_for_run` so the scan and the per-run answer cannot name different pictures — and that verdict adopts the editor's shipped rule verbatim (`STALE_CROP_KEEP_RATIO` 0.25, silent when the border rule proposes no trim), with a drift test grepping `mosaicTrim.OVER_TRIM_KEEP_RATIO` so the two copies can't diverge. `sharePctLabel` is now shared, so all three surfaces round one measurement the same way. Read-only throughout: a saved recipe is never rewritten. Tests +27. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.416.0** — ⭐ 🔴 PRIORITY 1 (the editor), the **editor half** of the fourth external audit's "owner hits this first" entry, filed the same day and reproduced in the shipped image: **a mosaic Auto-edited before the D1 fixes keeps the old over-trim in its *saved recipe*, and every surface shows the sliver.** The fixes re-derive the trim; nothing compared a stored crop against it. New `mosaicTrim.overTrimmedVerdict` weighs the recipe's live enabled crops (`cropCoverageFraction`) against the rectangle `/editor/trim-suggestion` already fetches, and under `OVER_TRIM_KEEP_RATIO` (0.25) of what the canvas offers says so — *"cropped down to about 3% of the stack, but about 92% of it is well covered"* — with **Re-trim border**, which is the existing trim *preview*, so the user sees the rectangle before `applyTrimCrop` replaces only the Crop op. Where the stored "what Auto did" note is on screen the Alert also says its trim figure describes the crop being replaced, closing the gap between two sentences a beginner reads together. A quarter rather than the entry's suggested half, because at 0.5 a deliberate crop to the middle 40 % of a mosaic gets accused while the measured case is 3.4 % against 92.4 %. Frontend-only, no new endpoint and no new request; the Target-page note and the Dashboard library-wide count stay open on the entry. Tests +9, two fail before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.415.1** — PRIORITY 4 (image quality, on the mosaic path that is on by default), a bug verified by reproduction and fixed in one run: **a mosaic panel that nothing could measure was dimmed anyway.** `overlapgain`'s own module docstring promises *"a panel that loses every pair keeps 1.0"*; `_solve_log_scales` ended with `solution - np.median(solution)`, and `lstsq`'s minimum-norm 0 for an unpaired panel only *means* 1.0 while that median is itself 0. Minimum-norm zeroes each connected component's **sum**, not its median, so a lopsided graph (three panels each reading 1.2× against a fourth, plus one sharing nothing) put the unpaired panel at **0.9554** — a 4.5 % dimming of a whole tile from an overlap that does not exist. Reachable on a star-poor overlap strip, i.e. the faint-field case. New `overlapgain._normalise` centres only the panels carrying a *surviving* pair (read at the point the fit is accepted, since the drop-and-refit loop can strand a panel that started out paired) and pins the rest to exactly 1.0. A fully-measured mosaic is byte-for-byte unchanged, pinned at `atol=0, rtol=0`. The existing `test_a_lone_panel_is_left_at_one_rather_than_dragged_along` passed throughout — its single symmetric pair makes the whole-solution median 0 by coincidence — and is kept, with the new test beside it saying what it cannot. Tests +2, one fails before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.415.0** — PRIORITY 2/4 (autonomy + image quality), a bug verified and fixed in one run: **the walk-away minimum-frames floor counted a mosaic's subs, not its depth.** `auto_stack_min_frames` exists to stop the hands-off scan publishing single-frame colour speckle, and asked the question of the target's *frame count* — right on a single field, wrong on a mosaic, where a 3×3 one pass in has nine subs and a picture one sub deep everywhere, so `9 >= 3` waved it through on exactly the canvases the owner shoots. New `stacker.panel_frame_counts` + `typical_panel_depth` (the **frame-weighted** median panel depth — stray-proof, and it does not strand a mosaic for one thin corner the way the thinnest panel would); the hold reuses the existing `auto_stack_held_thin` discipline (no attempt marker, self-clearing) and `auto_stack_min_frames = 1` stays the opt-out. Plus the three sentences that would then have argued with their own numbers — Jobs, the Dashboard's overnight digest, and the Target page, which could not see this hold at all until the new read-only `GET /api/targets/{safe}/autostack-thin-hold`. Single field byte-for-byte unchanged. Full entry in [`SHIPPED.md`](SHIPPED.md). Tests +30, three fail before.
- **v0.414.2** — 🐛 VERIFIED BUG (upgrade-safety, AGENTS.md §9 "the container still builds and boots"; Builder-reproduced 14 times by accident this run): **the app refused to boot over a missing *frontend*.** `main._mount_spa` read "is the frontend built?" off `STATIC_DIR.exists()` — the *directory* — then mounted `static/assets` unconditionally, and `StaticFiles` raises in its constructor when the directory is absent. So an **empty** `webapp/static/` took the "built" branch and raised out of `create_app()`: no API, no Settings page, no job queue, over a missing frontend the placeholder branch one line above already knows how to survive. Reachable because `vite build` sets `emptyOutDir` on `../webapp/static`, so **every build deletes that tree before writing it** — an interrupted build, a half-copied image layer, or (here) a pytest session overlapping one. Fixed by testing `index.html` rather than the directory, and mounting `/assets` only when it is there — nothing is lost, since the SPA catch-all already serves any file under the static root with the same resolved-path confinement. A complete build is served byte-for-byte as before. No config, schema, on-disk, endpoint, response-shape or default change. Tests +6, five fail before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.414.1** — FRIENDLINESS (PRIORITY 3, the ninth slice of the phone-invisible-Tooltip entry — the one *interactive* site the measurement said was worth doing): **asking what "Save as defaults" does no longer saves your defaults.** Its `<Tooltip>` wrapped the button, and its sentence is the only place the app says the button also drives *auto-stacking for this target* — so on a phone the one gesture available for "what does this do?" performed the persistent save. Now a `HintIcon` beside the button; label, action and accessible name untouched, hover unchanged. Frontend-only. Tests +1, fails before by saving. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.414.0** — FRIENDLINESS (PRIORITY 3, the eighth slice — the "still open" remainder of v0.413.0–2's own list, **shipped after a collision in which the other Builder's `HintAnchor` landed first and mine was dropped**; see `PROCESS-NOTES.md`, collision #14): **the last chips whose meaning a phone could not ask for** — `NightsCard` ×3, `Calibration` ×2, `BestPictures` ×2, `Gallery` ×1, converted to `HintAnchor` one line each, with `NightsCard`'s verdict badge skipping the anchor entirely when it has no sentence rather than passing `disabled` (an anchor makes its child a tab stop with `role="button"`). **Plus the durable half: a drift guard.** `hintAnchorDrift.test.ts` reads every non-test `.tsx` through `import.meta.glob` and fails if any `<Tooltip>`'s first child is a `<Badge>` — eight sweeps have each fixed the sites of the day and nothing stopped the next being written the old way, which is exactly how the badges survived four of them. Proven armed against a synthetic bad site *and* proven to have walked the tree. Frontend-only; `tsconfig.json` gains `"vite/client"` so the guard is typed. Tests +3. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.413.2** — PRIORITY 1/3 (the editor and the Target page), the seventh slice of the same entry and the one that carries a **bug**: **asking what "slower preview" means no longer adds the slow op.** `SlowPreviewChip` renders *inside* the Add menu's `Menu.Item`, so on a phone the only gesture for "what does this mean?" added the very op being warned about — the v0.402.1 defect one level out, and the same shape in `OpList`'s three row chips, where the tap selected the op. New opt-in `stopPropagation` on `HintAnchor` (off by default: swallowing a click a page expects is the worse failure). Also the Target page's `N integration` / **`N streaked`** / **`N trailed`** badges, each of which sits beside a bulk-reject button while what a streak *is* — and that Auto outlier removal keeps the frame — was hover-only. Eight sites. The frames table's column headings and the per-frame `Rejected — …` badge are deliberately left (the heading's tap *sorts*, and `FrameColumnGuide` already gives those sentences a reachable home; the reject badge's tooltip repeats its own text). Frontend-only; no config, schema, on-disk, endpoint, response-shape or default change. Tests +3, two fail before.
- **v0.413.1** — PRIORITY 3 (friendliness), the sixth slice of the same entry and the one that reaches the **most phone-critical page in the app**: **the Tonight page's planning verdicts now answer a tap.** You read Tonight standing next to the scope, in the dark, on a phone — and its score badge and four per-target chips (`readyHint`, `difficultyRowBadge`, `framingRowBadge`, `recentreNudgeRowBadge`) each printed a two-word verdict whose *reason* opened on `mouseenter` and on nothing else. Nine sites through `HintAnchor`: `routes/Tonight.tsx` ×5, `SuggestTargetsCard` ×2 (the Dashboard's copy of the same chips), `ContinueTonightCard`'s re-centre nudge, and `NextSessionCard`'s window line — whose hint is the honest **UTC** anchor behind the local wall-clock it prints, the same one its `.ics` carries. Four now-wrong "shown on hover" comments in `components/nextSession.ts` refreshed with it. Frontend-only; no config, schema, on-disk, endpoint, response-shape or default change. Tests +2, both fail before.
- **v0.413.0** — PRIORITY 3 (friendliness on the device the owner reads this app on), the fifth slice of the "a Tooltip is invisible on a phone" entry and the first to take its *other* half: **a stack card's verdict chips now explain themselves on a tap, not only on a hover.** Mantine's `Tooltip` ships `events={{ hover: true, focus: false, touch: false }}`, so of the app's 105 tooltips the **53 hanging off a non-control anchor** — a `Badge`, a `Text` — open on `mouseenter` and on nothing else: on a phone the sentence is not written at all. Enabling Mantine's `touch` is not the fix (floating-ui opens on `pointerenter` and closes on the `pointerleave` a lifted finger fires). New `components/HintAnchor.tsx` is the app's own controlled-tooltip affordance (`HintIcon`, v0.402.1) applied to an anchor with no behaviour to collide with; it **clones the child** rather than wrapping it, so no row moves and no page gets taller, and it keeps the site's own handlers and role. Applied to the eleven verdict chips of a stack card — `NoiseReadout`, `NoiseDelta`, `CleanestBadge`, `FocusChip` ×2, `CalibrationBadge`, `HazyNightBadge`, `PanelSeamsBadge`, `RejectionBadge`, `FrameCountBadge`'s thin-stack warning, and History's own *"what's this?"*, which is the sharpest case (two words that *invite* a question, answering only a hover). Hover is byte-for-byte what it was; keyboard users gain the hints for the first time. Frontend-only: no config, schema, on-disk, endpoint, response-shape or default change. Tests +9, three fail before.
- **v0.412.0** — AUTONOMY (PRIORITY 2, the 2026-07-25 backlog item, opt-in `astap_bootstrap_solve` path): **the faint-field rescue now anchors on a sub that already solved, instead of always re-solving a deep image.** The bootstrap engages when fewer than `min_frames` subs solved — a band that includes "a handful did" — and in that band it still built a deep image and asked ASTAP to solve *that*: a synthetic frame with no optics headers, on the field that had just defeated the solver sub by sub, while 1–7 real verified solutions of the same pointing sat unused in the DB. New `bootstrap.pick_solved_anchor` picks one (usable WCS by `wcs_text_is_usable`, same pixel shape as the members, star-richest first, at most `ANCHOR_LOAD_ATTEMPTS`=3 loaded since a load is a debayer) and the burst registers against it and takes its WCS — same phase-correlation shifts, same `propagate_wcs` CRPIX offsets, but no integration, no temp FITS, no extra ASTAP call and none of that call's failure risk. The deep-image path is untouched for the zero-solved case it was measured for, and for a target whose solved subs are unreadable or the wrong shape. The anchor is member 0 and every count below it (readability, registration, `n_members`, `n_registered`) counts only the **unsolved** members, so it cannot inflate the engagement gate; it is skipped in the propagation loop, because an already-solved sub is never touched. `BootstrapResult.anchored_on_solved_sub` / `bootstrap_anchored` say which path ran. Engine-only, additive, off-by-default path — no config, schema, on-disk, endpoint, response-shape or default change. Tests +5, four fail before, including a ground-truth CRPIX check with a deep solver that raises if it is called at all. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.411.1** — 🐛 BUG (trust / logging, found while writing v0.411.0 in the same block; reproduced by test): **a *successful* stack-then-solve bootstrap rescue logged itself as a failure.** `Project` has no `.name` attribute (the target's name lives in its meta table), and the bootstrap's credit line read it **inside** the block's own `except Exception` — so the one branch that fires when the bootstrap actually rescued subs raised, and the walk-away log said *"stack-then-solve bootstrap failed: 'Project' object has no attribute 'name'"* about a run that had just worked. The summary keys are written before the raise, so the Jobs page's rescue note was right all along — which is why nothing on screen ever disagreed. Fixed to `project.get_meta("name")`, the accessor the rest of the codebase uses. One line; no config, schema, on-disk, endpoint, response-shape or default change. Tests +1, fails before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.411.0** — AUTONOMY (PRIORITY 2/4, the 2026-07-23 backlog slice (c) of the v0.180.0 sibling-hint fill-in): **a second solve pass now reaches the subs a Seestar's own header hint kept blind.** v0.180.0 offers the solved siblings' centre at the tight `SIBLING_HINT_RADIUS_DEG` (5°) only to a frame with **no** header hint — and a Seestar writes `RA`/`DEC` into every sub, so on the owner's data that rescue never fires: each unsolved sub is searched blind-wide at 30° even after a dozen siblings pinned the pointing to within a degree, and an unlocated sub is silently left out of the stack. New pure `solve/runner.build_sibling_retry_arglist` re-offers **only this round's failures** around the now-known centre at the tight radius — a smaller *correct* search than the one that just failed, which is what the 2026-07-24 ASTAP measurement said moves the needle (~4 s failed at 30°, ~0.2 s at 5°); ASTAP still verifies the pattern, so it can only ever **add** solves. Bounded to one extra attempt and skipping the four cases it cannot help — a **setup** failure (no star database costs zero extra attempts), a **timeout** (already 3× the configured seconds, and it keeps its own "ran out of time" bucket), a job that **raised**, and a frame that already searched exactly there — plus standing down entirely when nothing has solved yet **or** when `use_solve_hints` is off (a blind solve was asked for, and this pass is nothing but a hint). `scanner.run_qc_and_solve` gains `retry_unsolved_with_sibling_hint=True`, running before the opt-in bootstrap so a real per-sub solve beats a propagated one. A rescued sub counts in `solve_ok`, so the Jobs page's existing "Located N of M" sentence improves with **no frontend change**; `solve_done`/`solve_total` stay the progress counters. Engine-only, additive — no config, schema, on-disk, endpoint, response-shape or default change. Tests +8, three fail before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.410.1** — 🐛 VERIFIED BUG (PRIORITY 1/3, the editor's preset chip and Adaptive-Auto's archetype routing; Builder-reproduced in both directions), **found by taking v0.410.0's bug class to the other cue `auto_recipe` consumes — exactly as v0.409.1 was found from v0.409.0**: **the same panel steps decided what your target *was*.** `classify_target` thresholds its geometry at `sky + max(0.06, 6·sky_sigma)` off a global level median; v0.409.1 made that blind to a *gradient*, and a mosaic's **steps** break it the same way and worse (a degree-2 surface barely touches a step). Measured on the four-panel scene, the identical stack with only the layout differing: `ext_frac` **0.0215 → 0.0030**, `star_share` **0.597 → 0.889**, verdict **`None` → star cluster at 0.89** (0.86–0.92 on four seeds); on the classify file's own star-field-with-nebulosity at residual steps of 0.024/−0.016/0.032, **cluster at 0.98**. It drives the editor's one-click preset chip and `auto_recipe`'s `object_type`, so a taste bias learned on one archetype could be spent on a stack the layout had renamed. **Same line, same place:** the geometry is read off `_detrended_luminance(_delevelled_luminance(lum, coverage))` — v0.410.0's de-stepper — while the **colour** cue still reads the untouched `arr`, so no threshold or floor moves. After: `None` on all four seeds, matching the single field. A coloured nebula, a galaxy and a cluster all keep their verdicts under the same steps and the same map (the nebula survives on v0.410.0's grain stand-down, not on luck). Wired at all three call sites via `editor._auto_measure_coverage`'s `is_mosaic` gate, so a single-field run reads no sibling and is classified exactly as today. Engine + one webapp gate, additive — no config, schema, on-disk, endpoint, response-shape or default change. Tests +3, **1 fails before**; three existing `classify_target` stubs gained the new keyword, assertions untouched. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.410.0** — 🐛 VERIFIED BUG (PRIORITY 1, the one-click editor path on the shape the owner actually shoots; Builder-reproduced against `origin/main`'s own `analyze_proxy`), **closing the residual v0.409.0 filed rather than guessed at**: **a mosaic's per-panel steps darkened the finished Auto picture — by steps Auto removes itself.** v0.409.0 made the sky *level* blind to a light-pollution gradient and said what it had not answered: panel offsets are **steps**, not a degree-2 surface, so the identical stack read **0.075** as a mosaic against **0.024** as a single field, `target_bg` **0.2100 vs 0.2304**, and the finished picture's sky came out **11.2 % darker** (p30 0.1687 vs 0.1899) — a property of the *layout*, not of the data. `auto_recipe` prepends `background.level_coverage` on every mosaic, so those steps are gone before `tone.stretch` sees a pixel: same mistake, other structure. New `presets._delevelled_luminance(lum, coverage)` removes them **the way the recipe does** — bin by the integer coverage value, shift each bin by its own robust sky median (`coverage_leveling`'s `rough_sky`, measured with that module's own `_robust_stats`), canvas median put back so the plane gets flatter and never brighter — and runs **before** `_detrended_luminance`, matching the recipe's own order. After: 0.0240 / 0.2304 / −1.1 % (same at seeds 5 and 21). **A measurement fix, not a threshold flip:** every constant untouched, σ still on the raw pixels. The map is asked for **only where the recipe carries the pass** (`is_mosaic` decides both, in one place), so a single-field stack's Auto is byte-for-byte what it was whatever map is handed in — pinned as recipe equality, and not merely conservative, since a single field gets no leveling pass to measure out. New `webapp/routers/editor._auto_measure_coverage` supplies it with the border trim's own precedence: the honest `_framecov.fits` frame count, falling back to the weighted map for older runs. A canvas the **object** fills is refused outright rather than flattened — each level's retained sample checked against 3× the image's own **grain**, measured structure-blind because on that very image a sigma-clipped canvas spread *is* the object (measured 0.24–0.36 across six scenes that are sky with an object on them, 5.1–12.5 across ones that are object). Correctly inert on the bundled samples (mosaic 0.00309 → 0.00312; field unchanged to five decimals even when handed its own map). Not over-claimed — two equally-deep panels are one bin here exactly as they are in the op, and there is a test named for it. Engine-only plus one webapp helper, additive: no config, schema, on-disk, endpoint, response-shape or default change. Tests +14 collected (11 engine, 3 webapp), **7 fail before**. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.409.1** — 🐛 VERIFIED BUG (PRIORITY 1/3, the editor's preset chip and Adaptive-Auto's archetype routing; Builder-reproduced in both directions), **found by taking v0.409.0's bug class to the other cue `auto_recipe` consumes**: **the same light-pollution gradient decided what your target *was*.** `classify_target` thresholds its geometry at `sky + max(0.06, 6·sky_sigma)` — a **global** level median plus the MAD of the levels beneath it, exactly the estimator v0.225.0 removed from `analyze_proxy` — so a tilt inflates the σ, the threshold climbs, and the faint diffuse half of the picture vanishes under it. Measured on a star-rich field with broad faint nebulosity at a 0.10 sky: `ext_frac` **0.0589 → 0.0010** and `star_share` **0.671 → 0.989** between tilt 0.02 and 0.05, turning "nothing clear" into **globular cluster at confidence 0.99** (1.00 at 0.08; same flip on three seeds of the other file's scene). And the other way: a real coloured nebula reads *nebula* at tilts 0/0.05/0.08 and is **lost entirely** at 0.15. It is read by the editor's one-click "try this preset?" chip and by `auto_recipe`'s `object_type`, so a taste bias learned on one archetype could be spent on a stack the tilt had renamed. **One line, same principle:** the geometry cues are read off `_detrended_luminance(lum)`; the **colour** cue still reads the untouched `arr` (`_extended_chroma` is scale-invariant by construction), so only the geometry moves and no threshold or floor changes. Every verdict on the file's gradient-free fixtures is byte-identical and all thirteen existing tests pass untouched. Engine-only, additive — no config, schema, on-disk, endpoint, response-shape or default change. Tests +3, **2 fail before**. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.409.0** — 🐛 VERIFIED BUG (PRIORITY 1, the one-click editor path, on by default; Builder-reproduced against `origin/main`'s own `analyze_proxy`): **a light-pollution gradient darkened the finished Auto picture — by a gradient Auto removes itself.** v0.225.0 made the sky *noise* structure-blind and never carried the same property to the **sky level** beside it, which stayed the median of the whole-image-normalized luminance and is the only input to Auto's stretch target (`0.24 - sky*0.4`). `background.final_gradient` is the recipe's **first** op, so the stretch's real input is the same picture whatever tilt the proxy carried — measured **0.1749 / 0.1751 / 0.1751** at gradients 0 / 0.03 / 0.08 — while Auto measured **0.047 / 0.195 / 0.357** of that stack, a 7.6× spread: it chose the goal for one image by measuring another. On the fixture this file's noise tests already ship, gradient 0.08 took the level 0.024 → 0.153, `target_bg` 0.230 → 0.179, and the **finished picture's sky 23 % darker** (p30 0.190 → 0.147). New `presets._detrended_luminance` reads the level off the plane with its frame-scale sky shape removed, via the same `bg/sky_poly.fit_sky_poly` both background passes detrend with (~40 ms, against 2.5 s to run the real gradient op) — subtracting only the *shape*, the surface's own median kept, so the plane gets flatter and never brighter. **A measurement fix, not a threshold flip:** every constant is untouched, and the σ stays measured on the raw pixels on purpose (its own estimator is already gradient-blind and its band is calibrated in those units; re-measuring it would move 0.007 → 0.023 and swing the denoise/sharpen crossfade on every image). Inert where there is nothing to fix: sky 0.0240 → 0.0240 synthetic, **0.00298 → 0.00298** on the bundled sample's real proxy, largest pixel changed 0.17 % of the image's robust range vs 13.6 % on the tilted one; declines wherever `fit_sky_poly` does. Engine-only, additive — no config, schema, on-disk, endpoint, response-shape or default change. A mosaic's panel *steps* are only partly answered (not a smooth surface) and are filed as the residual under "Bugs", not guessed at. Tests +8 collected, **6 fail before**. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.408.2** — 🐛🔴 VERIFIED BUG (wrong picture on a shipped feature the owner was actively looking at; MEASURED on his own file): **the Sun came back green and still meshed, because the video path debayered in the deep-sky path’s CFA phase.** v0.347.0 was right that a raw solar/planetary capture reaches the stack as an undebayered mosaic and wrong about *which pattern*: it took `RGGB` from `fits_loader.py` — where that name is the **fallback** for a `BAYERPAT` header the deep-sky path actually *reads* — and hard-coded it as `video/ffmpeg.CFA_PATTERN`. Video has no header, so it was an assumption. Measured on `2026-06-19-175558-Solar-RAW.avi`, the 2×2 sub-lattice means inside the disk are 40.7 / 10.2 / 131.7 / 40.7: the two **matched** values are the two green photosites and they sit on the **main** diagonal, where `RGGB` puts red and blue — here **13:1 apart**. Reproduced through the real `bilinear_debayer` from those four numbers alone: `RGGB` → R:G:B 40.7:**71.0**:40.7, **green**, mesh residual **40.50**; `GBRG` → **131.7**:40.7:10.2, red/orange, residual **0.00**. **Not fixed by swapping one guess for another:** new `ffmpeg.detect_cfa_pattern` reads the green *diagonal* off the stream’s first frame (the matched pair is green by construction), latched for the whole capture beside the existing "is this really a mosaic" decision, with `_CFA_DETECT_MIN_SPREAD_DN` / `_CFA_DETECT_MATCH_RATIO` falling back to the **measured** `GBRG` on a frame with nothing to read. R-vs-B stays the device fact the measurement establishes (a mosaic cannot distinguish `GBRG` from `GRBG`). **Second half, or the owner keeps the green Sun forever:** `colour_is_stale` short-circuited on `colour_current`, a boolean meaning "a build that knew about colour made this" — which v0.347.0 stamped True. It is now joined by an additive `colour_build` generation number (`_COLOUR_PIPELINE_BUILD`), so a still from the wrong-phase build is offered the re-stack, while an ordinary colour capture is re-probed once and never nagged. Alert copy follows (it said "grey"; those stills are green). **CFA phase and frame orientation are one coupled invariant** — `RGGB` row-flipped *is* `GBRG`, which is why AVI’s bottom-up storage split the two paths — pinned by `test_the_two_patterns_are_one_row_flip_apart` so neither constant can move alone. Additive/upgrade-safe: an old `meta.json` reads as generation 0 (tested); no config, schema, on-disk, endpoint or response-shape change. Tests +11 collected (7 engine, incl. one parametrized ×2; 4 webapp), five failing before on behaviour. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.408.1** — 🐛 VERIFIED BUG (image quality / autonomy, PRIORITY 2/4; Builder-reproduced against `origin/main`'s own `grade_frames`): **a mosaic panel too thin to be its own population was graded against the whole target and condemned wholesale as "likely cloud".** v0.270.2 made the flux-like metrics per-panel; a panel below `MIN_FRAMES_FOR_GRADING` (10) is not a population, so `pointing_groups` labels it `-1` and its frames fell back to the target-wide yardstick — the very reading the split exists to refuse — and because a thin panel's subs are alike it flags **all** of them. Measured on 3×12 healthy panels plus a 6-sub panel at a star-poor pointing with a **perfectly normal sky level and star flux**: **6 of 6 rejected, on `star_count` alone**, reason *"far fewer stars than typical (120 vs 404) — likely cloud"* — verbatim the sentence AGENTS.md §1 quotes as the v0.270.2 bug. This is the owner's shape (the bundled mosaic sample is 6/6/6/**3**; a panel cut short by cloud is thin by definition). **The fix is narrow, and physical rather than statistical: cloud raises the sky level, a different pointing does not.** Over one mosaic's few degrees `sky_adu_median` is a property of the *night*, while star count and median star flux are properties of *what you framed* — so a new `_MetricSpec.pointing_scale` marks those two only, and they may never borrow another panel's population (a frame with no yardstick of its own is left ungraded on them). `sky_adu_median` keeps its target-wide fallback, which is what the existing `test_a_panel_too_thin_to_grade_falls_back_to_the_whole_target` clouded panel actually trips — **no test weakened**; that test now also asserts the reason set is exactly `{"sky_adu_median"}`. Post-fix: star-poor thin panel **0 of 6** flagged, merely-fainter 0 of 6, genuinely clouded still **6 of 6** on the sky level alone. A panel with its own population still grades on every metric; a single-pointing target is untouched; `bulk_select` already used this pattern. Engine-only, additive — no config, schema, on-disk, API-shape or default change. Tests +5, three failing before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.408.0** — 🐛 VERIFIED BUG (image quality / trust, PRIORITY 2/4; Builder-reproduced against `origin/main`'s own function): **the streak guard's position half anchored on ONE median, so a mosaic whose panels each carry the extended object rescued NOTHING — a second stationary object made the detector strictly worse than one.** `qc/runner.stationary_streak_frames` is what gives back the subs a shape-only Hough detector wrongly calls trails when a bright elongated object (edge-on galaxy, elongated nebula) trips it on essentially every sub; the fraction tiers above it cannot see a minority-flagged object at all. It asked "are the flagged components at *this* one place?" of the median of the whole flagged set — right on a single field, and on a **mosaic** (§1: the owner is a heavy mosaic user) the panels point at different sky, so one object spanning the mosaic lands at a *different* place in each panel's frames and the median falls **between** the clusters, within `STATIONARY_CLUSTER_RADIUS` of nothing. Measured on main's function verbatim: one panel of 8 → 8 rescued; **two panels of 8 → 0**; a 2×2 of 6 → 0; two panels of 60 (the owner's scale) → **0**. Every one of those subs stays out of the stack, silently, on the by-default path. Now the clusters are **found, not assumed**: each candidate centre re-centres on the median of its own neighbours (so an accepted set is still the same median-centred one), the largest qualifying cluster is taken and removed, repeating up to `STATIONARY_MAX_CLUSTERS` (16, largest-first — a work bound above any Seestar mosaic's panel count). A set holding exactly one cluster is byte-for-byte the old answer, and all 21 existing tests pass unchanged. **The price of searching is paid explicitly:** asking once per candidate instead of once turns the radius's own coincidence budget into an event (measured: 20 scattered trails threw a chance four in 13 % of sets), so each cluster is scored against the null that describes real trails — Poisson within the radius, multiplied by the centres tried (`_chance_cluster_p`, `STATIONARY_CLUSTER_MAX_P = 0.05`) — re-measured at **2 false verdicts in 1,800 scattered sets (0.1 %)** while a 60-per-panel mosaic cluster sails through. Vectorised and memoised on the re-centred centre: 0.37 s for 3,000 flagged frames. Contract unchanged (un-reject-only, per frame, never a user override, no verdict without a position and a date); engine-only and additive — no config, schema, on-disk, API-shape or default change, and nothing about *what* is flagged moved. Tests +8, every multi-cluster one failing before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.407.1** — 🐛 BUG (friendliness / trust, PRIORITY 3), Builder-verified by reproduction on the running app (`agent-dogfood.sh --build --mosaic --editor`, step 4c): **the panel map and the health panel gave opposite instructions about the same panel of the same run.** Printed one line under the other on the bundled mosaic sample: the map's *"It's only a few minutes' difference at this stage, so it evens out on its own as you keep shooting"*, and `grain_uneven`'s *"another night on that panel is what evens it out"*. The map asks two questions of a thin panel — thinner by `THIN_FRACTION`, **and** behind by `THIN_MIN_SHORTFALL_S` (300 s, whose docstring exists to "stop a brand-new mosaic from being nagged about noise in its first half hour"); the grain note asked neither, firing on `grain_ratio ≥ 1.25` alone. **A depth cannot answer the second question**: 3 subs against 6 reads 1.4× grainier whether it is 30 s or 3 h behind (1/√2 either way), and the small case genuinely closes itself — ten more minutes on every panel takes 30 s vs 60 s to a grain ratio of 1.02. So the note was sending a beginner out for a targeted night to recover half a minute. `stack_health` now converts the shortfall to *time* (`(deep − thin) × median accepted sub exposure`, new `_median_sub_exposure` mirroring `recommended_dark_spec`) and reads it against the **imported** `mosaicmap.THIN_MIN_SHORTFALL_S` — one threshold, not a second opinion — keeping the whole measurement and swapping only the closing clause, quoted through the map's own `format_duration` and ending in the map's own words. Exactly the shape v0.406.2 gave the map's `behind` branch. At or above the threshold the sentence is byte-for-byte what it was (pinned whole, not by substring); `grain_verdict` untouched, so v0.406.1's `PanelSeamsBadge` tooltip is unaffected; `action` still `None`; no threshold, column, schema, config, API-shape or default change; an unrecorded sub exposure keeps today's wording. Tests +7 collected (three new cases plus a four-case parametrize), three fail-before, including a parametrized **agreement** pin that runs `mosaic_depth_map` and `stack_health` on the same mosaic at four shortfalls and asserts "go and shoot that panel" is said by both surfaces or by neither. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.407.0** — NEW BEGINNER FEATURE, PRIORITY 3 (enjoy / share / understand), the Scout's 2026-09-09 "shareable labelled picture" filed the same day: **the names of what's in your picture can now be downloaded on their own.** The entry asked for a new `annotate_render.py` and an `annotated.jpg` endpoint; **a grep found the whole engine half already shipped** — `seestack/objectlabels.py` (v0.293.0: `place_labels` as pure fraction geometry, `draw_object_labels` for the budget and deconfliction, `MARK_RGB`/`HALO_RGB` shared with `skymarks` so both overlays read as one set), baked by `png_bytes_to_jpeg` and reached by `download_stack_run`'s `label_objects=true`, crop- and North-up-aware via `_object_labels_for_run`, saved as `_labelled.jpg`, covered by seventeen cases in `tests/webapp/test_share_object_labels.py`. What was missing was the **download**: the only caller that ever set the flag was *"Share the keepsake"*, which sets it together with `keepsake` and `scale` — so the names could leave the app only wrapped in the matte, the caption and the scale bar, while the Target hero's own *"What’s in it?"* answer vanished the moment the picture was saved. `SavePictureMenu` now offers **"With object names"** beside *"With scale & compass"*, asking for `label_objects` and deliberately **not** `scale` (two downloads, not one item growing a second flag), following the page's North-up toggle and degrading to the plain picture on an unsolved run exactly as its sibling does. Frontend-only; no config, schema, on-disk, default, endpoint or response-shape change. Tests +4 assertions inside two existing cases (no new `it()`, so the frontend count stays 3,550), both failing before; the href is pinned three ways because `label_objects` is the last of five positional booleans. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.406.2** — 🐛 BUG (trust / friendliness, PRIORITY 2–3; Builder-verified by reproduction on the `--mosaic` sample): **the mosaic panel map dropped the thin panel and then reassured the owner that nothing was being held back.** `mosaic_depth_map` discards every `pointing_groups(min_members=`MIN_PANEL_FRAMES`=5)` cluster labelled `-1` — right for *strays*, wrong for a panel that is thin **because it is thin** — so on the 6/6/6/**3**-sub sample it drew a **hole exactly where the grain is** and wrote *"All 3 panels of your 2×2 mosaic … no part of the picture is being held back"* over it, while `stack_health` on the same run said 23 % of the picture was 1.4× grainier (and `stackhealth.py` justifies that note's `action=None` with "the panel map already says which panel is behind"). New `_thin_panels_on_the_grid` + `_axis_lines` give the dropped clusters **one** more hearing against the *geometry*: admitted only on an existing row line **and** column line, into an **empty** cell — so a stray (not on a grid line) stays out, a thin cluster can never *extend* the grid, and no panel that exists today moves a single figure. `_verdict_text` also stops calling a grid "2×2" unless the panels fill it, and gains a third branch so a mosaic that is thinner by the fraction but only minutes behind stops being called "similar" under a visibly paler cell — still with no highlight, no `aim_hint` and no nag. `THIN_MIN_SHORTFALL_S` deliberately untouched. Engine-only, additive. Tests +7, two fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.406.1** — 🐛 same bug, the two surfaces v0.406.0 left: **the History / Gallery / Compare `PanelSeamsBadge` tooltip still promised *"you shouldn't see seams between them"*** on a mosaic showing a grainier rectangle. `seamsLabel(verdict, grain)` now reads both verdicts and says *"…where the picture looks grainier that's a difference in depth (fewer subs on that panel), not a step in the sky"*; the chip stays green, keeps "Panels even", and a `"check"` verdict is untouched. `grain_verdict` rides on `StackRunOut`/`GalleryItem` as an additive optional field from the same shared `stackhealth.grain_verdict`, read off the column so neither listing opens a file. An older backend omitting it gives today's tooltip character-for-character (pinned). Tests +6. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.406.0** — 🐛 BUG + NEW MEASUREMENT (trust / friendliness, PRIORITY 3; found by measuring a `--mosaic` dogfood pass's pixels, which the pass itself reported CLEAN): **a mosaic can be perfectly levelled and still show an obvious rectangle, and the app said it couldn't.** On the mosaic sample (4 panels, 6/6/6/3 subs — §1's shape) the finished picture shows a visibly grainier quadrant over **23 %** of the canvas, while `seam_residual` reads **0.70** → *"the sky matches across the joins, so **you shouldn't see seams between them**"*, and the same panel praises the run for **"even coverage"**. Both statements were true and both were answering the wrong question: a panel differs from its neighbours in **level** (0.478 ADU here, **0.09× the grain** — levelling worked) or in **grain** (σ **7.79 vs 5.20 = 1.43×** — nobody measured it). New `measure_coverage_grain` compares each substantial coverage level **below the modal one** against the mode — anchoring on the *deepest* level would fire on every mosaic ever shot, since overlap strips are always deeper — and stamps `GRAINRAT/THN/DEP/SHR` plus four additive `stack_runs` columns. `stackhealth` now says *"about 23% of the picture has 3 subs on it where most of it has 6, so that part looks about 1.4× grainier … another night on that panel is what evens it out"*, with `action=None` because there is no in-app fix, and the two over-claims stand down (nothing removed — the flat note still says the panels evened out). σ is **sigma-clipped, not adjacent-difference**, so the same number survives the decimated read `backfill_coverage_grain` heals an existing library from — no re-stack needed. No `SCHEMA_VERSION` bump (rollback-safe), no frontend change. Tests +24, one fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.405.1** — 🐛 BUG (friendliness / trust, PRIORITY 1 editor), found by *looking at* a `--mosaic --editor` dogfood pass rather than by reading its exit code: **the editor told a mosaic's owner to "shoot it in mosaic mode".** The Target page says *"It's bigger than **this mosaic** — only about 55% of it is in this picture. Adding more panels next session would capture the rest."*; the editor of that same run said *"is bigger than the Seestar's single frame — shoot it in mosaic mode to capture all of it."* — the pre-capture *catalogue prediction*, which cannot know what was shot. `ObjectInfoCard.hideFraming` and its own docstring have carried the rule since the measured verdict shipped (*"on a page carrying both, the prediction is the copy to drop"*); Target passes it and History renders no card, so **the editor was the third surface nobody listed**. It now reads the verdict through the shared `useStackFraming(safe, rid)` — the query key the editor was *already* fetching for its re-centre offer, so **no new request** — passes `hideFraming`, and renders `FramingVerdictNote` for the run it is editing. Where nothing measured the picture the verdict self-hides and the catalogue line stays exactly as it was: nothing removed, single-field editors unchanged. Frontend-only. Tests +2 (1 fails before). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.405.0** — NEW BEGINNER FEATURE, PRIORITY 2–3 (autonomy / friendliness): **the Dashboard now says which targets you've shot more of since their picture was made.** The per-target *"N new subs since your last stack"* nudge has existed since v0.90.0, but with `auto_stack` off and a target per object across many nights, the question after a night's capture is *which* target to open — and the only surface that knew was the one you had to open to find out. New `GET /api/new-subs-waiting` + `NewSubsWaitingNote` answer it library-wide, on the Dashboard's existing `NoticeBoard` at `advisory` priority, self-hiding at zero. **One definition, two surfaces:** accepted **and** plate-solved subs dated after the newest *genuine* run (`run_has_reusable_options` — the Target page's own `reusable` flag), pinned by a test that re-derives the Target page's number from the payloads that page reads. Cheap by construction: per target one `stack_runs` read that stops at the newest genuine row, then one indexed `COUNT` (`Project.count_accepted_solved_after`); a never-stacked target is skipped. **It offers and never acts** — no batch button (re-stacking is hours of CPU on a NAS); each target links to its own Stack form. Additive/upgrade-safe. Tests +18. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.404.0** — NEW BEGINNER FEATURE, PRIORITY 2 (autonomy) — Builder-found while reading the owner's one-sitting list: **the app finally mentions the one switch the whole walk-away path waits on.** `auto_stack` has shipped **on** since v0.391.0 but reaches only *fresh* installs (a box that has ever run carries an explicit `"auto_stack": false` no upgrade may overwrite, §9) — so on the owner's install the entire "drop your subs in and come back to a picture" chain sits behind a Settings switch **nothing in the app had ever mentioned**, while every morning it ingested, QC'd and located a night and made nothing of it. One self-hiding `AutoStackOffNote` in the Dashboard's existing `NoticeBoard` now says so and offers the switch; one click PUTs `{auto_stack: true}` (a *patch* — nothing else in the config moves) and the note is replaced by what happens next, not merely gone. Silent unless it would be true: settings unknown or on, a picture *was* made in the window, or no single target kept enough subs to clear `auto_stack_min_frames` (judged **per target** — four targets of two subs is eight subs and still no picture). It promises the *behaviour*, never the outcome, because the recap counts **kept** subs and auto-stack counts **located** ones. **A browser moved it:** the first draft lived in `LastNightCard`, passed every jsdom assertion, and rendered **hidden** at 420 px — that card sits in the `InsightTabs` "Recent" panel, `display: none` until clicked. Verified in a real browser end to end (above the fold at 420 px, one click really flips the real server, gone after reload; +238 px, only where it applies). Frontend-only; tests +18. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.403.1** — PRIORITY 1 (editor) test infra: **one-click Auto's preview is now measured against its own export end to end, on a mosaic.** `test_edit_proxy_parity.py` measures the A2 class one op at a time; nothing rendered the eleven-op recipe Auto actually builds, where an op can scale its own parameter correctly and still be handed a differently-*fitted* input. `tests/test_auto_recipe_proxy_parity.py` builds the recipe from the proxy (as the editor does), renders it on the proxy at `proxy_scale=5` **and** natively, and compares the two as pictures. **Measured: worst statistic 0.0034** (and 0.0043 at step 4, 0.0076 at step 8 on larger strips scoped-and-recorded rather than run every time) — inside the ~2 % decimation floor it asserts. **The trap is armed on every run:** patching `EditContext.scaled_px` to the identity *is* the A2 defect and moves the same number to **0.1085**, a 32× separation, so the passing test is a gate rather than a tautology. Fixture states its own shape via `tests/shapes.py` — and `assert_reference_is_the_thinnest_panel`, not `assert_panels_thinner_than_the_reference`, which the first draft got wrong and `shapes.py` caught. Test-only; +4. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.403.0** — NEW BEGINNER FEATURE, PRIORITY 2–3 (autonomy / friendliness), the “in-UI destination target picker” residue of the 2026-07 bulk-upload block (slice (c), open since v0.115.0): **the upload box knows which targets you already have — and says so before the two mistakes that live in a blank one.** Typing `M31` when the library holds *M 31* splits an object across two thinner stacks; worse, typing the target's own name lands the subs in the bare `M 31/` beside `M 31_sub/`, which `scanner._apply_seestar_convention` skips as the Seestar's *own* finished picture — so the upload succeeds and nothing ingests. The field is now an `Autocomplete` of the folders that already hold subs, with one sentence under it saying what the typed name will do and a one-click fix where there is exactly one right answer. **The folder is read, never reconstructed**: new pure `Project.source_folders_under(prefix)` groups the `frames` rows by the directory their `source_path` sits in, so nothing under `incoming/` is walked, opened or `stat`ed (AGENTS.md §10, trap armed *and proven armed* in a test) — and it reports the **whole** relative folder, because a test caught the first version collapsing `MyWorks/M 31_sub` to `MyWorks`, which reads exactly like a folder you could upload into. The skip warning compares **exactly**, like the scanner does (a `_mosaic_sub` sibling does *not* trigger the skip, and a test pins that the copy does not claim it); only the “did you mean” nudge folds case and spaces. Withheld for a folder drop or a `.zip`, where the typed name is a *parent* and `folderPreserveNote` already says the true thing. A 420 px browser pass found the fix button clipped to `Use “N` and the row wraps now. Additive: one read-only endpoint, no config/schema/on-disk/API-shape/default change; no destinations ⇒ exactly the old behaviour, which is its own test. Tests +37 (16 Python, 21 frontend), including a scanner-constants drift guard TypeScript cannot import. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.402.1** — 🐛 BUG (friendliness / trust, PRIORITY 3), Builder-found by enumeration while shipping v0.402.0: **five controls in the app answered "what does this do?" by doing it.** Wherever a `<Tooltip>` is wrapped around a `Switch` or a `SegmentedControl`, the only gesture a phone has is the one that operates the control — so the editor's `Auto-crop edges` switch (whose sentence is the only place the library-wide default is named), the Jobs page's `Notify me when done` switch (whose tap also fires the browser permission prompt) and the Gallery's three filters (including the sort whose hint is the only place that page explains its σ) each hid their explanation behind the act of using them. This is v0.374.11's defect one level up, and the sweep is exhaustive: those five are every such site in the frontend. `HintIcon` — the icon half of `HintLabel`, lifted out so `HintLabel` renders it unchanged — now sits *beside* each control, which also leaves the control's own accessible name alone. Hover and keyboard focus still work; no page gets taller; nothing removed. Tests +10, four of them fail-before regressions at the three routes asserting the words appear *and* the control did not move. Full entry under the tooltip idea above.
- **v0.402.0** — PRIORITY 1 (editor) × PRIORITY 3 (friendliness), the third slice of the "a tooltip is invisible on the device the owner reads this app on" entry: **the editor's preview toolbar now explains itself in text.** Four of the eight buttons directly under the picture (`Coverage`, `Star mask`, `Drag to crop`, `Split`) carried a plain-language sentence each and carried it *only* as a hover `Tooltip` — and a tap on one of those buttons runs it, so on a phone the one gesture available spends the question on the answer. New `PreviewToolGuide` disclosure (*"What do these buttons do? →"*), built from the same `PREVIEW_TOOLS` array the tooltips now take their labels from, and shown for exactly the tools `visiblePreviewTools({isMosaic, cropDrag})` says are on the screen. `Compare` gains the sentence it never had (it is `Split`'s twin and its label never says what it compares against). Measured with `agent-dogfood.sh --build --mosaic --editor`: editor at 420 px **3,047 → 3,072 px** closed, nothing overflowing, no console errors. Tooltips unchanged for anyone with a mouse; nothing removed. Tests +12, two fail-before. Full entry under the tooltip idea above.
- **v0.401.1** — PRIORITY 3 (friendliness), found by **running** the app right after shipping v0.401.0 and invisible to every code read of it: **the new field-fill diagram's overflow case could not be read.** On that branch the card suddenly shows *two* shapes, the object covers the frame, and the caption said "the outline" — which names neither. Two fixes: `FieldFillDiagram` now paints the `ellipse` **before** the `rect` (SVG paints in document order, and a dashed grey edge under a translucent indigo wash reads as a smudge, not as the edge of your field), and `field_fill`'s overflow text names the frame — *"Bigger than one frame — it spills over the dashed edge of your field."* Both pinned by tests. The geometry was already correct and measured so off the screenshot's own pixels; the defect was purely "which shape am I looking at?", which is not a question that occurs to you while writing the shapes. Dogfood record and the generalisation in [`PROCESS-NOTES.md`](PROCESS-NOTES.md) (2026-09-09).
- **v0.401.0** — NEW BEGINNER FEATURE, PRIORITY 2–3 (plan/understand), the Scout's 2026-09-09 idea filed the same day: **the "will it fit?" sentence gets a picture.** The identity card now draws the object to scale inside one frame, under the sentence it illustrates — because "fits comfortably in a single Seestar frame" is true of a nebula filling two thirds of the frame *and* of a planetary that is a dot in the middle of it, and those are different shots to plan (a test pins that pair: 3′ and 70′ through an S30 field, both `fits`, one captioned "expect to crop in close"). New pure `seestack.framing.field_fill` returns the object's axes as fractions of the frame's edges plus the field's own edges and one sentence; `objectinfo._to_info` fills it from the **same** catalogue size, the same square-box convention for a missing minor axis and the same *derived* field `framing_hint` and `mosaic_plan` already read, so the picture and the words cannot disagree. Three decisions worth keeping: the fractions are **not clamped** (`fieldFillGeometry` grows its `viewBox` instead, so an overflowing object is drawn whole outside the dashed frame — clipping it would hide the one thing the picture exists to show); the **field travels in the payload** rather than being re-derived in the frontend, pinned on both the derived-S30 and S50-fallback paths; and `_fill_pct` rounds to fives only above 20 %, because the app's usual idiom turns a 3 % object into "5 %" and a 0.2 % one into "0 % of the width". Additive: one optional response field, one optional engine dataclass, one component; `hideFraming` hides the drawing with the sentence, and an older backend draws nothing. Tests +24. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **CLOSED, not built (no version)** — the 2026-08-30 idea *"a corner target can't be centred in its own zoom clip"*: **the observation is right and the fix it names is backwards.** It asked for the largest zoom in [1.3×, 1.8×] at which the focus can be the crop's true centre — "a **gentler** push-in that genuinely lands on it" — but the crop is `W/s` wide, so centring on `cx` needs `W/(2s) ≤ min(cx, W−cx)`: the further out the object, the **more** zoom, not less. Measured on `crop_box_for_scale` itself at W=1000: today's 1.8× already lands exactly on anything inside [0.278 W, 0.722 W]; 0.90 W needs 5×, and the entry's own 0.96 W case needs **12.5×** — an 80 px crop blown up to the clip's 640 px edge, the 3.5× upscale `zoom_clip_size`'s never-upsample rule exists to prevent. So the bounded-zoom shape is closed; reopening it needs a different idea (re-aim the whole move, or accept a margin). Table and reasoning in [`SHIPPED.md`](SHIPPED.md).
- **v0.400.1** — 🐛 BUG (trust / share, PRIORITY 3), Builder-verified by reproduction while wiring v0.400.0: **v0.384.0's "your Process-target picture now shares off the master" did not reach the owner's main path, because Auto trims the border.** An auto-edit records a `preview_crop_json`, and `_native_picture_source` declined outright on *any* recorded crop — so the JPEG, keepsake, scale-&-compass, all three wallpapers and the zoom clip of every auto-edited picture were still re-encodes of the 1024 px preview. `auto_crop_border` is on by default, so this is what a "Process target" run *is*, not an edge case. The decline's stated reason ("the render is of the whole canvas") is true for a **linear** run and false for a display-space one: Auto's trim is a `geometry.crop` op **inside the very recipe** `render_run_full_res_png` replays, expressed in fractions, so the render reproduces the same rectangle of sky. `_render_reproduces_the_crop` now allows exactly that case — display-space, a saved recipe, and `preview_crop_of_recipe` (the same function that *recorded* the value, so they cannot drift) equal to it; `UNKNOWN` or any disagreement stays a no, because a big wrongly-framed picture is worse than a small honest one — and `_visible_canvas` makes the sizing decisions against the rectangle the render actually hands back. Nothing downstream needed changing, checked rather than assumed: `wallpaper_target_pixel` shifts into the cropped rectangle *before* rescaling, and the scale bar's `fraction` is already a fraction of the cropped canvas. Measured: the share JPEG goes **400×400 → 1280×1280** on a 1600² canvas trimmed to 80 %, same framing (max 12/255 against the same scene served the old way). Tests +4, two fail-before, including two that pin the *unchanged* declines; nothing loosened. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.400.0** — PRIORITY 3 (enjoy / share), the last open **size** item of the 2026-08-30 download-copy sweep: **the zoom clip stops being a 1024 px preview blown into a share.** It was cut out of `run.preview_path`, and because `zoom_clip_size` never upsamples that cap did not soften the clip, it *sized* it — `CLIP_LONG_EDGE` is 640 and the clip came out at `1024 / CLIP_ZOOM` = **569 px**, deepest frame the preview at 1:1, with `…/zoom-clip/info` reporting that smaller number as if it were the ask. `_zoom_clip_source` now cuts it from the **same cached share render every other hand-out already uses** (`_native_picture_source`, which declines on exactly the cases where a re-render would be a different picture — baked North-up, display-space with no recipe, a trimmed preview, no master, a canvas no bigger than the preview) and falls back to the stored bytes otherwise, so an ordinary run is byte-for-byte the clip it was. Focus re-measured against whichever bytes win, as the wallpaper already does. Size asked for is `min(_share_source_long_edge, 2 × zoom_clip_min_source_long_edge())`: past 1152 the output stops growing and the extra pixels are **supersampling**, which is worth having but is paid 24 times over (the move is 24 crop-and-resize passes) — so `ZOOM_CLIP_SOURCE_OVERSAMPLE = 2` takes the 2×2 average and stops, and **no render happens that the share JPEG and wallpaper were not already paying for**. The cache grew with the source (`_zoom_clip_signature` now carries the master stamp, the recipe hash and the app version; tag `v1`→`v2`, so cached clips rebuild). `info` cannot drift from the file by construction: `_native_picture_source`'s cheap gates are now `_native_picture_gate`, which it *is* plus the render, and `_native_picture_size` reads the size through the same gate — pinned by decoding the served animation, not by comparing strings. Measured: 222×167 → **640×480** on a 1600×1200 canvas with a 400 px preview, and >1.5× the high-frequency energy in the deepest frame against the same scene served the old way, compared at one size. Tests +4, three fail-before; nothing loosened. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.399.3 + v0.399.4** — 🐛 BUG (image-quality, PRIORITY 1), **D1's fourth instalment, closed**: **Auto's on-by-default border trim no longer crops a *fully tiled* mosaic** — up to 19.8 % of a canvas with no ragged edge anywhere, silently, on the owner's 3x3–12x8 shooting shape. v0.391.1's coverage bound could not reach it: on a fully tiled canvas that bound is **1.0 by definition**, so a rectangle keeping 0.80–0.91 cleared `TRIM_KEEP_RATIO` and was accepted. The discriminator is spatial and is two facts rather than a tuned number — `_outline_mask` says where the data *runs out* (uncovered pixels, plus the nearly-empty band along the union outline, since a bounding-box canvas often has no NaN at all), and `_thin_labels` says a ramp is a **band** while a panel is a **block** (nowhere thicker than a quarter of its own longest extent — ~0.02 for a ramp, ~1.0 for a panel, at any canvas size). `_border_trim_rect` then removes only what is *attached* to that outline and is itself a band; everything else a depth threshold calls poor is a panel, wherever it sits. It is a **second** answer and the more generous of it and the depth ladder wins, so it can only ever keep more — pinned as a property, and true of every one of the 441 measured maps. v0.399.4 then feeds it the **frame count** (`_framecov.fits`) instead of the sum of per-frame weights, falling back to the weighted map for runs that have no sibling; that was lever (b) of the filed entry, "arguably the more honest input" that "could ride along with a real one". Measured over 147 rasters × 3 outline shapes, as how many keep under 95 % of what their own coverage allows: on the frame-count map **4 / 0 / 34 → 0 / 0 / 0**, worst case 1.000 in all three; on the weighted map 13 / 14 / 39 → 4 / 4 / 10. Tests +4 engine / +2 webapp, all fail-before; `well_covered_mask` (the all-sky map, the sky-area tally) untouched. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.399.2** — 🐛 BUG (image-quality/trust, PRIORITY 3–4), Builder-verified by reproduction: **a mosaic panel that is merely thinner than its neighbours is no longer faded off the all-sky map, or left out of the "how much sky have I photographed?" tally.** `well_covered_mask` asks `panel_coverage_level` which coverage level counts as "one panel", and *substantial* there is 8 % of the canvas — one panel of a **twelve**-panel mosaic. On the owner's 5x5/10x10/12x8 rasters a panel is 1–4 %, so the search walks past every thin panel and settles near the **mode** of the depth distribution; everything below half of that is called fringe. Measured on the integer frame-count maps this path actually reads: **90 of 147 fully tiled rasters fade something, the worst 26.3 % of a canvas covered edge to edge** — and because `seestack.skyarea` counts the same mask, the owner's photographed-sky figure was short by the same fraction (7.0 % on the 6x4 regression). The trim had a second line of defence (v0.391.1's coverage bound); a per-pixel mask has no rectangle to compare against, so its only lever is the reference — hence a mask-only `MASK_LEVEL_MIN_FRAC` (0.03), leaving `largest_covered_rect` bit-for-bit unchanged. **0 of 147 after**, while every honest fade survives to the digit (a single field's dither ramp 2.50 % before *and* after, a ragged 2x2 8.17 % likewise; a raster that is both many-panelled and ragged still loses its border, 11.2 %). Safe by construction: `panel_coverage_level` is monotone in that fraction, so the reference can only fall and the mask can only grow. Tests +6, three fail-before. **The same run verified and filed D1's fourth instalment** — the trim still cropped fully tiled rasters by up to 19.8 %, with five candidate fixes measured and rejected; *closed in v0.399.3/v0.399.4 above, entry in [`SHIPPED.md`](SHIPPED.md)*. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.399.1** — 🐛 BUG (broken-UX/trust, PRIORITY 1–2), found by **running** the app during the v0.399.0 live check: **the Stack form named the outlier method the run would *not* use, on a mosaic.** `/stack-estimate`'s `auto_reject_resolved.method` re-derived the answer from the target's *frame count* while the engine's `_resolve_auto_reject` sizes it from the mosaic's **per-pixel panel depth** — reproduced on the 2×2 sample: 21 subs, depth 3, endpoint said `sigma_clip`, the run that had just finished recorded min/max. The A6 class (v0.326.7) surviving in the reporting path, on the owner's dominant shape. Not just a sentence: `Stack.tsx` drives `sigmaClipEffective`/`minMaxEffective` off this field, so the form greyed the wrong toggle and coached about the wrong method. Fixed by reading the method off the **resolved** options the endpoint already computes (one definition, cannot drift), plus an additive `panel_depth` so the copy can give the reason; `autoRejectMethodNote` extracted to `frontend/src/autoRejectNote.ts` with a depth voice, frame wording byte-for-byte unchanged wherever depth says nothing new. Tests +9, three fail before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **CLOSED, not built (no version)** — Performance: **`GET /api/gallery/best` does not need the cache the 2026-08-04 entry proposed.** That entry set its own gate ("time the endpoint on a realistic library first"); measured at **97 ms** on 40 targets × 20 runs and **235 ms** on 80 × 40 — under CPU contention, so upper bounds — i.e. the same band as `/api/gallery` beside it and two orders off the 13.8 s endpoints that justified v0.374.7–v0.374.9. A cache would buy ~0.1–0.25 s twice per Dashboard path and pay in staleness on the one wall whose point is "the picture I pinned". Entry, numbers and the safe shape if it is ever reopened are in [`SHIPPED.md`](SHIPPED.md).
- **v0.399.0** — NEW BEGINNER FEATURE, PRIORITY 2–3 (autonomy/friendliness): **the Stack form says about how long the run will take.** The Jobs page could say how much longer a *running* stack had to go; nothing answered "start it now or in the morning?" before the button, next to the size and the memory verdict the same panel already gives. Measured, never modelled: new additive `stack_runs.duration_s` stamped by `run_stack` — added **without** a `SCHEMA_VERSION` bump, through `_reconcile_table_columns`, because a bump would make an older build refuse to open the DB (a red rollback test said so) — and new `seestack/stacktime.py` takes the **median seconds-per-sub of this target's own comparable past runs**. "Comparable" is strict on purpose — same `stack_cost_class` (which *is* `stacker.combine_method` plus the two-pass-drizzle split, asserted equal to it in a test, so the two cannot drift), canvas within ×2, and at least 8 subs — and it returns nothing at all on a first stack, on unseen settings, and on every library the moment it upgrades. `/stack-estimate` resolves `auto_reject` through the engine's own picker before matching, so a run about to combine with min/max is not timed from κ-σ history. The wording says what it stands on ("from your last 2 stacks of this target") and softens to *Roughly* on a ×4 extrapolation, formatted through the running job's own `formatEtaSeconds`. Tests +35. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.398.1** — PRIORITY 3 (friendliness), the Scout's 2026-08-26 #3 entry that v0.272.1 left open: **the Lucky-imaging knob is typed as the percent the finished picture is badged with.** It asked a beginner for 0.05–1.0 while the Gallery says "Lucky 50%". New optional `StackOptionField.unit` (`"percent"`, carried only by `lucky_fraction` today) makes `StackOptionControl` show and accept 0–100 with a `%` suffix — value, min, max and step scaled together, so the typed input and the editor slider speak one unit — while the engine field, its `(0, 1]` contract and the stored value are untouched; `show`/`store` are the identity for every other field. The round-trip rounds in both directions, so a stored 0.35 renders `35 %` and stores back exactly 0.35 rather than 0.35000000000000003. Tests +8, including the invariant that a `percent` unit may only sit on a float whose bounds really are a fraction. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.397.0** — PRIORITY 2–3 (autonomy/friendliness), the LEAD filed with the v0.396.0 rename offer: **a mosaic is offered its object's name.** The offer was gated on a 0.25° cone against the *union canvas* centre, so the bundled 2×2 sample sits 0.3223° from M 42 and got nothing while a single field of the same object got an offer — on the owner's own dominant shooting shape. Not fixed by a bigger radius (which would claim neighbours for single fields too) but by the object's **own extent**: `objectinfo._object_containing` accepts a centre inside the object's minor half-axis, capped at 1.5°, consulted **only** when the cone found nothing, and only for a mosaic-suffixed name (`confident_object_title(allow_extent_match=)` is off by default, so the shared-caption path is untouched). Measured over the whole real catalog before believing it: **exactly one** containment exists beyond the cone in all 157 objects (M 31 contains M 32, 0.403° against 0.525°). Tests +5, four fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.398.0** — NEW BEGINNER FEATURE, PRIORITY 3 (friendliness/plan): **"Add tonight to calendar" on the constellation nudge.** The "you're one object away from finishing Lyra, and M57 is usable until 02:10" card ended on a sentence; `GET /api/life-list/nearly-there/calendar.ics` now hands that window to the beginner's own calendar as a plain offline `.ics`. It **names no id** — it re-asks the endpoint the card read and calendars the object *it* picked — so the `_SHOWPIECE_IDS` guard the idea warned about is neither widened nor needed, and the file can never describe a different night from the card. The body comes from the new shared `plan.catalog_object_ics_response` (extracted from `get_suggest_ics`, takes an object and never an id), so the two reminders cannot drift. 404 rather than a blank calendar on every empty case. Tests +8. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.396.0** — NEW BEGINNER FEATURE (the last open slice of the Scout's 2026-08-27 #10 entry, and the **🛑 BLOCKED** premise it was stuck on): **a target still named after its folder can be renamed to what the plate solve says it is, in one click.** The identity card gains "this target is still named after its folder — call it *Crescent Nebula*?" (opt-in `allowRename`, Target page only), backed by new `Library.rename_target` (display name only — the safe name, folder, project and every stored path stay put) and `objectinfo.suggested_target_rename` (the **title-grade** 0.25° cone, not the card's looser one, because a rename outlives the session; silent when the stored name already identifies something). **The blocker was real and is now fixed:** the scanner resolves a folder *by display name*, so a rename would have made the next scan allocate `NGC_6888_SUB-<sha1>` — a second target, same sky. New additive nullable `targets.folder_name` (no `SCHEMA_VERSION` bump; the existing `_ensure_columns` self-heal adds it) is the alias row that entry asked for, and `_names_owning_safe` lets a folder answer to both names. A test caught the split live before the column existed. `scanner.preserve_mosaic_suffix` keeps a mosaic a mosaic. Tests +16. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.395.0** — PRIORITY 2 (autonomy) and the last step of the north star, the owner's 2026-09-08 answer to gate Q1 shipped **with its condition rather than after it**: **an unattended night now comes back as a picture, and any one target can be told to stop.** `Settings.auto_edit_on_autostack` ships `True` — fresh installs only, the same §9 argument as v0.391.0's (`SettingsStore` re-saves the whole model, so every install that has booted carries an explicit `false` and no migration may flip it). The owner said *"yes, but should be easy to override with manual settings"*, and the backlog's own note said not to ship the flip without it, so all three halves are here: new `webapp/auto_edit_pref` stores a **tri-state per target** in the existing `project_meta` kv table (no schema change) — `None` follows the setting, `True`/`False` override it — which `pipeline._wants_auto_edit_for` consults before finishing a fresh stack, so it survives the night rather than a page; `_auto_edit_process_run` now refuses to write over a recipe **the user** saved — which is not the same as "a recipe exists", since the pass legitimately re-runs over its own output, a distinction an existing test found rather than reasoning did; it is separated by the baked-look stamp the run already carries; and the control is a link under **any picture the app finished** (`StackRunOut.auto_edited`, one more meta read in a loop that already does three) rather than a standing switch on every target page — it writes an explicit `false` to turn off, and clears vs. sets `true` to turn on depending on which one would actually work. A garbled or hand-edited value reads as *unset*, never as "off". Settings copy names the fresh-install caveat and all three ways out. "Process target" is deliberately untouched — an explicit click has always auto-edited. Tests +19 (5 pref unit, 5 pipeline/API, 2 config-upgrade incl. a stored-`false` that asserts it *differs from the fresh default*, 5 card, 2 copy). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.394.0** — PRIORITY 3 (enjoy + share), slice (iii) of the life-list follow-ups filed 2026-08-27 and the last one open: **"My life list" becomes one shareable picture.** New pure engine module `seestack/lifelistcard.py` composes all 110 Messier squares in catalog order — your own picture cover-cropped into the ones you have, a faintly lit square for one captured but not stacked yet, a dim numbered square for the rest — under a strip saying how far along you are. **The empty squares are the point:** the montage wall (`/api/gallery/montage.jpg`) shows only the pictures you have, which makes it a gallery; a life list has to draw the whole list. Three drawing calls are deliberately the opposite of the wall's and are explained in the full entry (cover-crop not letterbox; its own label drawer, because `_draw_corner_label` clamps to 9 px on a 114 px tile and would make the captured ids smaller than the to-shoot ones; left-aligned catalog order, so the counting survives a short last row). `GET /api/life-list/grid.jpg` renders it on demand from the previews the app already keeps and writes nothing, resolving each picture through the shared `targets.current_picture_path` so the poster cannot disagree with the page it was shared from; it **404s until one object is captured**, which is exactly where the new self-hiding "Share my grid" button inside the page's existing header card stops being offered. Previews are downscaled to `TILE_SOURCE_MAX_PX` on the way in and each target is loaded once, so filling 110 squares is tens of megabytes, not hundreds. Additive: one module, one read-only GET, one button; no config, schema, on-disk, API-shape or default change. Tests +18 (13 engine, 5 endpoint, 2 vitest). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.393.0** — the owner's 2026-09-08 answer to gate Q5 ("skip folders named `batch_stack_tmp` at scan time? → YES"), which was the one open **Bugs** entry nobody could start: **another stacking program's working folder is walked past instead of ingested as a junk target.** `_apply_seestar_convention` now skips a folder whose name is in the existing `_TEMP_FOLDER_NAMES` (the entry's own condition — reuse the set the v0.319.6 *cleanup* verdict already uses, never a second list), before the bare-folder fallback that used to bring it in. **Exact names, not a `*_tmp` pattern**, so a real folder someone named badly is untouched. **Not silent, because a silent skip could never be undone from the UI:** it lands in `ScanResult.unvouched_skips` *whatever its files are named* — the device-output rule can be certain it is right and so stays quiet when every file is accounted for, a name-pattern guess about someone else's directory cannot — and the report is where the one-click "bring it in" lives. That override needed no special case: a scoped scan takes the folder as the unit without consulting its name, which is its documented meaning; pinned by a test either way. New shared `components/skippedFolderCopy.ts` owns the wording so the Jobs alert and the Library card cannot drift into two accounts of one folder, and neither now calls a scratch directory "your Seestar's own finished picture"; the card keeps its own "are some of my subs missing?" title, which is the right question for the old rule and the wrong one for this. Additive `reason` field on `SkippedOutputFolder`, the remembered record and `SkippedFolderOut`, defaulted so an older record/backend/frontend reads as the only case it could produce. Tests +18 (6 engine, 4 webapp, 8 copy/UI; the engine and webapp ones fail before). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.392.0** — PRIORITY 1 (editor), the LEAD filed by the v0.390.0 run: **the editor asks before it drops a look you haven't saved.** Nothing in the editor persists a recipe on its own, so the nav bar, the in-page "History" button or the browser's back button silently threw the whole edit away — and there was no guard of any kind (`useBlocker`/`beforeunload` appeared nowhere in `frontend/src`). New `components/editor/UnsavedLookGuard.tsx`: `useBlocker` (a data router is mounted in `main.tsx`) raises a three-way modal — *Save and leave* / *Leave without saving* / *Stay here* — and `beforeunload` covers a tab close, registered only while there is something to lose. **The filed shape's baseline was deliberately not taken:** the entry proposed dirty = `recipeKey !== seedKey`, which on the v0.390.0 auto-seed path makes every first open dirty — the entry's own care note calls that worse than no guard. Dirtiness is measured instead against new `Editor.tsx::committedKey`, *the look the editor put on screen*: the Auto seed is not unsaved work (nobody asked for it and the next open reproduces it for free), while the first slider the user touches is. It moves forward on a successful Save **and** on Export, whose own notification sends the user straight to History. Both signatures are captured inside the mutation beside the recipe being sent, so an edit made while a save is in flight cannot slip past. Search-param-only navigations are not blocked (the editor rewrites its own query string). `seedKey` is untouched — the "What Auto-process did" note still needs it frozen. Frontend-only; no config, schema, on-disk, API or default change. Tests +10, and `Editor.test.tsx`'s harness moved from `MemoryRouter` to `createMemoryRouter`/`RouterProvider` (the router `main.tsx` actually mounts) so a navigation can be driven at all; all 113 existing cases pass unchanged. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.391.1** — BUG FIX (Builder-verified by reproduction, and by the READY fixture-shape entry that shipped with it): **a mosaic panel that is merely thinner than its neighbours is no longer cropped away as a ragged border.** On a dense raster with uneven panel depth — the owner's own 3x3 / 12x8 shooting shape — one-click Auto kept **25.6 %** of a 12x8 canvas, 34.8 % of a 6x4 and 17.6 % of an 8x6, all fully tiled with no ragged edge at all (AGENTS.md §1: a trim above ~15 % is a bug). **The second half of D1:** its fix made `panel_coverage_level` take the lowest *substantial* level instead of the peak, but substantial means 8 % of the canvas and 96 panels over two dozen depths hold ~1 % each, so the search walks past the thin panels and settles near the **mode** (19.1 where the thinnest panel is 8). The discriminator is not a threshold — 5 % of pixels *scattered* destroys the rectangle as thoroughly as 40 % around the rim — it is **what the discarded pixels are**: a border is *uncovered*, a thin panel is *covered*. So `largest_covered_rect` now also computes the rectangle the coverage alone allows, and when the depth threshold does worse than `TRIM_KEEP_RATIO` (0.8) of that bound it halves the threshold and asks again. Measured on fifteen shapes: every honest case byte-identical (including a **diagonal** mosaic, still 12.2 % — it is mostly uncovered, so its bound is small too), the three broken rasters → no crop, and a raster that is *both* uneven and genuinely ragged goes 34.2 % → **95.1 % kept** rather than standing down. Can only ever keep more, never less (pinned over 40 random maps). `well_covered_mask`, the all-sky fade and `coverage_thin_fraction` are untouched. Tests +5, two fail-before; no existing test weakened or rewritten. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.391.1 (same commit)** — the `READY` infra entry filed 2026-09-08: **`tests/shapes.py`, a vocabulary for stating what a "mosaic" fixture can and cannot vouch for**, measured with the *same* `panel_coverage_level` the rules under test measure with. `test_coverage_trim.py` now asserts its fixtures' shapes instead of describing them in a comment — and `assert_panels_thinner_than_the_reference` is what stops a "12x8 with uneven depth" test passing for the wrong reason. `test_photometric_mosaic_auto.py` also gains the assertion its whole file rested on unstated (both panels are drawn from the same seed, so a step between them is photometric and not sky). It found the bug above on its first run, which is the entry's own claim ("it is what finds the next D1") demonstrated rather than asserted. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.391.0** — PRIORITY 2 (autonomy), the ⭐ READY — GATE OPEN entry the owner approved 2026-09-07, with both prerequisites landed and nothing in front of it: **a fresh install now walks the whole chain — ingest → QC → solve → *stack* — without the owner finding a switch.** `Settings.auto_stack` ships `True`. **It reaches fresh installs only, deliberately:** `SettingsStore` re-saves the full model on every boot, so every install that has ever run carries an explicit `"auto_stack": false` and keeps it — and no migration flips it, because the file cannot tell "he turned it off in August" from "the app dumped the default", and flipping a setting someone turned off is the breach AGENTS.md §9 exists to prevent. The owner flips his own switch in Settings (still the one item under REQUIRES MANUAL OWNER ACTION). Safe on by default only because three guards landed first, all in the path: the readability preflight + thinner-than-best hold (v0.270.1), `auto_stack_min_frames`=3 (v0.256.0), and the settle window (v0.390.1). `auto_edit_on_autostack` stays **off** — that is question 1 on the owner's one-sitting list, not this entry's call. Settings copy now says both halves and names the three guards; the Walk-away master switch is unaffected (its other four keys still default off). Tests +3 Python / +2 vitest, **all five fail before the flip** — including the only test in `test_auto_stack_pipeline.py` that does not name `auto_stack`, and a stored-`false` upgrade test that asserts it *differs from the fresh default* rather than merely being `False`. Nothing loosened; one default value, no schema/on-disk/API change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.390.1** — PRIORITY 2 (autonomy), the READY entry filed 2026-09-08 and the prerequisite the `auto_stack` flip is gated on (**so that flip is now unblocked**): **a target the sky is still filling is held until the night settles, instead of being re-stacked in full after every 5-minute poll.** `_auto_stack_frame_count` fires on "more solved subs than the last stack covered" and nothing asked whether subs were still *arriving*, so a night of shooting one target meant re-stacking every night it had, over and over, while the "newest picture" kept becoming a picture of a night that was not over. New `pipeline._auto_stack_settle_hold` holds while the newest accepted sub is younger than `auto_stack_settle_min` (default 20 — a named constant: longer than any poll, shorter than a meridian-flip pause; 0 = today's cadence exactly), **without stamping the attempt marker**, exactly like the thin and readability holds — so the stack happens once, on the whole night, at the first scan after the subs stop. Delayed, never stranded, never skipped; the Stack form and "Process target" are untouched. Time comes from new pure `Project.newest_accepted_sub_time()` (two `MAX()`s, no `FrameRow` — asked of every target on every poll), preferring `source_mtime` and falling back to `timestamp_utc`, whose error direction can only make a target stack *sooner*. A source clock running ahead costs one window plus the skew, never forever. The entry's "second face" (per-target `auto_stack_min_frames` publishing a one-panel mosaic on night one) is covered by the same hold, not by a second mechanism. Surfaced on the Jobs page in the same alert shape the other two holds use ("waiting on N still being shot"), and deliberately **not** in `overnight.needs_a_look` — a target still being shot is not something to go and check. Tests +10 Python / +4 vitest; seventeen existing auto-stack tests across five files now set the window to 0 explicitly (their fixtures write subs seconds before asserting), none loosened. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.390.0** — PRIORITY 1 (editor), the ⭐ READY — GATE OPEN entry the owner approved 2026-09-07: **the editor opens on the good picture instead of a nudge to press one button.** On a run with no saved recipe, first open runs `…/editor/auto` and opens on that, with the usual "What Auto-process did" note and *"Started you off with Auto-process — Undo to see the plain stack."* It stands aside for a saved recipe, and for either look of the user's **own** — the previous run's edit *and* their saved default; the entry named only the first, but both buttons live inside the nudge a seed replaces, and removing a feature is the owner's one hard constraint. `resetOps([])` then `setOps(built)` puts it exactly one Undo from the plain stack (the reset matters — navigating from another run leaves that run's recipe in `ops`); nothing is persisted without a Save; a failed seed falls through to the old empty pipeline and nudge with **no** red error, via its own `autoSeed` mutation sharing `fetchAuto`/`applyAutoResult` with the button. `seeded` still gates every preview query, so the decision is made once and there is no seed-then-reseed flash. **Gate re-measured, not trusted:** the mosaic sample stacked fresh and read through `_trim_rect_for_run` keeps **92.1 %** of the canvas. Tests +6 net; the old first-view test rewritten deliberately, never weakened. The entry's "unsaved-changes guard" does not exist anywhere in the frontend — filed back under Ideas. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.389.2** — BUG FIX (the 🟠 VERIFIED entry filed 2026-09-08, with its two named companions): **"thin coverage" is measured against a *panel's* depth, not the coverage map's peak — the same mistake D1 removed from the trim.** `coverage_thin_fraction` now references `coverage_trim.panel_coverage_level`, so "How's my stack?" can no longer tell a mosaic owner that 22–74 % of his picture is a ragged border while offering a "Trim border" that keeps the whole canvas (measured on seven shapes: the 2x2 sample 22 % → 0.0 %, a 12x8 raster with uneven depth and weight jitter 74 % → 0.0 %; the single field unchanged to the digit, since the panel level *is* its peak). The level comes off a strided sample capped at 2 M pixels, because `panel_coverage_level` sorts a float64 copy and this runs at stack time on the full canvas. Old runs heal without a re-stack: two additive columns (`coverage_shares_version`, `coverage_median_depth`, no `SCHEMA_VERSION` bump) let `backfill_coverage_shares` **re-derive** a stale share off the map the run already wrote — a single-field run is never marked stale, and a stale mosaic whose map is gone goes quiet in memory only, never losing the row. The κ-σ reach note gains the provable half of A6: `coverage_median_depth` fires it on a mosaic whose panels are shallow but whose four-way corner cleared the threshold, worded as the half of the picture it can prove. `coverage_is_mosaic`'s dense-raster false negative is documented, deliberately **not** widened (legacy-fallback only). Tests +26. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.389.1** — CLOSED BY MEASUREMENT (the Scout's 2026-08-26 #2 idea, unblocked by v0.387.0): **`photometric_normalize` stays off outside a mosaic — star-core SNR gains only +0.16 % on the realistic single-field case with quality weighting on** (+0.39 / +1.22 / +3.33 % as the haze gets extreme; +0.00 % and bit-identical when there is nothing to correct). On a single field every pixel gets the *same* subs, so the spatial step that makes the pass valuable on a mosaic is structurally absent and all it can change is the combine weight — which quality weighting's `transparency_factor` already approximates. Not a default flip on the hot path. **The first fixture inverted the answer to −9.7 %** by scaling the sky noise along with the signal; haze dims the stars, not the sky glow. `tests/test_photometric_single_field.py` (+2) pins the bit-identity and the never-hurts direction. No code changed. Full entry, table and fixture warning in [`SHIPPED.md`](SHIPPED.md).
- **v0.389.0** — NEW BEGINNER FEATURE (the Scout's 2026-08-26 #4 entry, unblocked by doing the data task its 2026-08-29 stand-down laid out): **"does my colour look right?" — the finished picture's colour, checked against what that object actually looks like.** A vetted `nebula_class` (`emission` / `reflection` / `both` / `unknown`) is curated onto all 28 bundled `type: "nebula"` entries and nothing else, pinned by the blurb cross-check v0.276.0's `distance_ly` pass used (22/2/3/1). `edit/histogram.py::measure_object_colour` is the sibling of `measure_sky_cast` on the *object* population — sky-subtracted, star-core-trimmed, read off the stretched display image — and `seestack/colourcheck.py::colour_expectation` is the pure join to one line, or `None`. **Built to stay quiet:** only two families speak, a nudge needs 3× the lead a reassurance does, there is a dead band of silence between them, `both`/`unknown`/planetary/SNR never speak, and the word "wrong" never appears. A test, not reasoning, caught the σ estimator: a lower-half MAD called 34 % of a pure-noise frame "object"; `median − p15.87` puts it back at ~2 %. Surfaced as the editor histogram's `colour_check` beside the sky-cast line, plus `ObjectInfoOut.nebula_class`. Tests +27. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.388.0** — NEW BEGINNER FEATURE (the Scout's 2026-09-08 "While you were asleep" entry, built as it instructed — the Dashboard *did* already fold most of it, so it shipped as a consolidation rather than a card): **the "Last night" card now says what the app *did* with the night, not only what the sky gave.** New pure `webapp/overnight.py` — `new_pictures_since` (one line per target, newest first, each carrying the frame count of the picture it replaced so "deeper than the 78 it had before" is only said when true) and `needs_a_look` / `newest_scan_summary` (the holds the scan already records — `auto_stack_held_unreadable` missing-files first, then `auto_stack_held_thin` — read from the **newest finished scan only**, so a resolved hold stops being news with no state to go stale). Stamps compared with `activity_calendar.parse_utc`, never as strings (the app writes UTC in two shapes). Additive `RecentStack.is_genuine`, set through the *shared* `pipeline._stack_options_from_run_json` predicate, keeps an editor export from reading as a second picture; `_rollup_stacks_cached` extracts the cache `/api/stats` already owned so the digest costs no second walk over every project. `LastNightCard` gains three pure wording helpers — a missing-files hold reads as something outside the app to go and check, a thin hold as patience. Both lists are empty on a night nothing was stacked (the owner's live `auto_stack` off), so the card renders exactly as before. Tests +17 Python / +13 frontend. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.387.0** — PRIORITY 4 (image quality, and the only ready one that reaches a heavy mosaic user), the READY entry left open by v0.271.0: **a mosaic panel shot entirely through haze is lifted to match its neighbours, measured in the sky the panels share.** New `seestack/stack/overlapgain.py::compute_overlap_gain_scales` runs as a pre-pass at stack setup — each panel's clearest few subs through the stack's own `align.align_one`, block-meaned to a ~400 px coarse map, a median signal ratio per overlapping pair, then one log-scale per panel by least squares, normalised to a median of 1.0 and clamped to `[1/2, 2]`, multiplied into the `{frame_id: scale}` map the accumulators already consume. **NOT `transparency_score`** — v0.271.0 removed that comparison after measuring a 2.23× panel-gain error, because it cannot tell "hazy panel" from "emptier patch of sky". **Measured: the star-flux step across the join goes 38.6 % → 2.3 % on a 0.6× hazy panel, and the recovered scales are 0.774/1.291 = 1.667 = 1/0.6.** The guard that makes it safe on by default was found by a test, not by reasoning: overlapping *footprints* only mean two WCS agree, so on a fixture whose panels overlap while holding unrelated stars the first implementation invented a 2.6× gain — a Pearson correlation across the strip (`MIN_OVERLAP_CORRELATION`) refuses that and cannot be fooled by a gain, which is exactly what correlation is blind to. Every other uncertainty resolves to "change nothing" too: too few shared/signal cells, a ratio outside the clamp, a fit whose pairs disagree, or any exception → `None` → today's stack byte for byte. Provenance stamped as `PANG*` and surfaced as History's "Mosaic panels matched to each other · N panels · brightness lo–hi× · measured in N overlaps". Tests +15 engine / +2 API / +3 vitest; `test_a_wholly_hazy_panel_is_deliberately_left_alone` deliberately rewritten (its fixture cannot carry the new claim). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.386.2** — PRIORITY 3 (friendliness), Scout dogfood find on the **mosaic** target: **the "Is it enough yet?" goal chip printed a mosaic's per-panel-scaled goal as a raw float — `goal ~14.526171875 h (3.63-field mosaic)`.** The verdict sentence beside it already rounded via `readiness.ts::fmtGoal` ("~14.5 h"), but `Target.tsx` printed `readiness.goalHours` unrounded in the chip, so the two disagreed and the chip read like a bug. `fmtGoal` is now exported and used for the chip too (whole number as-is, else one decimal). Frontend-only, one-line behaviour change; verified by the `--mosaic` dogfood screenshot. Tests +1 fail-before (`Target.test.tsx`, a 3.63-field nebula mosaic → `goal ~14.5 h`, and the raw float absent). No config/schema/API/default change.
- **v0.386.1** — PRIORITY 3 (robustness on the RAM-capped NAS), the READY entry filed 2026-09-07: **the "Full-res PNG" download — and the "Full-size versions" archive that renders every target through the same call — stops holding about five copies of the picture at once.** `render_preview_png_full_res` owns every array it touches and never reads them again, so it now consumes rather than copies: `autostretch(copy=False)` (new opt-in flag; the default still copies for every other caller), an in-place normalise (`np.subtract/np.divide(out=img)` — that one line used to allocate two more full-size temporaries at once), `del rgb`, `nan_to_num(copy=False)`, `clip(out=)` and `pack_unit(copy=False)`. **Measured with `tracemalloc`, not estimated: 5.00× the decimated array before, 3.83× after** — ≈ 520 MB → ≈ 400 MB on the owner's 3494×2470 mosaic, ≈ 2.9 GB → ≈ 2.2 GB at the 8000 px cap, on a button a beginner presses to print while a stack job may be holding its own canvases. **Bit-parity, and pinned as such:** a new test renders linear, display-space and Adjust-stretched masters through an independent out-of-place copy of the old path and asserts the PNG bytes are identical. The robust percentile is left exact (a strided sample would move pixels), so what remains is the stretch's own working set. Tests +2, the ratio one failing before at 5.00×. Engine-only. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.386.0** — the READY infra entry filed 2026-09-07: **`scripts/agent-dogfood.sh --mosaic` — a second, opt-in sample target shaped like the owner's shooting, so an Auto/editor claim can finally be checked on a mosaic.** `webapp/sample_data.load_sample(lib, shape="mosaic")` builds a separate target from **one shared star catalog**: 2×2 panels stepping 82 % of a frame (so overlaps hold the *same* stars), per-panel pointing jitter, uneven depth (6/6/6/3) and one panel shot through haze (×0.85 signal on a +8 % sky). Measured on the real thing: a 907×615 union canvas, **4.8 % genuinely uncovered**, coverage plateaus at 3/6/12/21, `coverage_is_mosaic` True and four `pointing_groups` panels — every one of which is structurally invisible on the single-field sample, which is how D1 survived twenty sweeps. The script loads it, stacks it, prints the trim Auto would apply (**7.9 %** today; above ~15 % is D1-shaped) and probes/edits it into `$SHOTS/mosaic/` so the field sample's page-height baselines are untouched. Default unchanged everywhere: the Dashboard button, `POST /api/sample` with no body, and the field sample's generated pixels are **bit-identical** (verified against the old implementation). Tests +7. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.385.0** — PRIORITY 3 (friendliness), the READY entry filed 2026-09-07: **the "Save / share" menu was built twice and the two copies disagreed — now one `SavePictureMenu` component serves the Target page's hero and every History run card.** The item set is the *union* of the two (the hero gains FITS, TIFF and "Copy caption"; the History card gains "Share the keepsake"), the wording is History's label-plus-hint idiom on both, and the North-up / nameplate toggles still reach exactly the JPEG-family downloads they did. Nothing removed, no new surface, no page height changed (the menu is closed by default). Frontend-only; tests +7 new component cases, two Target assertions that fail before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.384.0** — PRIORITY 3 (get / enjoy / share), the READY entry filed 2026-09-07: **the picture he shares of a "Process target" run comes off the master instead of the 1024 px preview — and every share of any run stops re-reading that master.** `_native_picture_source` declined every display-space run (his main path: "Process target", "Reprocess everything", and every walk-away run once `auto_edit_on_autostack` is on), so its JPEG, keepsake, scale-&-compass, share and all three wallpapers were re-encodes of a 1024 px preview; and for a *linear* run it re-rendered the master on **every** request — 104 MB off the NAS per tap on his mosaic, nine taps to a run. New `_build_or_get_share_source` renders once through `pipeline.render_run_full_res_png` (the one place that decides which render a finished run *means*, so the share, the Full-res PNG button and the pictures archive cannot drift) and caches it beside the run as `<basename>_share.png` + `_share.sig`, modelled on the zoom clip: signature = preview stamp | master stamp | recipe hash | size | app version, written `.tmp`-then-renamed. One render at the largest size any hand-out needs serves them all; the share JPEG decimates the decoded cache (`Image.BOX`), never a second FITS read. Both files are registered in `RUN_ARTEFACT_SUFFIXES`, so they are deleted and pruned with the run. **A display-space run with no saved recipe still declines** — the plain render of its linear master is the *un-edited* picture — as do the baked-North-up and cropped-preview cases, unchanged. Tests +8, four fail-before; the two existing tests that pinned the old blanket decline now pin the recipe-less case they were really about, renamed in the same commit. Additive files only; no config, schema, API-shape or default change. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.383.1** — PRIORITY 3 (friendliness — a felt wait on a beginner feature): **a Sun or Moon video stack stops debayering the frames it is about to throw away.** `video/ffmpeg.iter_frames` demosaics a raw (CFA) capture once per decoded frame — ~350 ms a frame on the owner's 4,487-frame solar file — and `lucky.stack_video`'s second pass paid it for *every* frame before dropping all but `keep_percent` of them one line later, so roughly a third of a half-hour stack was debayering discards. `iter_frames` now takes `wanted: Collection[int] | None`; a frame outside it is still decoded (the byte framing demands it) but not demosaiced, and is yielded as **`None`** rather than skipped — so the caller's `enumerate` still lines up with the `keep_idx` pass 1 built, and no caller can ever mistake an un-demosaiced mosaic for a picture. Pass 1 is untouched (it grades on the colour frame's luma). The "is this really a mosaic" latch stays on the **first frame off the wire**, wanted or not, so a capture whose first frame is discarded still debayers correctly. Tests +5: the demosaic count is `n_graded + n_kept` (18, where it was 24) on a real ffmpeg-encoded `pal8` capture, and the stacked image is `array_equal` to the same run with the old eager decode — this is a skip, not a change. Engine-only.
- **2026-09-08 (backlog-readiness run, docs only) — D4 closed: the working list cut from 13,052 to 3,950 lines.** 47 shipped or closed entries archived verbatim in [`SHIPPED.md`](SHIPPED.md) and 46 sweep records, dogfood baselines, process and collision notes moved verbatim to [`PROCESS-NOTES.md`](PROCESS-NOTES.md) (both under a 2026-09-08 heading). Open residue worth knowing from the archived partials: ~~an in-UI destination picker for bulk upload~~ *(shipped v0.403.0)*; a 9:16 portrait zoom clip; a noise-delta picture on "Did it get better?"; auto-applying the classified preset; raw-OSC video and drizzle-upscale for Stack video — the three that need the owner are on his one-sitting list. The "Shipped" list below was compressed to one line per entry in the same pass (400 entries; full text archived verbatim in `SHIPPED.md`).
- **v0.383.0** — PRIORITY 3 (trust / friendliness), the READY entry filed 2026-09-07: **the Storage page says, with the owner's own numbers, that the subs in `incoming/` are the only copy there is.** The largest risk to his pictures is not a bug in this app — his raws live in `incoming/` and nowhere else, `copy_to_cache` is off so the app holds no copy, and nothing said so; the page's closing aside called the folder "worth having a backup of" in the same breath as "you can rebuild your whole library from them". That aside is now one plain sentence built from his data: *"Your 8,542 subs (44 GB) in incoming/ are the only copy AstroStack knows of. It reads them where they are and never writes there, and it keeps no copy of its own — nothing this app does backs them up. Keep a copy somewhere else."* With `copy_to_cache` on it says instead that the cache copies are working files "Clear caches" deletes — not a backup. **The numbers come from the `frames` rows, never from the folder:** new pure `Project.source_frames_under(prefix)` sums `source_size_bytes` over rows whose `source_path` has that literal prefix (`substr`, no LIKE escaping; trailing separator so `incoming2/` can't match), called inside the per-target `try` `get_storage` already opens — so answering never walks, opens or `stat`s anything under `incoming/` (AGENTS.md §10), pinned by a test that makes those calls fatal *and* proves the trap armed first. Rows predating `source_size_bytes` are reported separately, so the figure is honestly "at least". Four additive response fields with defaults + `frontend/src/components/incomingCopyNote.ts` (pure, takes the page's own byte formatter). Nothing removed; no new card. Tests +11, two fail-before; `tsc`/`vitest`/`vite build` clean. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.382.5** — 🟡 PRIORITY 3 (friendliness / trust), the third audit's **D2**: **the "installing ASTAP's star database helps" note stops firing at a night that is merely still being solved.** A scan ingests every new sub *before* any is solved, and `seestack/stackhealth.py`'s `unsolved` note counted every accepted sub with no `wcs_json` as a plate-solve failure — so mid-pipeline, on a healthy night, it announced *"Only 36 of 120 subs could be located"* and pointed the owner at a setup problem that does not exist, for as long as the solve took. Both terms now count only frames whose solve has actually **run**: new pure `_solve_was_tried` reads the `reject_reason='solve_failed:…'` mark a failed solve leaves (a failure deliberately does not touch `accept`), which is the same predicate `Project.solve_failure_reasons` already uses, so the note and the reject breakdown cannot disagree. Side effect worth having: the ratio a beginner reads is now the true failure rate rather than one diluted by the queue — 6 located / 6 failed / 300 pending reads *"6 of 12"*, not *"6 of 312"*. Conservative by design (a frame keeping a concrete `qc_error` reason reads as untried — undercounting keeps the note quiet, overcounting is the bug). Engine + copy only; no config, schema, on-disk, API or default change. Tests +2 fail-before, plus four existing fixtures given the mark a real failed solve leaves. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.382.4** — 🔴🔴 **D1, the third audit's headline find: Auto's border trim cropped every mosaic down to its panel overlaps.** `coverage_trim.well_covered_mask` measured "well covered" as half the map's **peak** — right on a single field (the peak *is* the interior), catastrophic on a mosaic (the peak is where panels **overlap**, so the threshold sat above every panel interior). Reproduced before changing anything, with the audit's own shapes: 2x2 @15% kept **8.0 %** of the canvas, 3x3 @5% **1.7 %**, 12x8 raster 1.5 %, and a 1x2 with unequal depths **dropped the thin panel whole** — while the single-field control returned its correct `(0.02, 0.02, 0.98, 0.98)`. New pure `coverage_trim.panel_coverage_level` measures against **one panel** instead: the lowest coverage level a real share of the canvas sits at. That one sentence is right for both shapes — a single field has exactly one such level and it *is* the peak, so that path is **byte-for-byte unchanged**; a mosaic has several and the lowest is one panel; unequal panels give the *thinner* one. Levels are found by relative tolerance (weighted coverage reads as 30±jitter, and integer bucketing would shatter it) above an absolute pixel floor (on a tiny map 8 % rounds down to "one pixel is a plateau"). **The reference is always ≤ the peak, so the mask can only grow — the worst case is leaving fringe in, never trimming a panel away**, and that property is itself tested. Both consumers move together (`render/thumbnail.stack_detail_mask`, the "My map" fade). Half the commit is fixtures: six tests shared a "thin single-frame fringe" that was **62 % of the canvas** — the same shape as the bug — and now share one ramped 4 px border, with no assertion loosened. Tests +8, three fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.382.3** — PRIORITY 1 (editor responsiveness), the second bite out of the same clause and the bigger one: **the live preview stops reading a mosaic's whole coverage canvas, twice, on every render.** `seestack/edit/proxy.py::_load_map` did `np.asarray(fits.getdata(path), dtype=np.float32)` and strided *afterwards* — the cast copies, so the run's **full-resolution** map was materialised every time, and that map is hundreds of MB at this owner's mosaic sizes. The editor asks for two of them (coverage + frame coverage) per render and fires two renders per edit, so one slider drag was four full-canvas reads and four full-canvas allocations before any op ran. Now: open with `memmap=True`, slice `[::step, ::step]` first, cast last — measured on a 480 MB map at the proxy's own step of 8, **2.65 s cold / 0.21 s warm → 0.011–0.021 s**, with identical values (the decimation picks pixels, the cast rounds each one; neither order changes which or what). The defensive 3-D collapse moves after the stride for the same reason. Tests +2 (the memory contract as its two observable halves — a memmap is asked for, `fits.getdata` is monkeypatched to raise and never reached — plus the float64 and 3-D reorder cases); the 133 existing coverage/leveling tests pass unchanged. Same signature, same values, nothing persisted or defaulted differently. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.382.2** — PRIORITY 1 (editor), the first bite out of the only thing the "Live preview" entry still listed as open — *responsiveness*: **the live preview stops re-solving the star field it solved a moment ago.** Several ops measure the whole image before they transform it (the stretch's per-channel stats, the tone curve's points, "Neutralize background"'s sky medians, and by far the largest, colour calibration's star detection + white-balance solve), and every render redid all of it from the top — twice, since the preview PNG and the histogram are two requests over the same recipe and the same proxy. New `webapp/edit_fit_cache.py` carries those measurements forward through the `EditContext.fit` channel the loupe already uses, but **only for the longest common prefix of enabled ops**: the first op whose id or params differ ends the prefix, so an op either receives the number it would have measured anyway or measures it. Measured on a 1500×1000 proxy with the one-click Auto recipe: **4.25 s → 2.39 s per render (1.78×)**, `np.array_equal(before, after, equal_nan=True)` **True**. Position-not-uid matching is load-bearing (a recipe posted without uids gets fresh ones per request, which would have made the carry a permanent miss); proxy geometry is in the key so a windowed render can never share one. In-process, bounded to 8 slots of small scalars, nothing persisted — a miss is exactly today's behaviour. Tests +10, four of them through the endpoints. Full entry, and the measured next slice (`frozen_deltas`, another 1.8×, 4.2e-7 apart), in [`SHIPPED.md`](SHIPPED.md).
- **v0.382.1** — PRIORITY 4 (image quality), a three-times-deferred real-data gate closed with numbers instead of another deferral: **"does the Auto denoise↔sharpen crossfade over-read a sky gradient as noise?" — no, and it has not since v0.225.0.** The entry was filed 2026-07-08 against the *level*-MAD `sky_sigma`, where gradient 0.00→0.05→0.10→0.20 of range moved it 0.015→0.028→0.054→0.098 and flipped Auto to *sharpen 0.0 / full denoise* by a gradient of 0.05. The local adjacent-pixel-difference estimator (v0.225.0, shipped for the mosaic grid regression) is blind to structure slower than a pixel, so running the entry's own ladder on the current code gives **0.0042→0.0039→0.0035→0.0030** — *down*, not up, because the tilt lifts the normalisation ceiling — with `_noise_fraction` 0 throughout, no denoise op added, and an identical sharpen amount. No product code changed; what ships is the pin: `test_a_strong_gradient_never_costs_a_clean_stack_its_sharpening` holds the *decision* across the whole feared range, where the existing sibling test held only the σ at one gradient. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.382.0** — PRIORITY 2 (autonomy) + the unblocking of a PRIORITY 4 gate: **the app starts collecting the real-data evidence its own gated highlight cue needs.** The automatic "your core is blown out" cue is deliberately real-data-gated — nobody knows how often a genuinely blown core occurs on the owner's stacks, or how severe — and runs keep meeting that gate and standing down while nothing accrues the measurement. Now every unattended auto-edit asks the editor's own solver what "Hold back highlights" would offer on the picture it just made and stamps the answer (`editor_auto_highlight:{run_id}`), **including an explicit `strength: null`** so "measured and clean" never reads as "never measured"; `pipeline.auto_highlight_summary` + `GET /api/auto-highlight-summary` aggregate it, and one dimmed line joins the Auto colour self-check on Settings → Maintenance. `editor.solve_highlight_protect` is the endpoint's body lifted out, so the button and the passive record cannot drift (with `uid=None` it solves against the recipe's *own* stretch — pinned). No pixel moves, no default flips; the proxy it measures on is the one the editor builds anyway, so a fresh run now warms it. Tests +16. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.381.0** — PRIORITY 2–3 (trust / autonomy), closing the "LEAD, NOT FINISHED" filed the same day: **the folder your scan walked past now waits for you on the Library page.** A bare `<T>/` beside `<T>_sub/` holding files the Seestar's naming can't vouch for — the owner's `NGC 6888`, 4,815 files — has been *reported* since v0.329.2 and *actionable* since v0.378.0, but only on the **Jobs page**, attached to one scan's result, and the scan that finds it is the watcher's, fired while nobody is looking. New `webapp/skipped_folders.py` has the scan **write the finding down** (one JSON value in the registry's existing `library_meta` table — the lead's feared "schema decision" was not needed), `GET /api/targets/skipped-folders` serves it, and `SkippedFoldersCard` shows it on the Library page with the same one-click "bring it in" (`BringFolderInButton`, now shared with Jobs so the two can't drift). **The part a standing card needs and a per-scan alert never did:** the convention keeps skipping the folder, so a card mirroring the newest scan would still be shouting after the owner acted — a remembered folder is therefore dropped as soon as its target owns *any* frame from inside it, and one that has left `incoming/` is forgotten. Polling never walks `incoming/` (pinned by a test that makes a walk fatal); nothing writes to it. Upgrade-safe: one additive meta row, one additive endpoint. Tests +23. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.380.0** — PRIORITY 1 + 3 (editor / friendliness), the completion of v0.379.0's beginner path: **a "Crop" button in the editor header, beside the app's two automatic crop offers.** Cropping is the edit a beginner is most likely to want *and* know the name of, and the only route to it was **Add operation → More operations → Crop** — the op is not in the Add menu's Common group — followed by four typed fractions. One click now adds the op (or **re-opens the recipe's existing crop**, via the new pure `cropDrag.ts::existingCropUid`, rather than stacking a second one whose fractions would be relative to the first's output; a crop the user had switched off comes back on, since pressing Crop *is* the ask), selects it, and opens the drag rectangle. **Placed in a group that already exists** — "Trim border" and "Re-centre" both end in the same adjustable Crop op — so it is not one more always-on banner, and it is hidden while a crop *proposal* owns the preview. **Measured, as the IA rule requires:** page heights byte-identical on the running app (phone editor **2,887 px**, desktop **1,841 px**, both unchanged; on a 420 px phone it shares the Auto-process row rather than starting a new one), nothing overflowing, no console errors. Nine existing `Editor.test.tsx` queries that reached the pipeline's Crop row by its bare text are now addressed by its own `aria-label` ("Select Crop") — more precise, not looser, and the reason one of them failed first. Frontend only. Tests +7.
- **v0.379.1** — PRIORITY 1 (editor), two refinements the browser probe of v0.379.0 asked for (no logic change): the crop **handles' grab area is 22 px around a 12 px marker**, so a handle is hittable with a finger on the 374 px-wide phone preview without eight chunky squares sitting on the picture; and the *"Keeping 62% × 55%"* caption takes `pointerEvents: "none"`, because it is drawn over the **top-left corner handle** — the one control on that screen you must be able to grab. Verified end-to-end against a running app (`Editor.tsx`).
- **v0.379.0** — ⭐ PRIORITY 1 (editor), a new beginner-facing capability on an op that already existed: **you can aim a crop by dragging it on the picture instead of typing four fractions.** `geometry.crop` was only ever reachable through the descriptor form's Left/Top/Right/Bottom sliders — fractions of a canvas that is 10,000 px wide on this owner's mosaics, chosen while looking at a decimated proxy. Selecting an enabled Crop op now opens a draggable rectangle on the live preview (body slides, eight handles resize, outside dimmed, *"Keeping 60% × 80% of the picture"* live), plus one-click **"Back to the whole picture"** and a plain-language note before a crop under a quarter of the frame costs real pixels. The sliders stay and follow along. **The rectangle is drawn over the recipe with *this op bypassed*** — a crop's fractions are relative to the image entering it, so dragging on the ordinary (already-cropped) preview would compound against itself; new `cropDrag.ts::cropDragBlockedReason` therefore **declines, and says why**, when any enabled geometry op sits after this crop (a Rotate, a Resize, or a second Crop, whose bypassed render would show *its* output). The overlay box's aspect is measured off the loaded image, since no endpoint reports the bypassed render's dimensions, and the rectangle waits for that measurement rather than risking an offset. The drag is local until release: one undo step, no per-pixel re-render, and the bypassed render is now keyed on the *other* ops only (`withoutOpKey`), which also makes the existing per-op Compare/Split cheaper. Frontend only; no engine, schema, config, on-disk or default change. Tests +39. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.378.1** — Tooling (no product code): **`scripts/agent-setup.sh` stops printing "agent env ready" over a `.venv` that holds nothing but pip.** A PyPI read timed out mid-resolve, `pip install -e ".[dev,web]"` died, and the `source`d script's `set -e` did not stop it — so the run met `No module named pytest` and had to work out that a perfectly good checkout was not the problem. It now retries the install once at a longer timeout, decides readiness by **importing** (`pytest, fastapi, numpy, astropy`) rather than by an exit status it cannot trust, and on failure prints the retry command plus the diagnosis — *this is an install failure, the checkout is fine* — and returns 1. Success path byte-identical. `AGENTS.md` §7 carries the same tell. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.378.0** — Autonomy / friendliness (PRIORITY 2–3), and a latent defect in a public API: **a folder the scan skipped as "your Seestar's own picture" can now be brought in with one click, instead of by renaming it inside `incoming/`.** `POST /api/scan`'s `root` field always read like a "re-scan just this folder" shortcut and was not one — `scan_and_organize` derives each target's name from the file's path *relative to the scan root*, so a root pointed **at** a target's folder left nothing to derive from and filed every frame under `Unsorted`. New `scanner.target_name_for_folder` (the convention's naming half, now shared so a scoped scan cannot fork a target) + `scan_and_organize(single_target=True)` → `_scan_one_folder`, which ingests the folder itself as one target and leaves out only what is still knowable per file, a `Stacked*.fit`. Surfaced where the problem is reported: the Jobs page's skipped-folder alert now carries the folder's path and a **"Bring \"X\" in anyway"** button, and its old advice — *rename the folder* — is gone, because that rename would have to happen inside `incoming/`, where the owner's raws exist in one copy and nowhere else (AGENTS.md §10). Off-path by construction: no `root`, or `root` = the incoming folder, is the ordinary scan, byte-for-byte. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.377.2** — PRIORITY 1 (editor), found by looking at the phone screenshot the new `--editor` drive took: **a quarter of the live preview was hidden behind its own toolbar.** The preview controls (Star mask / Compare / Split / Compare a look / Refresh / Zoom) were a `<Group>` at `position: absolute; right: 8; top: 8` inside the black stage — tidy at 1440 px (one row, 588×30 over a 653×435 image = **6.2 %** of the picture), and at 420 px the same six buttons wrap to **two rows**, 366×66 over a 374×249 image = **25.9 %**, on the width the owner actually reads this app at; a mosaic renders a seventh button. The `<Group>` now sits **under** the picture in the normal flow (`justify="flex-end"`), at every width — a move, not a removal, per the owner's own IA constraint, and with no new mechanism (no `useMediaQuery`, no duplicated `visibleFrom`/`hiddenFrom` DOM). The transient overlays that *label* the picture — the "Star mask"/"Proposed crop" captions, the coverage legend, "Updating…" — stay on it. Measured after on the same running app: **the picture did not shrink** (652.7×435.1 / 374×249.3, identical), desktop page height **1,841 px unchanged**, phone **2,815 → 2,887 px (+72 px, +2.6 %)** — the stated cost for 25.9 % of the preview back. Tests +1, fail-before (and the first draft of that test was vacuous because `closest('[style*="position: relative"]')` stops at the image's own box; it now walks up to the stage by `overflow: hidden`). Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.377.1** — Tooling for PRIORITY 1 (no product code): **the dogfood pass can now *drive* the editor, not just photograph it.** `scripts/dogfood_probe.mjs` screenshots `/targets/<t>/edit/<run>` in the one state it opens in, but every complaint AGENTS.md §1 records about the editor is about what happens **after a click**, and nothing in this repo’s tooling had ever clicked one — while two consecutive runs have reported the backlog dry, i.e. the running-app method is the one still finding things and it could not reach the highest-priority surface. New `scripts/dogfood_editor.mjs` (`agent-dogfood.sh --editor`) adds **every op the Add menu offers**, waits for the debounced preview to settle, and checks it actually re-rendered with no console error and no failed request, removes the op again so op N is measured against the same recipe as op 1, then undoes and redoes. The op list is read from the open menu rather than hard-coded (expand *"More operations"* first, read the label off the item’s first `<p>`, address by index because Common repeats, then dedupe → exactly the **21** ops `registry.all_specs()` holds), and removal targets `[aria-pressed="true"]` because `addOp` inserts on the correct side of the stretch rather than appending. `--editor` is hoisted out of the page-probe block so `--editor --no-probe` works. Off by default (a few minutes); AGENTS.md §7 says to add it on any run that touches the editor. **First run clean:** 21/21 ops previewed, undo+redo applied, no errors. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.377.0** — Friendliness / trust (PRIORITY 3), and the measured quantity two earlier runs said it needed: **"How's my stack?" can finally say what the black around a mosaic is.** A beginner meeting a wide black band on an unedited mosaic had nothing telling them whether the picture was broken, and the existing coverage note *structurally could not* tell them: `stacker.coverage_thin_fraction` is `count((cov > 0) & (cov < 0.25·peak)) / count(cov > 0)`, so the uncovered pixels are in neither of its terms — measured at **0.00 % thin on a canvas that is 36.6 % black**. New pure `stacker.uncovered_fraction` (share of *every* canvas pixel no frame reached; NaN counts as absence; `None` when nothing is covered, since an empty canvas is not "a picture that is 100 % black"), persisted as `stack_runs.uncovered_frac`, and a new `uncovered` health note that **explains before it offers** — on a diagonal mosaic the largest well-covered rectangle is genuinely small, so Trim border is named as a choice, not as the fix. **No `SCHEMA_VERSION` bump, deliberately:** `Project._check_schema` raises on a DB newer than the build, so a bump would stop the *previous* Docker image opening the owner's projects; the column arrives through `_reconcile_table_columns` instead, additive in both directions. Old runs heal off the coverage map they already wrote — `backfill_coverage_shares` fills both shares from **one** read. Threshold measured, not chosen (`_UNCOVERED_SHARE = 0.12`): eight real `run_stack` geometries put the honest cases at 1.1–5.1 % (reprojection leaves a NaN margin, so "any black at all" would fire on every stack ever made) and the genuinely ragged ones at 19.8 % / 36.6 %. No frontend change (`kind` is a plain string; the card keys off `action`). Tests +21. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.376.2** — Friendliness / performance (PRIORITY 3), measured before it was built (no pixel changes): **the Sky map stopped re-reading every target's master FITS on every visit.** The map requests one `sky-overlay` per target with a stack, each of which runs `stack_coverage_mask` over the whole master cube — **14–23 ms warm on a 104 MB (3494×2470×3) mosaic master**, which is what **declines shape (b)** (a composed-RGBA cache would buy tens of milliseconds and own an invalidation bug), but those megabytes come **off the NAS** cold, per target, on every visit and reload — and `Cache-Control: no-store` forbade even keeping the copy a revalidation would refer to. New `_file_stamp` / `_derived_image_etag` / `_etag_matches` give the response a strong `ETag` over the preview's and the master's `mtime:size`, `preview_north_up_deg`, `preview_crop_json` and `webapp.__version__`; `private, no-cache` keeps it revalidated on **every** request (so a History "Adjust" re-save can never serve stale) while making revalidation possible at all, and a matching `If-None-Match` is answered **304** from two `stat` calls. Weak (`W/`) and `*` validators handled. Headers only — no body, endpoint, config, schema, on-disk or default change. Tests +2, both fail-before. Four sibling `no-store` image endpoints left open on purpose: same shape, different invalidation inputs, none measured. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.376.1** — Performance, measured on the owner's shape (no behaviour change): **the Stack page stopped building the same mosaic canvas twice per load.** `routes/Stack.tsx` ran two `stackEstimate` queries — the sizing for the options on screen, and a fixed `drizzle: true, scale 1.5` feasibility probe behind the proactive drizzle nudge — and both went through `estimate_stack`, whose whole cost is `mosaic.compute_mosaic_canvas`: one stored WCS read per **sub**. The second request re-derived the identical canvas because it asked about a different *drizzle scale*, a knob that multiplies the canvas's output and cannot move the canvas. `estimate_stack` is now split into `estimate_stack_basis` (the expensive, options-independent half → the new frozen `StackCanvasBasis`) and `estimate_stack_from_basis` (pure arithmetic), composed back into an unchanged `estimate_stack`; `mosaic_canvas` is the one option the canvas depends on, so a basis **refuses** options that disagree with it rather than silently sizing the wrong canvas. `/stack-estimate` gains an additive `drizzle_probe` sized off that shared basis at `DRIZZLE_PROBE_SCALE = 1.5`, built from a fresh `StackOptions` so the rejection knobs can't make the nudge flicker. Measured on a 9-panel **5,477**-sub mosaic: a Stack-page load's sizing work **2.18 s → 1.13 s**, a second sizing off a held basis **44 µs**. Upgrade-safe both ways — an older frontend ignores the key; a newer frontend against an older backend withholds the nudge rather than suggesting a run that might be refused. Shape (c) of the four-shape perf lead; (b) and (d) stay open. Tests +11, 4 fail-before. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.375.0 + v0.376.0** — ⭐ NEW BEGINNER FEATURE: **"My wishlist"** — save the objects *you* want to shoot (a `wishlist` table in the library registry, `Library.add_to_wishlist`, `seestack/wishlist.py`, `GET`/`POST`/`DELETE /api/wishlist`, `WishlistStar` on every life-list tile and on the Tonight page's catalog rows) and be told on the right night that one of them is up (`GET /api/wishlist/tonight` over the planner's own `nightplan.well_placed_tonight`, `WishlistTonightCard`). **No `LIBRARY_SCHEMA_VERSION` bump — deliberately:** the DDL lives in `_AUX_TABLES_SQL` and is re-run idempotently on every open (`_ensure_aux_tables`), because a bump would make the *previous* Docker image refuse to open the registry and turn a rollback into a bricked install. "Captured" is delegated to `lifelist.catalog_capture_status`, never re-derived, so the two screens cannot disagree. Self-hides on an empty list, no location, nothing up, an older backend, and while another night is picked. Tests +38. Full entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.374.11** — Friendliness (PRIORITY 3) with a **verified bug** at its centre: **tapping "what does this do?" on a stacking option changed the option.** `HintLabel` — the *only* explanation surface for a descriptor-driven option, shared by the Stack form, Settings, the editor's op parameter panel and the editor's print-size control — hung `field.help` on a hover `Tooltip` around a bare 14 px `<svg>`. It is passed as a `Switch`'s `label`, which Mantine renders **inside a `<label>`**, so a click on the icon activated the control: driving the pre-change component directly, one click on a boolean option's icon fired `onChange(true)`. A phone has no hover, so that click is the only gesture a beginner has for "what does this do?" — it flipped their setting and showed them nothing. The icon is now a real control (`UnstyledButton component="span" role="button" tabIndex={0}`, controlled tooltip opened by tap, hover *or* focus, `preventDefault()` on the click). **A span and not a button is load-bearing:** a `<button>` inside that `<label>` is a *labelable* element, so the field's label would name two controls at once — it broke seven `Settings.test.tsx` queries the moment it was tried, and reads the same way to a screen reader; the `aria-label` is generic (*"What does this do?"*) for the same reason. **No page gets taller** — same icon, `lineHeight: 0`, no padding, no new prose — and hover is unchanged for anyone with a mouse, while keyboard users reach the hint for the first time. Second slice of the "a Tooltip is invisible on a phone" entry, taken at the shared component rather than one route. Frontend only; tests +7, four fail-before.
- **v0.374.10** — Friendliness / trust (PRIORITY 3), copy only: **the grainier-restack note stops saying "about 2400% more background grain".** A manual restack of a handful of subs against a 500-sub master really is that much grainier — arithmetically right, and it reads as a bug, on the one note whose whole job is to be trustworthy when the picture got *worse*. New pure `format.formatMoreThan` says a gap past a tripling as a multiple instead — *"about 25.0× as much background grain as your 14 May one"* — and returns the **joining word** with the number, because the phrasing change moves the preposition (*more … than* → *as much … as*) and that is exactly where a hand-assembled sentence breaks. The ordinary band is untouched, which is where nearly every real firing lands (the nudge's bar is ~17.6 % more grain), and 200 % itself still prints as a percentage — both sides of the crossover are pinned. A non-finite, zero or negative gap prints "about 1% more" rather than `NaN`. `percent_cleaner`, the mirror note's number, needed nothing: a fraction *less* is bounded below 100 % by construction. Endpoint and engine untouched; frontend only. Tests +7.
- **v0.374.9** — Performance, the residue v0.374.8 filed with its number (no behaviour change): **reading a sub's stored solution stops re-verifying a FITS header card by card.** `wcs_io.wcs_from_text` went through `astropy.wcs.WCS(Header.fromstring(text))` at **0.85–1.05 ms** a frame, and `mosaic.compute_mosaic_canvas` reads one per **sub** — the last ~4 s of the ~4.7 s `/stack-estimate` (fired **twice** per Stack-page load, and again on every drizzle/canvas toggle) and `/rejection-outlook` (every Target-page load). The cost is not the projection maths: it is `Card._verify`, paid building the `Header` *and* again on every `key in header` lookup. New `_wcs_from_plain_tan_text` scans the fixed-format 80-column cards itself and assigns onto a bare `WCS(naxis=2)`: **0.85 ms → 0.07 ms** a header (12×), `compute_mosaic_canvas` on a 9-panel **5,477**-sub mosaic **6.02 s → 0.89 s** (6.8×), `estimate_stack` on a real 5,477-row `project.sqlite` **6.04 s → 1.06 s** (5.7×), and every real stack and plate-solve read benefits too. **A pure optimisation, pinned as one:** across ten header shapes (our own CDELT and CD serialisations, an ASTAP sidecar carrying CD beside CDELT+CROTA, the legacy CDELT+CROTA2 convention, half-written CD/PC matrices, a seam frame, a near-pole frame) the fast WCS re-serialises **byte-identically** through `to_header(relax=True)`, records the same `pixel_shape`, and transforms a pixel grid to **bit-identical** RA/Dec; `test_mosaic.py` pins the union canvas identical with the fast path disabled. `CROTA` is handed to wcslib via `wcs.crota` rather than re-implemented. Anything the scan doesn't fully understand — SIP, `PV`, a non-TAN or galactic projection, a third axis, non-degree units, a duplicated keyword, a length that isn't a whole number of cards — returns `None` and falls through to astropy's own read, so no keyword can be silently dropped and a bare `END` sidecar still reads as an unsolved frame. Shape (a) of the four filed; (b)–(d) stay open with their care notes. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.374.8** — Performance, found by running the app at the owner's scale (no behaviour change): **two endpoints took ~14 seconds each on a 5,477-sub target.** Sweeping all 36 per-target read-only GETs (enumerated from the app's own OpenAPI schema) against a 9-panel, 5,477-sub mosaic found the distribution sane except for `/stack-estimate` (**13.8 s** — the Stack page fires it *twice* and refetches on every drizzle/canvas toggle) and `/rejection-outlook` (**13.3 s** — the Target page NoticeBoard, every load). Both run `mosaic.compute_mosaic_canvas`, which calls `wcs_io.footprint_radec_deg` once per **sub**, and that transformed the four corners with four separate `pixel_to_world` calls — each building a whole `SkyCoord`. One vectorised `all_pix2world` instead: **1.299 ms → 0.011 ms** a frame (118×), `compute_mosaic_canvas` **13.87 s → 4.75 s** for the identical `3494×2470` canvas, the two endpoints **→ 4.66 s / 4.77 s**, the whole 36-endpoint sweep **28.3 s → 10.6 s**. Deviation from the old path over 200 WCSs: **0.0**. Gated on a new `_is_plain_radec` so a galactic WCS is never read as RA/Dec (it keeps the old path, which declines it), and fast-path failures fall through so a frame with no size still answers `None`. Every real stack benefits too. Entry in [`SHIPPED.md`](SHIPPED.md); the residual `wcs_from_text` cost is filed below with its number.
- **v0.374.7** — Performance, measured on the owner's own shape (no behaviour change): **the shared mosaic-panel gate stopped clustering one row per sub.** `seestack/stack/pointings.py::cluster_pointings` is single-linkage union-find, **O(n²) in pure Python**, and `pointing_groups` — the one gate QC grading, quality weighting, photometric normalization, the transparency baseline, the session recap and bulk-select all delegate to — was handed a whole target's frame list, as was `detect_mixed_pointings` (the pre-flight of every unattended stack once `mixed_pointing_guard` is on). `mosaicmap` had already solved this for itself in v0.352.x by folding onto a 0.01° grid; the fold now lives in the engine as `fold_pointings` + `_cluster_distinct`, so all seven paths get it. On a 9-panel, **5,477-sub** mosaic (441 distinct cells): `pointing_groups` **1.152 s → 0.012 s** (96×), `detect_mixed_pointings` **2.650 s → 0.021 s** (126×) — ~3.5 s off a stack (three calls), and one call off every scan and two Target-page endpoints. **Nothing moves:** 0.01° is 25× below `PANEL_LINK_DIST_DEG` and 300× below `LINK_DIST_DEG`, every input index gets its own cell's label, `eligible`/`weights` are summed per cell, and the mixed-pointing verdict carries each cell's true sub count and true summed unit vector so `majority`/`others`/`separation_deg` stay the unfolded numbers. Verified by sweep — **664 configurations** with panel separations straddling both link distances exactly, zero mismatches against the rule spelled out on `cluster_pointings`. Two rails (a link distance near the grid, and an already-distinct set) fall back to the exact clustering. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.374.6** — Backlog curation, measured not guessed (no code change): **the standing "the Library page walks the library twice per refresh" perf watch item is closed — it costs ~196 ms, so caching it would buy nothing and risk a stale cleanup list.** The entry (filed with v0.319.3–4) asked for exactly this before anyone added a `registry_cache` layer. Built the owner's own shape — 6 targets / ~25k frame rows, the confirmed `M 3` + `M 3_SUB` duplicate pair at 5,477 + 5,455, the genuine `NGC 6888` two-folder pair at 4,815 + 3,110, and a mosaic pair, all plate-solved so both endpoints actually do their confirmation work — and timed the two endpoints the page polls together: **cleanup-suggestions ~106 ms, merge-suggestions ~105 ms, one refresh ~196 ms**, against `/api/targets` at 2 ms. Half of that is the duplicated walk, so the whole prize is ~100 ms on a page that is not polled in a loop — well under the staleness bug the entry itself warns the cache would introduce. Entry cut to [`SHIPPED.md`](SHIPPED.md) with the method, so nobody re-measures it.
- **v0.374.5** — Coverage gap, test-only: **every read-only endpoint is now pinned to *answer* on a brand-new install and on a target that has never been stacked.** Those two states are the ones a beginner meets first and the ones the suite tested least — nearly every `tests/webapp/` test builds, solves and stacks a library before it asks anything — so a divide-by-zero-frames or an `[0]` into an empty run list would have surfaced first on somebody's first evening. `tests/webapp/test_first_run_endpoints.py` sweeps **90** endpoints enumerated from the app's **own OpenAPI schema** (52 parameterless + 38 per-target), so a route added next month is covered the day it is added, and asserts only *no 5xx* — 404 and 422 are honest answers here, and each endpoint's own tests pin what it should say. Guarded against rotting into a vacuous pass: each sweep asserts a floor on how many paths it found, and a third test points the helper at a deliberately-crashing route and requires it to report exactly that one. All 90 answer on `main` today — a net, not a fix. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.374.4** — Friendliness / trust (PRIORITY 3): **the sensor-defect census stops printing a healthy sensor's share as "0.000%", and stops saying "1 hot or dead pixels".** `defect_note` formatted the share as `:.3f`, but the band a *healthy* sensor lands in is below what three decimals can show — `seestack.calibrate.defects` puts real sensors at 1e-5..1e-3 of the sensor (0.001 %–0.1 %), so ten broken photosites on the Seestar's 2 MP sensor (0.00048 %) printed as **0.000%**, which reads as a broken readout on exactly the masters worth reassuring about. New `_defect_share` says **"less than 0.001%"** below the cut — the same words and the same cut `skyCoverage.formatSkyFraction` already uses for the identical problem, so the app has one voice for "too small to print" rather than two. And the singular case is spelled out (*"1 hot or dead pixel"*, *"one of the camera's photosites is broken"*, *"repair it"*), because a sensor with exactly one bad photosite is a real and good outcome. Measurement, refused-map warning and the clean-sensor silence untouched; 2 tests fail before. Copy only. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.374.3** — Trust / friendliness (PRIORITY 3), honesty core: **the broken-pixel repair offer names its exception before the click, not one click after.** `calibration.defect_repair_offer`'s **on**-state carried a careful guard — a target that pressed *Save as defaults* between v0.367.0 and v0.374.0 has an explicit `repair_sensor_defects: false` in its own blob, and a blob wins over `default_stack_options` in both readers, so the copy counts those targets (*"…except 1 target"*). The **off**-state, the one the reader acts on, made the same universal claim (*"for every stack, including the hands-off ones"*) with no guard, and only revealed the exception *after* the button was pressed — the v0.374.2 shape again: two states of one fact, and the one read first was the wrong one. `n_overridden` now qualifies both, in each one's own tense (*"— 1 target would keep its own setting"*, with the why and the how-to-include in the tooltip), and the router's walk is gated on `_offer_wanted` alone rather than on the switch being on: a library with nothing repairable still never pays for it. Reachable on a live in-place upgrade precisely because v0.374.0 deliberately does not migrate existing blobs. Three tests fail before. No config/schema/on-disk/default/response-shape change. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.374.2** — Friendliness (PRIORITY 3) with a correctness core: **the Stack form's streaked-frames caution stops advising a setting that cannot work.** `Stack.tsx`'s hand-written `rejectionOn` — `(auto_reject && n>=3) || (sigma_clip && n>=4) || (min_max_reject && n>=3)`, a copy of the *dispatch* gates — meant that on a **1–2 sub** stack every term was false whatever was ticked, so the form told a user whose sigma clipping was on by default that *"this stack has no per-pixel rejection enabled"* and offered a button to turn on the setting that was already on and cannot run at two subs, while `rejectionReachNudge` said the opposite two inches away. The predicate is gone: `rejection_reach` gains an additive **`best_available`** (the same engine helper asked with `auto_reject`/`drizzle_reject` set — "could *anything* take a lone trail out at this depth?", sized by a mosaic's `panel_depth`), and the new pure `streakRejectionAdvice` decides the sentence from it. Where a method reaches it names **Auto outlier removal** (honest at every depth, unlike sigma clipping — the same correction v0.323.1 and v0.334.1 made on two other surfaces) with the one-click fix, or drizzle's own rejection on the drizzle path; where nothing reaches it names the sub count needed and offers **no button at all**. The two halves now split one question — `rejectionReachNudge` owns "you asked for rejection, will it reach?", this owns "you asked for none, should you?" — so they cannot contradict each other; `minMaxRejectHint` still supersedes on the 3–10 band, pinned by a test. Additive response key only; no config/schema/on-disk/default change and the peak is provably unmoved. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.373.0** — Friendliness / "enjoy + come back tomorrow" (PRIORITY 3), a **new beginner feature**: **the Dashboard finally says how many of the 110 Messier objects you've photographed, and links to the life list.** `/life-list` has existed since v0.279.0 and nothing on the home screen ever pointed at it, so the number that is its whole hook was one nobody saw. New read-only `GET /api/life-list/counts` serves *just* the tally through the same `life_list_summary` over the same `catalog_capture_status` the full route uses — a test asserts the whole counts block is byte-identical between the two, so the Dashboard sentence and the life-list page's header can never disagree — and it is a separate route because the Dashboard asks on every visit while the full response carries ~160 catalog rows plus a preview stat per captured target (a `Dashboard.test.tsx` case pins that `getLifeList` is never called). **The IA rule decided its shape:** not a seventh stat tile (the grid is `lg: 6`) and not another card, but one quiet line in the same grouping as the sky-coverage read-out, whose own comment already says *"a new fact joins a grouping instead of becoming one more block"*. Pure `components/lifeListLine.ts` owns the words and changes the tail with how far along you are — plain count → "over halfway" → "just N to go" → "the whole list" — and refuses a nonsense tally rather than printing one. **Self-hides at zero captured**, so a fresh install never meets a 0-of-110 scoreboard. Additive/read-only; no schema, config, on-disk or default change, and the line stays absent against a backend without the route. Ships slice (i) of the life-list follow-ups; (iii) share-the-grid stays open.
- **v0.372.1** — Maintainability in service of correctness (no behaviour change): **one shared *real* display-space fixture, `tests/displayspace.py`, plus the guard-on-the-guard that stops a fixture silently ceasing to test anything.** A1's sting was that the regression test written for that exact defect in v0.210.6 **passed while the bug was live** — its fixture was `clip(sky + noise)`, which has no hard shadow clip, and the shadow clip *is* the bug. `real_stretched_stack` / `sky_truth` / `clipped_fraction` / `assert_shadow_clip` now live in one place; `test_edit_curve.py` reads them instead of its own copy and `test_edit_levels.py` gained the real-fixture pair the entry asked for. **Measured on the way:** `suggest_levels_points` returns **black = 0.0** on genuine `autostretch` output (its 1st percentile lands inside the 1.08 % zero spike) where the synthetic fixtures return 0.05–0.13 — correct, but not what those fixtures describe, so it is now pinned; `measure_sky_cast` was probed on the same fixture (deviation 0.00035, neutral) and cleared rather than migrated. Degenerate/flat fixtures deliberately left alone. Ships the ⭐ maintainability idea filed 2026-09-02; working in [`PROCESS-NOTES.md`](PROCESS-NOTES.md).
- **v0.372.0** — Autonomy + trust (PRIORITY 2/3): **a target stops silently ignoring your global settings — the Stack form now names every saved option that overrides them.** "Save as defaults" persists the *whole* form, so a target saved months ago carries an explicit value for every option that existed that day (a string of `false`s for checkboxes nobody opened), and its blob wins over `default_stack_options` in **both** readers — the form's seed and `pipeline._stack_target(auto=True)`. A switch flipped globally afterwards therefore never reaches that target, for ever, with nothing saying so; v0.371.0 hit exactly this with `repair_sensor_defects`. New pure `walkaway.pinned_stack_options` + read-only `GET /api/targets/{safe}/stack-defaults/pinned` + a self-hiding note inside the form's existing flow (no new page, no banner) name each pinned option and both its values, with a one-click **"put my global settings back in the form"** that saves nothing — *Save as defaults* stays the reviewable moment. **The baseline is what makes it honest:** comparing against `default_stack_options` alone fired on *every* target that had ever pressed Save (`get_stack_defaults` seeds a never-configured form with `auto_reject: True` while the descriptor default is `False`), so it compares against `_merge_stack_defaults(settings, None)` — the seed this very form would have been given — extracted from `get_stack_defaults` so the two can't drift. `_same_option_value` keeps `False == 0` from glossing a type change as agreement while `3`/`3.0` still compare equal. Shape (a) of the ⭐ lead; (b) save-the-delta and (c) drop-stale-keys stay open with their care notes. No behaviour change to any merge. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.371.1** — Image quality / data integrity (stacking-engine-class per §1): **amp glow read as broken photosites — `find_sensor_defects` flagged healthy pixels wherever the sensor was legitimately noisier.** The threshold was `DEFECT_SIGMA` × the MAD of the residual over the *whole* CFA plane, but a master dark's noise is not stationary — amp glow is dark *current*, which carries shot noise, and the glow corner is a small fraction of the sensor, so the plane-wide MAD is set by the quiet bulk and the bar sits below the glow's own grain. Measured on a master built the way the camera builds one (mean of 20 Poisson+read-noise frames) with **every photosite healthy**: **133 flagged at 2,000 e⁻ of corner glow, 1,564 at 20,000** — each then overwritten from its neighbours on every sub of every stack, and reported by the v0.370.0 census as broken pixels in the owner's camera. It survived 20+ tests because the existing fixture adds read noise of *one fixed sigma everywhere*, so its glow is a change of level only; the new `_shot_noise_dark` fixture is what catches it. Fixed by `_local_robust_scale` — an upper percentile of |residual| per 16×16 block (a MAD under-reads it nine-fold, because in a steep gradient the local median lands on the centre sample itself) — with the threshold as `sigma × max(plane_wide, local)`, so it can only ever **rise**: the new map is a provable subset of the old, and a clean stationary master's answer does not move. **P80 and not higher is set by the refusal guard** — at P90 a master with a tenth of the sensor spiked stops being refused and starts being repaired. After: 0 false positives at every credible glow with all 12 planted defects still found. Opt-in feature, no default flipped. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.371.0** — Autonomy + friendliness (PRIORITY 2/3): **the v0.370.0 sensor-defect census gets its button — one click repairs the broken photosites on every future stack, including the hands-off ones.** The census named `repair_sensor_defects`, but naming is not reaching: it is a checkbox in the Stack form's *advanced* group, so acting on the line meant opening a collapsed disclosure to find a setting by name — once per stack — and the walk-away chain (`_stack_target(..., auto=True)`) sees no form at all. New pure `calibration.defect_repair_offer` + `POST /api/calibration/defects/repair` write the option into the **global `default_stack_options`**, the one place both `get_stack_defaults` (the Stack form's seed) and the unattended merge read — pinned by a test asserting it through `GET .../stack-defaults`, the reader itself. **Silent unless some master reports defects a repair could actually fix**, so a clean sensor and a *refused* map (where the switch would repair nothing) both offer nothing; and no count is quoted, because which master supplies the map depends on what is bound at stack time. **And the on-state stays honest about the one case that would make it false:** "Save as defaults" persists the *whole* Stack form, so a target saved before this existed pins `repair_sensor_defects: false` in its own blob and wins over the global — the copy counts and names those targets (*"…except 1 target"*) and says how to include one, and the per-target walk is only paid for when the switch is on *and* something is repairable. Exactly reversible from the same control — off *removes* the key, leaving the options blob byte-for-byte as it was. Read-modify-write is server-side, so a click cannot clobber another default. No pixel moves, no shipped default flipped. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.370.0** — Autonomy + friendliness + image quality (PRIORITY 2/3/4): **"does my camera have broken pixels?" — the Calibration page answers it, and names the one switch that fixes them.** `repair_sensor_defects` (v0.367.0) repairs exactly the broken photosites from the master dark, but it is an *advanced* Stack-form checkbox, off by default, and nothing anywhere told the owner either that their sensor has broken pixels or that the repair exists — so in practice it was invisible. New `defects.census_sensor_defects` (the per-phase measurement extracted into `_candidate_mask`, so `find_sensor_defects` is unchanged) reports the count **and** whether the map was refused — the two cases the repair path deliberately collapses — served by a read-only `GET /api/calibration/defects` over every *pedestal* master (dark/bias; a flat is never censused) and rendered as one self-hiding line inside each master's existing name cell: the count plus the switch's exact label, or a yellow "too many pixels read as broken to repair from this one". **A clean sensor says nothing** — no action, no line. The number is pinned equal to `CalibrationMasters.load`'s own `n_sensor_defects` on a master with a no-data patch, so screen and stack can't describe two sensors; cached per file identity (a master FITS is immutable once written). No pixel moves, no default flipped. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.369.4** — Calibration / data integrity (stacking-engine-class per §1): **a no-data hole in a master invented sensor defects around itself.** `defects.find_sensor_defects` filled every `exclude`d (sanitized-to-0) sample with the *whole plane's* median before taking the local median, so inside amp glow the fill read as a defect **and** dragged the 5×5 baseline of the real photosites beside it — 115 flagged pixels (48 inside the hole) on a believable master with an 8×8 hole, each overwriting a good sample on every sub. Now filled from `_local_fill` (local mean of valid samples over `_FILL_WINDOW`), the MAD is measured over valid samples only, and `flagged &= valid` enforces the docstring's promise; a genuine hot pixel beside the hole is still found. Gated (opt-in `repair_sensor_defects`, imported masters only) and bit-identical for a master with no non-finite pixels. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.369.3** — Editor / one-click Auto (PRIORITY 1): **Adaptive Auto's first type-scoped nudge moved one *bucket*, not one step.** `auto_prefs.record_feedback` started a fresh `by_type` override at neutral, so with a global `brightness=+2` one "too bright" tap on a galaxy landed at **−1** — a three-step jump past neutral — and `+1` was unreachable, the taste oscillating between `+2` and `−1` forever (a per-type 0 was dropped, handing the parameter back to the global set). Now a type-scoped tap seeds from the aged global bias and moves one step, and a per-type 0 is *stored* while a non-zero global sits underneath it (`_coerce_bucket`/`_bucket_biases` `keep_zero`, `by_type` only; a bias that merely *faded* to 0 still falls back as before). Found by auditing the brand-new v0.369.x code. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.369.1** — Data integrity / calibration trust (treated as stacking-engine-class per §1): **the one-click discover→build path stops combining the frames its 4-header sampling missed.** `discover.classify_folder` confirms a folder's kind from `SAMPLE_HEADERS` (4) evenly-spaced headers, but `masters.build_master` then combined *every* shape-matching FITS — so a twelve-file folder whose sampled positions all read "dark" but which also held two lights built a "master dark" out of both (reproduced: 4 darks at 10 + 2 lights at 900 → a master averaging >300), and a contaminated master is subtracted from every frame it is later applied to. The shape rule can't catch it (same camera, same shape) and `header_kind_note` only *captions* it. New `build_master(require_declared_kind=...)` drops a frame declaring a different slot (reason `"wrong kind"`, already rendered by the Jobs page's `skipped_buckets`), **keeps** a frame that declares nothing and a flat-dark in the dark slot (reusing the now-public `discover.KIND_TO_MASTER`), and runs **before** the majority-shape vote. Default `False` ⇒ the manual build a user aimed at a folder is unchanged. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.369.0** — Editor + autonomy (PRIORITY 1/2), the last remaining sub-part of the ⭐ owner-requested **Adaptive Auto** ask: **recency decay — "recent feedback weighs more", which the original spec asked for and no slice had built.** A bias was permanent: three "too dark" taps saturated `brightness` at `+3` for the life of the library unless the owner found the opposite chip three times or reset the whole profile. Now a bias fades **one step per `DECAY_DAYS` (90)** without reinforcement (`auto_prefs._faded`), never crossing zero into the opposite taste, reading a future stamp (clock skew) as "just now"; decay applies at read time *and* before a new tap, so a tap builds on the taste actually in force and restarts that parameter's clock. **The fade is never silent** — new `steps_faded`/`fade_note` and an additive `AutoPreferencesOut.fade_note`, rendered in `AutoFeedback.tsx`, explain both a partial fade and the full one (where the "why Auto shifted" note would otherwise just vanish). **Upgrade-safe by construction:** decay needs a `stamps` entry, and a profile written before this shipped has none — it never fades and reads byte-for-byte as today. Slice **(b) is now complete**; only the spec's *"optional later"* slice (c) remains. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.368.0** — Friendliness + autonomy (PRIORITY 3/2): **"Was last night off for you?" — the newest night's star size against the owner's own usual, so dew / a wrong focus / a bad-seeing night is caught the morning after instead of weeks later in a mushy stack.** The app only ever trended FWHM *within* a session (`session_recap.focus_trend`, early third vs late third), which is structurally blind to a night that was soft from the first sub. New pure `activity_calendar.off_night(nights)` sits beside `sharpest_night` and reads only what `finalize_calendar` already folded — the Dashboard heatmap's cached per-night median FWHM — so it costs no extra library walk and shares one definition of "that night's star size". Silent unless the latest night is ≥1.30× the **median of the per-night medians** of ≥4 *earlier* qualifying nights, and never a diagnosis (seeing is not a fault: it names causes and asks the owner to look). Self-hiding `OffNightCard` in the Dashboard's existing **Recent** group beside `LastNightCard`, on the shared `["activity-calendar"]` key. Slice (b), the season-long sparkline, deliberately not built. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.367.1** — Stacking-engine hardening (PRIORITY 1 current focus), the traced-but-unreachable batch under "Bugs" drained in one pass, each with a fail-before regression in the new `tests/test_engine_defensive_guards.py`: `align.py`'s sub-pixel cap rewritten as `not (abs(dy) <= CAP and abs(dx) <= CAP)` at **both** sites, so a NaN shift reads as "too large" instead of slipping through every comparison and letting `nd_shift` wipe the frame; `weighting.py`'s FWHM ratio computed in `np.float64` so a pathological `fwhm_px` saturates to the 1.0 the formula already wants rather than raising `OverflowError` and sinking the run; `reference.py::pick_central_frame` filtering on `math.isfinite` to match `pointings.py`, so a NaN centre can't be picked as the whole stack's reference; `storage.py::prune_stack_runs`'s two closes nested like `get_storage`'s; and `solve/runner.py`'s "so it stops being re-offered" comment corrected to what the branch actually does (`build_solve_arglist` deliberately keeps offering a `solve_failed:` frame, which is right — an unreadable sidecar is usually transient). `align.py::extract_reference_patch`'s all-NaN fallback was found **already fixed** and struck. No behaviour change on any reachable input.
- **v0.367.0** — Image quality (PRIORITY 4) + calibration autonomy (PRIORITY 2): **repair the sensor's broken photosites from the master dark, in the raw Bayer domain, instead of relying only on the blind post-debayer local-median filter.** New pure `seestack/calibrate/defects.py` — `find_sensor_defects` measures each **CFA phase** against its own local median (so amp glow, a gradient and a per-phase offset all flag zero) and refuses any candidate set past 2 % of the sensor; `DefectMap` precomputes the same-phase neighbour gather once at load so the per-frame cost scales with the *defects*, not the canvas. `CalibrationMasters.apply_raw` repairs after the pedestal subtract and before the flat divide, so a hot site is erased while it is still one pixel and **a star can never be touched** — the map is measured on the dark. `StackOptions.repair_sensor_defects` is **off by default** and off measures nothing (§9); `DEFECTPX` → `sensor_defects` → one History line when it did something. Still open: validate the map's population on a real Seestar dark before anyone proposes defaulting it on. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.366.1** — Autonomy + friendliness (PRIORITY 2–3): **the "you already have darks" answer reaches the screen where the gap is actually noticed.** `_uncalibrated_advice` (the History Info panel's "why did this come out uncalibrated?" line) was silent in exactly the beginner case — no usable master in the library at all — because `diagnose_uncalibrated` only explains a *near-miss* master. It now falls back to `calibration.incoming_calibration_advice`, which names the frames sitting in `incoming/` ("You already have 40 dark frames in your incoming folder (“MyDarks”)"). The folder walk is the shared `cached_incoming_folders`, run only when there is no master-derived advice; `folder_as_master` shapes a discovered folder like a registry entry so "would this cover my subs?" is answered by the same `existing_master_like` that answers "does a master I own cover them?" — one definition, so the advice can't send anyone off to build a 30s dark for 10s subs, and a folder already built into a master says nothing. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.366.0** — Autonomy + image quality (PRIORITY 2/4): **"you already have darks" — the app notices calibration frames sitting in `incoming/` and builds the master in one click.** `seestack/calibrate/discover.py` confirms a folder from the **frames' own `IMAGETYP` cards** (`frame_kind_from_header`), never from the folder name — the naming-convention gate the entry refused to guess at simply stops mattering, and a camera that writes no card gets silence rather than a guess. `GET /api/calibration/incoming` + `POST /api/calibration/incoming/{id}/build` (folder re-resolved server-side from a sanitised id), `existing_master_like` reusing the unattended binder's own confidence bar so a covered folder says "you already have this one", and a self-hiding `IncomingCalibrationCard` inside the existing Calibration page. Offers only; builds nothing until asked and applies nothing after. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.365.0** — Image quality/trust (PRIORITY 4): **a finished picture says whether its rejection pass could have clipped anything, and the History Info panel stops calling a blind pass clean.** The stacker stamps `REJDEPTH` (samples on the deepest pixel — the literal peak, so "no pixel could be clipped" is provable), `REJNEED` and `REJREACH` beside the existing `REJ*` block; `lone_outlier_min_depth(mode, sigma_kappa)` is now the one definition of that bound behind `rejection_reach`, `stackhealth`'s `rejection_blind` note and the cards, and takes both the `"drizzle"` and `"drizzle-reject"` spellings. `rejectionSummaryText` claims *"data was already clean"* only when the run's own header says the pass reached — a thin mosaic panel now reads *"not enough subs on a pixel for it to reach"*. Deliberately no second paragraph: `StackHealthCard` already carries the explanation and the cure on that same page. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.364.0** — Friendliness (PRIORITY 3): **the "why were some frames left out?" breakdown gets a home a phone can reach, and its advice gets a button** — `RejectionBreakdownCard` in the Target page's existing Quality insight group (the breakdown had only ever rendered in a `HoverCard.Dropdown`, which has no touch affordance at all), plus `rejectionActions.ts` turning each bucket/verdict into the thing its note names — `settingsLink("plate-solving")` or the page's own Plate Solve — keyed off a new additive `verdict.key` from `webapp/rejection_summary._verdict` rather than matched on the copy. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.363.0** — Autonomy/friendliness (PRIORITY 2/3): **"First look" reaches the Dashboard** — the sharpest accepted sub of the target that has kept subs but no picture yet (`FirstLookStrip` + `pickFirstLookTarget`, inside the existing Recent insight group, self-hiding on a settled library), so the "did tonight work?" glance is answered on the landing page and not only on the Target hub. Entry in [`SHIPPED.md`](SHIPPED.md).
- **v0.362.0 + v0.362.1** — Friendliness/autonomy (PRIORITY 3): **the "Your first image" checklist carries the whole journey — finish it in the editor, then save that version.** The card walked a beginner to their first stack and stopped, congratulating them on a linear, flat, dark picture and *mentioning* the last two steps in a sentence, because nothing cheap reported them. `_rollup_stacks` now also counts runs carrying a saved editor recipe and runs whose edit was exported (one `project_meta` prefix scan each on a project it already opens), served as additive `n_edited_runs` / `n_finished_pictures` — the second one the **union** of the export marker and the in-place auto-edit's `preview_display_space`, because a hands-off "Process this target" finishes the picture without any export and the first cut of this asked a walk-away owner to go and do it again (caught by booting the app with `scripts/agent-dogfood.sh`, not by reading it). The filed care note was answered with a measurement: **1.11 ms for both scans on a 400-run / 1,400-meta-row target, against 11.15 ms for the run walk already being paid there**, behind the existing 30 s cache — and a target with no stack runs is never asked (test spies on `iter_meta_prefix`). The card's "never show on an established install" guard moved to a new `firstImageHasPicture` (the four first-picture steps only), so adding steps cannot make the owner's box look mid-journey and pop a card onto a Dashboard it has never appeared on. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +4 `tests/webapp/test_stats.py`, +5 vitest (8 updated).
- **v0.361.1** — The other half of v0.361.0, and the surface its follow-on actually named: **the Tonight page's "Worth more time" list carries the same mosaic aim clause.** "Plan a night" is where a beginner decides where to point, and it renders its own `WorthMoreTimeList` off the same `/best-tonight` answer the Dashboard card uses — so shipping only the Dashboard left the where-to-point hint off the where-to-point page. The pure helper and the query moved into one `hooks/useMosaicAim.ts` that owns the three decisions both surfaces must agree on: the shared `["mosaic-map", safe]` cache key (no second request, and no way to name a different panel), the **lead pick only** (this list runs to eight rows), and `retry: false`. The map fixture moved out of `useMosaicAim.test.ts` into `test/mosaicMapFixture.ts` — importing a test file was registering its suites in the importing file and running those assertions twice. Frontend-only; no engine, API, schema, config, on-disk or default change. Tests: +4 `WorthMoreTimeList.test.tsx`, 2 moved.
- **v0.361.0** — Autonomy/friendliness on the owner's dominant workflow, and the follow-on v0.355.0 deliberately left open: **"Point here right now" now also says *which corner* of the mosaic.** The Dashboard's one recommendation answers *which target*; for a heavy mosaic user that is half the question, because a 3×3 whose total looks healthy can still have one corner at a fifth of the others, and pointing at the mosaic again spreads the night evenly over panels that don't need it equally. New `seestack.mosaicmap.aim_hint` says the map's own fact in one clause — same `panel_position_words` and `sharecard.format_duration` the long card sentence uses, so the app keeps one vocabulary for where a panel sits and how long an integration is rather than growing a second spelling per surface. Served as an additive, defaulted `aim_hint` on `MosaicDepthMapOut`; `PointHereTonightCard` reads it for the **lead pick only** (three project reads to annotate rows nobody is being told to shoot is a cost with no reader) through the Target page's own `["mosaic-map", safe]` cache key, so the two surfaces share one entry and can never name different panels. Silent on a single field, on an even mosaic, on a failed request and against a backend too old to send the clause — the frontend never rebuilds the sentence locally. No config, schema, on-disk, default or existing-field change. Tests: +4 `tests/test_mosaic_map.py`, +2 `tests/webapp/test_mosaic_map.py`, +7 `PointHereTonightCard.test.tsx`.
- **v0.360.0** — Understand/enjoy/trust, and the one gap two independent greps agreed was all that was left: **the Target page now offers "Compare with my last one".** `/compare` has been a full bookmarkable A/B route — split slider, per-side provenance, plain-language verdicts on noise, panel flatness and night count — since v0.150-ish, with entry points from the Gallery and per-row in History; a beginner who never opens History never discovered any of it, and *"is my new picture actually better than last week's?"* is asked from the Target page. New `CompareWithLastCard` is one link and nothing more, and it joins the existing **Story** tab beside the deepening reel (which answers the same question as an animation and self-hides on the same condition), so the page gains no always-on control. Pure `pickCompareWithLast` skips a run with no picture and an **editor export** — pairing one of those with the stack it came from answers "did my edit change anything?", which the editor already answers, not "did another two nights help?" — with `undefined` counting as genuine so an older backend is unchanged. The URL moved into one shared `sameTargetCompareHref` that History's Compare button now delegates to, so the two surfaces can't disagree about where the link goes. Frontend-only; no API, schema, config, on-disk or default change. Tests: +6 `compareWithLast.test.ts`, +4 `CompareWithLastCard.test.tsx`, +1 `Target.test.tsx`.
- **v0.359.0** — Friendliness, and the closing half of the v0.308.0 North-up follow-on: **Compare can turn both pictures North-up at once, so a Split or a Blink actually lines up.** The Seestar is alt-az, so two nights on one object land at different field rotations — which is precisely why scrubbing the split divider between them can be hard to read. The Gallery lightbox half was already built; Compare needed a different predicate, because on a *pair* the question isn't "would the turn do something?" but "would the turn leave the two agreeing?". Pure `compareNorthUpOffer(a, b)` offers the toggle only when at least one side has a rotation to apply **and** neither side is a run with no usable orientation (`directions` null) — turning one side of a pair whose other side can't turn makes the two agree *less*, so that case stands down. Reuses the shared `NorthUpViewToggle`, its `localStorage` key (off by default, remembered per viewer) and the `["annotations", safe, run_id]` cache the Target hero and the lightbox already warm. A view, not a save: nothing on disk changes. Tests: +11 `Compare.test.tsx` (5 on the helper, 6 driving the page).
- **v0.358.2** — Process/leverage, the second and last half of **R2**: **446 resolved entries (16,223 lines) were cut out of "Ideas" and appended verbatim to [`SHIPPED.md`](SHIPPED.md)**, taking this file from 29,432 lines to 13,207 — under half, and a third of the 40,915 it stood at before R2 began. Same shape rule as the "Bugs" move (struck through, or "✅" in the entry's first three lines), plus one carve-out: an entry whose own text names an open follow-up was **left here**, so the move cannot hide live work behind a resolved header — 28 entries, each now a small, safe split job. Losslessness verified line-by-line before the cut. **Grep [`SHIPPED.md`](SHIPPED.md), not this file, for anything already built.** One pointer line rather than 446, for the same reason the "Bugs" move gave.
- **v0.358.1** — Verified bug (found and reproduced while shipping v0.358.0), image/trust correctness on the file a beginner shares: **a picture that was *processed* and then saved North-up mis-measured itself.** `_unrotated_preview_size` recovers "how wide was this preview before the turn?" from the **master FITS** — i.e. the *canvas's* preview grid — but a "Process target" preview is a **crop** of the canvas, rendered off the ≤1500 px edit proxy and then capped at 1024 px, so it is neither that grid nor a fixed fraction of it. Both states land on one run through `_save_processed_preview(north_up=True)`, which is the owner's own workflow. Measured on a 1000×800 canvas trimmed to 70 %: the **shared JPEG's scale bar was drawn 1.43× too long — 10.2′ of sky under a "5′" label** — and the **wallpaper/zoom clip re-centred by the same ratio** (target pixel at 14.3 where the object was at 10.0). New `_unrotated_stored_preview_size` stops guessing the grid: it takes the crop box's shape and the stored PNG's size, turns the box with the renderer's own `follow_north_up_turns`, and reads the decimation off the ratio — scale-free, and through the same transform the picture took, so the `rot90` snap can't make them disagree. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +4 `tests/webapp/test_preview_crop_geometry.py` (the wallpaper one fails before with exactly that pair).
- **v0.358.0** — Friendliness/trust, and the decision the entry demanded first: **the scale bar and the compass survive a "North up → Save".** The shared JPEG has baked both onto exactly those pixels since v0.284.0 while the card it was shared from said neither could be placed — a screen↔file disagreement, not a missing feature. **Decision recorded (option b): the Moon sentence answers for the *field* the telescope saw, not for the frame.** The crop precedent's mechanism is "measure the visible rectangle" but its stated harm was *overstating the field*; on a turn those diverge, and re-measuring on the grown canvas would overstate what the owner shot by the growth factor. So `frame_arcmin`/`moon_comparison` stay the kept rectangle's, only `fraction` is re-based, and History's line says which rectangle it means (*"…that's the sky you captured; the black corners the North-up turn added aren't counted."*). `_turned_preview_grid` gives the pins, the bar and the rose **one** geometry (still the renderer's `follow_north_up_turns`); the payload gains `preview_directions` and widens `preview_scale_bar`; `storedPreviewScaleBar` takes it, so the copied caption gets its scale clause back. Pinned against `_sky_marks_for_run`'s own `bar_px`/`directions`, so file and screen can't drift. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +8 `tests/webapp/test_stack_annotations.py`, +5 vitest (1 rewritten).
- **v0.357.1** — Friendliness/housekeeping, the follow-on v0.357.0 left: **the prepared full-size download is disk the Storage page can name, and delete.** The archive lives outside the library in `<data_root>/exports/` and is easily gigabytes, so the page whose whole job is "what is using my disk?" walked straight past it. `StorageResponse` gains an additive, defaulted `exports_bytes` (same best-effort `_dir_bytes` as every other figure) and `DELETE /api/gallery/pictures-archive` gives the space back — idempotent, sweeping a stale `.part` with it, and scoped to the two paths the module owns so it cannot reach the library or `incoming/` (§10). The row self-hides at 0, which covers every install that never presses the button and any older backend. Tests: +3 `tests/webapp/test_pictures_archive.py`, +2 `Storage.test.tsx`.
- **v0.357.0** — Get/share + trust, and the honest end of a limitation the app already admitted in its own copy: **"Full-size versions" — every finished picture at print size, in one archive.** `/api/gallery/pictures.zip` streams each target's stored *preview* (capped at 1024 px by `_write_preview_png`), which the card has said since v0.308.1 is *"right for a phone album, not for printing"* — leaving one route to a printable backup: open every target and press **Full-res PNG**. It cannot be a second query parameter, because a target's native-resolution picture has no file on disk (it is rendered from the master FITS plus the run's saved recipe), so `POST /api/gallery/pictures-archive` submits a **`pictures_archive` job** with progress and cancel and `GET …/pictures-archive/{job_id}` hands over what it built — the editor's own submit-poll-download shape. The *which render* decision moved into one shared `pipeline.render_run_full_res_png` used by both callers, so an archive member is byte-for-byte the PNG that run's own button serves (pinned by a test); member naming moved to `picturesarchive.unique_entry_name` for the same reason. A pruned master falls back to its preview and the archive **says so** in `_preview_size.txt`; an unreadable picture lands in `_skipped.txt`. One archive at a time in a new `<data_root>/exports/`, written `.part`-then-rename, cancel leaves nothing, peak memory one picture. Nothing the user owns is written — no run, no preview, nothing in `incoming/` (§10), pinned by a snapshot test. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +11 `tests/webapp/test_pictures_archive.py`, +2 `MyDeepSkyWallCard.test.tsx`, +1 `Jobs.test.tsx`.
- **v0.356.2** — Follow-through on v0.356.0, from driving `header_kind_note` adversarially rather than reading it: **the note stops relabelling the owner's own frames, and stops being able to 500 the Calibration page.** A folder of flat-darks in the dark slot is correct, but was confirmed as *"All 40 frames say they are dark frames"* — they said flat-dark; a tally whose kinds aren't exactly the slot's now echoes what they actually said, biggest group first, with the single-kind wording untouched. And the tally comes out of the registry's own JSON, which nothing validates on read: a hand-edited string or list raised `AttributeError` inside `list_masters` (the whole page, not one row), and an unrecognised key was echoed verbatim as *"3 say they are xyz frames"*. Both now degrade to silence, the same answer the function already gives for "no frame said". Neither was reachable from the app's own writes — the function was correct for its producer and brittle for its store. Tests: +3 `tests/webapp/test_calibration.py`.
- **v0.356.1** — Autonomy + image quality, the other half of v0.356.0: **the Stack form says it too, where the master is actually used.** The form already checks whether a master *can* be applied (size, colour phase, exposure, temperature) but never asked what it is made of — and a master dark built from a night's subs passes all four, then subtracts a picture of the sky out of every frame. One pure `pickedMasterContentWarnings` over the four picked slots renders the server's own `header_kind_note` sentence as **one** orange alert (red on this form means "stacking will fail", and this stack succeeds — which is the problem) above the size/phase blockers (not four), first, because it is the only one of them that ruins the picture silently instead of failing loudly. Conditional on something rare — a master whose frames declared a kind *and* disagreed — so a confirmed-good master, and every master built before v0.356.0, add nothing to the form; pinned by its own test. Frontend-only, no API/schema/default change. Tests: +4 `calibrationFit.test.ts`, +2 `Stack.test.tsx`.
- **v0.356.0** — Autonomy + image quality: **a master calibration frame now says what its own frames claimed to be.** The Calibration build form takes a folder path in a text box and a kind from a dropdown, and nothing checked the two agree — point it at a night's subs with "Dark" selected and the app built a "master dark" out of light frames, registered it as a success, and every stack it touched then had a picture of the sky subtracted out. New `seestack.io.fits_loader.frame_kind_from_header` reads the standard `IMAGETYP` card **one-sidedly** (an exact table, never a substring test — `'Dark Flat'` contains both needles and gets its own `dark_flat` answer; anything unrecognised or missing is `None` = *"this frame didn't say"*). `MasterMeta.header_kinds` tallies it over the frames that actually reached the combine, and one pure `calibration.header_kind_note` turns that into one sentence used by **both** the finished build job and the Calibration master list, so the two can't drift: *"All 40 frames say they are dark frames."* or *"…40 say they are light frames (your subs). This is not a dark master — delete it and point the build at a folder of dark frames."* Self-hiding when no frame carried a card we recognise, which covers a camera that doesn't write one **and** every master built before this version. Read-only: nothing gates a build, filters a folder, or classifies anything at ingest — that was step (3) of the lead and stays undone. Ships step (2) of the `IMAGETYP` lead; full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +3 `tests/test_fits_loader.py`, +4 `tests/test_calibrate.py`, +9 `tests/webapp/test_calibration.py`, +4 `Jobs.test.tsx`, +2 `Calibration.test.tsx`.
- **v0.355.1** — Friendliness / the owner's standing "extremely busy UI" priority: **the Dashboard stops recommending the same target twice, one card apart.** `PointHereTonightCard` and `ContinueTonightCard` sit directly above one another (`routes/Dashboard.tsx:390-391`), share a teal `IconTelescope`, and rank the **same** owned library by two different rules — best-placed-now × marginal noise gain (`/api/plan/best-tonight` → `rank_targets_now`) versus closest-to-its-goal (`pickContinueTonight`) — so on a beginner's library they routinely landed on the same target and printed it twice under two headings in two voices. `pickContinueTonight` gained an `alreadyRecommended` argument, filled from the sibling's own answer through the shared `BEST_TONIGHT_QUERY_KEY`/`MAX_SHOWN`/`REFRESH_MS` constants (a cache hit — no extra request, and the two can't drift). The pick moves **down to the next-best started target** rather than blanking, so a beginner with several targets gets a second, genuinely different suggestion; with one, the card hides and the Dashboard is a card shorter. Nothing removed. An older backend that 404s `/best-tonight`, and undefined/null/empty exclusions, all reproduce the previous pick bit-for-bit. Closes the *"Finish what you started"* idea as **already built** (that capability is `/best-tonight`); full write-up + the closed entry in [`SHIPPED.md`](SHIPPED.md). Tests: +3 `continueTonight.test.ts`, +3 `ContinueTonightCard.test.tsx` (all 6 fail before).
- **v0.355.0** — Friendliness/planning, on the owner's dominant workflow: **"Your mosaic, panel by panel" — a small map of where your mosaic is thin.** The readiness figure already scales a mosaic's goal by panel count, so it says *how much* is left; nothing said **where**, and a mosaic whose total looks healthy can still have one corner at a fifth of the others — grainier than the rest of the picture however good the total is. New `seestack/mosaicmap.py` clusters the accepted+solved subs with the engine's **existing** `pointing_groups` gate (so a single field, a tight dither and an unsolved target all show nothing, exactly as today), sums each panel's own integration, lays the panels out North-up/East-left from their real RA·cos(dec)/Dec offsets, and says one sentence: the thin panel named positionally ("thinnest at the bottom-right"), or a plain "nothing is being held back" when the mosaic is even. Median not mean, so two thin panels can't drag their own yardstick down; plus an absolute 5-minute shortfall so a young mosaic isn't nagged. `GET /api/targets/{safe}/mosaic-map` returns `null` for everything that isn't a mosaic and the card then renders nothing at all; it joins the Target page's existing **Planning** tab rather than adding a tenth stacked card. The card mounts with the page, so the O(n²) clustering was measured (2.2 s at the owner's 5,400-sub scale) and folded onto a 0.01° grid before clustering (0.06 s), with the fold's sizes carried into the gate by a new defaulted `pointing_groups(weights=…)` so there is still exactly one gate. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +15 `tests/test_mosaic_map.py`, +3 `tests/test_pointings.py`, +6 `tests/webapp/test_mosaic_map.py`, +11 `MosaicMapCard.test.tsx`.
- **v0.354.2** — Image-quality/parity: **the picture on screen stops being half a step darker than the picture you download.** v0.354.1 made the six exports in `stack/output.py` round; every *other* float→byte site still spelled `(x * 255).astype(np.uint8)`, which truncates — so from that version the editor's live preview, the gallery/History preview, the full-res preview render, the loupe, the star-mask overlay and the deepening reel were each up to a whole step darker than the PNG/TIFF written from the same display-space pixels. Fifteen sites now go through `output.pack_unit`, two of them *exports* the v0.354.1 sweep had missed because they live outside `stack/output.py`: `printexport.render_print` (the file that goes to a print lab) and `webapp.video._write_tiff16` (the Moon/Sun still). `THUMB_VERSION` deliberately **not** bumped — a ≤1/255 change does not justify re-rendering every cached thumbnail on the owner's install. Three test helpers that re-implemented the truncating pack in their own expectations were re-pointed at `pack_unit`, not loosened: each stays an exact `array_equal`. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +7 `tests/test_preview_rounding_parity.py` (all 7 fail before), including a grep drift guard over `seestack/` + `webapp/` so a sixteenth site can't appear silently.
- **v0.354.1** — Image-quality/correctness: **every file the app writes stops being half a step too dark.** All six float→uint packs in `seestack/stack/output.py` spelled `(x * MAX).astype(np.uintN)`, which truncates toward zero — a systematic ~½-step downward bias on every PNG, JPEG and TIFF, and a break of the reversibility the "full data" linear TIFF's own description sells (recovered float low by up to a whole DN where rounding is honest to ±½). One shared `output.pack_unit` now `np.rint`s for all six, matching what `render/thumbnail.py` already did for alpha. `test_linear_tiff_no_clip.py`'s two strict-equality anchors were **re-reasoned, not loosened** — stated against the half-step band and still exact, which a truncating or a clipping packer both still fail. The display-side twins in `seestack/render/` are filed as a lead, not swept. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +6 `tests/test_export_rounding.py` (5 fail before), 3 re-reasoned in `tests/test_linear_tiff_no_clip.py` and 2 in `tests/webapp/test_video_sharpen_still.py`.
- **v0.354.0** — Friendliness/understand: **the Nights card says which of your nights the Moon washed out, not just the newest one.** v0.278.0 put a retrospective Moon verdict on the "Last night" card; the question behind it ("so which of my ten nights were any good?") had no answer, and a sharp night under a 96%-lit Moon 20° away reads as a good night in the Nights table. Every row now carries the same reading (`NightSummaryOut.moon`) and a dimmed **bright Moon** marker appears on `poor` nights, sentence in the tooltip + `aria-label` like the verdict and `ended early` markers; `good`/`ok` say nothing and nothing is ever filtered on it. The filed cost note was measured, not reasoned about: 24.6 ms/row would have added 0.74 s to a 30-night page, so `seestack.nightplan.session_moons` does the table in one astropy pass (0.075 s at 30) for **bit-identical** floats — `_moon_geometry` now delegates to `_moon_geometry_many`, so scalar and batched cannot drift. Unknown site / unsolved target / ephemeris failure all read as `null`, never as "fine". Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +4 `tests/test_session_moon.py`, +6 `tests/webapp/test_target_nights.py`, +5 `NightsCard.test.tsx`.
- **v0.353.3** — Autonomy/correctness: **the app stops *recommending* a flat-dark the flat can't use.** `recommend_masters` — the answer behind the Stack form's "Use recommended" button and its ★ — ranked a flat-dark on exposure/gain/temperature alone, with no dimension awareness, so with two cameras' masters in one library the exposure-perfect-but-wrong-size dark out-ranked the usable one and one click pre-filled the silent mismatch v0.353.2 had to warn about. `_recommend_flat_dark` now skips a dark that `dims_conflict`s with the **flat** it would calibrate. One-sided, so an unrecorded dimension changes nothing on upgrade; the unattended `auto_bind_master_ids` never had the hole (its `_bindable` gate covers both). Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +3 `tests/webapp/test_calibration.py`.
- **v0.353.2** — Broken-UX + image quality: **a mismatched flat-dark is no longer silently dropped, and the Stack form stops predicting a failure that never comes.** The flat-dark is the one calibration pick that is neither refused nor applied — `CalibrationMasters.validate` never looks at it and `load` just skips the subtraction on a shape mismatch — so the stack succeeded with the flat's own pedestal still baked in (measured: a 40 % vignette corrected to 1.0000 with a matching flat-dark, **1.1333** without), while the form rendered the shared red *"Stacking with it will fail"* blocker. `CalibrationMasters.flat_dark_shape_mismatch` + a `calibration_warnings` line now say it on the finished run, and a dedicated `flatDarkSizeWarning` (amber, measured against the **flat**, which is the engine's own test) says it honestly at pick time. Same carve-out as `biasSizeWarning`, one slot along. Also closes the third silent flat-dark found on the way: clearing the **Master flat** left `flat_dark_master_id` set, submitted, ignored (the engine only loads one inside `if flat_path:`) and invisible — `flatPickPatch` now clears it with its flat. Full write-up in [`SHIPPED.md`](SHIPPED.md). Tests: +3 `tests/test_calibrate.py`, +5 `calibrationFit.test.ts`, +1 `Stack.test.tsx`.
- **v0.353.1** — Engine parity: **`reproject_rgb` now trims the same frame edge the production path does.** The whole-canvas variant validated on a bare `0 <= src <= size-1` while `reproject_rgb_windowed` — the one `align_one` actually calls — insets by `FRAME_EDGE_INSET_PX` to keep the debayer/reproject artefact ring out of the stack. No production pixel moves (`reproject_rgb` has one caller, a test); the point is that the simpler signature is no longer a trap. Tests: +1 `tests/test_windowed_stack.py` (fails before).
- **v0.353.0** — Data-integrity / image quality: **a master flat built on a different colour-filter phase is refused instead of tinting every frame.** `CalibrationMasters.validate` compared `arr.shape` only, so a flat whose CFA phase is one pixel out of step with the lights was divided into the raw Bayer mosaic per *colour* — correcting every red photosite with a green value. It now fails fast (the same shape as the dimension guard) when both sides declare one of the four real phases and they differ; a dark or bias corrects each physical pixel, so it is never refused and earns an advisory instead. The unattended binders (`calibration.bayer_conflict`, `auto_bind_master_ids`, `_bind_saved_calibration_masters`) skip such a flat so a walk-away stack can't turn into an error, `coverage_miss_reason` names the phase, and the Stack form warns at pick time (`flatBayerWarning`). Inert on every master built before `BAYERPAT` was read. Tests: +7 `tests/test_calibrate.py`, +3 `tests/webapp/test_auto_stack_saved_masters.py`, +5 `tests/webapp/test_calibration.py`, +8 vitest.
- **2026-09-05 — the R2 bulk move.** 227 resolved entries and 24 QA sweep/audit records were cut out of "Bugs (fix these first)" (12,375 lines → 991) and appended verbatim to [`SHIPPED.md`](SHIPPED.md) and [`PROCESS-NOTES.md`](PROCESS-NOTES.md). **Grep those two files, not this one, for anything that shipped before v0.352.3.** One line rather than 227 auto-truncated ones: re-adding a summary per entry would put a fifth of the cut straight back, and both destination files are the grep target by their own front matter (AGENTS.md §2, §4).
- **v0.352.2** — Friendliness: **"shoot it in mosaic mode" now says how big a mosaic.** With the measured framing verdict on screen the Target page hides `ObjectInfoCard`'s catalogue line — and the panel plan lives inside it — while History renders no such card at all, so the one number answering the beginner's next question had nowhere to appear. `FramingVerdictNote` now renders `mosaic.text` from the shared `["identify", safe]` query (one request, not two), on the `partial` verdict only. Found by re-running `scripts/agent-dogfood.sh`, which also closed the "coverage vs panel count" lead: at v0.352.0's derived field the sample reads 15 % ↔ 3×3 = 9 panels, which agree. Tests: +3 `FramingVerdictNote.test.tsx`.
- **v0.352.1** — Trust/friendliness: **a mosaic picture is no longer called "your frame", nor told to go and shoot the mosaic it already is.** `framing_result_verdict` measures everything against the run's *canvas*, but worded all four verdicts as if that canvas were one frame — so on the owner's dominant workflow the "did I frame it well?" card claimed a multi-panel canvas was a single frame and advised "Shoot it in mosaic mode". A `canvas=` kind (`CANVAS_FRAME`/`CANVAS_MOSAIC`) read from the run's own `stack_runs.is_mosaic` picks the wording; every number is unchanged, and a run from before schema 8 (`is_mosaic` NULL) keeps byte-identical sentences. Tests: +6 `tests/test_framing.py`, +5 `tests/webapp/test_stack_framing.py`, +3 `FramingVerdictNote.test.tsx`.
- **v0.288.0** — Share/back-up: **"Download all my pictures" now really means all of them.** The zip walked
- **v0.287.4** — Editor/export parity: **the full-res PNG download now keeps the look you saved.** Tuning a
- **v0.287.3** — Data-integrity: **a plate solve is only believed when its WCS actually locates the frame.**
- **v0.281.0** — Autonomy: **a walk-away stack whose drizzle canvas won't fit now makes a slightly smaller
- **v0.281.0** (same change, the half it rests on) — Correctness/autonomy: **`StackOptions.unattended` — one
- **v0.280.0** — Beginner feature / friendliness (Builder, branch `claude/compassionate-galileo-4maz3z`):
- **v0.279.1** — Autonomy/trust (Builder, branch `claude/compassionate-galileo-4maz3z`): **"Your cleanest shot
- **v0.277.3** — Memory/hardening (Scout, branch `claude/vigilant-knuth-yeeeim`; found by the calibrate-masters
- **v0.272.1** — Friendliness: the Stack form's **Lucky imaging** knob was labelled "keep best **%**" but its
- **v0.270.4** — 🟠 The editor levels a mosaic's sky by **frame count**, the way the stack that produced it
- **v0.345.4** — the `astropy.stats` "Input data contains invalid values" warning is no longer emitted per frame / per canvas (`bg/per_frame.py`, `bg/final_gradient.py`, `qc/metrics.py::estimate_sky`); measured to fire only on a NaN-bearing (mosaic) canvas. Full entry in [`SHIPPED.md`](SHIPPED.md) (cut from "Infra" 2026-09-07).
- **v0.310.0 + v0.311.0** — the wallpaper, share JPEG, keepsake and scale-&-compass exports come off the master at share size for *linear* runs (`stack._native_picture_source`, `SHARE_JPEG_MAX_LONG_EDGE`); display-space runs were declined on purpose — that half is the READY render-cache entry under "Features that serve real workflows". Full entry in [`SHIPPED.md`](SHIPPED.md) (cut 2026-09-07).
- **v0.270.2** — 🟠 A star-poor mosaic panel is no longer auto-rejected as "cloud". `grade_frames` built its
- **v0.270.1** — 🔴 The walk-away auto-stack can no longer publish a picture made worse by subs whose files
- **v0.237.2** — Level a big mosaic's thin panel the same way in the preview and the export.
- **v0.231.1** — "Point here right now" now respects the Moon: the whole-night plan's proximity penalty is
- **v0.231.0** — NEW beginner feature "Point here right now": a Dashboard card that picks, from the user's *own*
- **v0.230.2** — Honest accounting for subs that simply **weren't on disk**: a `count_unreadable_frames` preflight in
- **v0.219.0** — NEW beginner feature "Your first image": a self-checking four-step map of the journey (point at your
- **v0.218.0** — The master-coverage roll-up now *explains* itself: each missed target carries a plain-language
- **v0.217.1** — The skipped-calibration-master note now reaches the walk-away user: the same recorded
- **v0.213.0** — ⭐⭐ Fixed the PER-FRAME background flatten's starved object mask — the last stacking-engine source of
- **v0.212.0** — NEW beginner feature "Was last night's sky bright?": a relative, self-hiding read on the latest
- **v0.211.1** — Editor export/render job polling hardened into one tested helper (`pollJob.ts`): rides out up to 5
- **v0.211.0** — ⭐⭐ Fixed the one-click Auto colour split (purple one side / green the other) at its root: the
- **v0.210.20** — Click-path audit fix (f) + (d): `bulk_frames` now returns a `note` so "Reject worst" on a
- **v0.210.19** — Four frontend click-path/UX fixes from the 2026-07-26 audit: (g) `isNavActive` matches whole path
- **v0.203.0** — Fix the aliased/low-res interactive stack render: `load_stack_rgb` now downscales with a NaN-aware
- **v0.202.0** — ⭐⭐⭐ Auto-derive the plate-solve FOV per frame from the FITS header (S30 ≈ 2.1°, S50 ≈ 1.27°) +
- **v0.196.0** — ⭐⭐ Full-res PNG offered on every beginner picture-download surface (consistency follow-up to
- **v0.195.0** — ⭐⭐ Full-resolution PNG download on the History card (directly answers the owner "my output is
- **v0.184.11** — ⭐ "How's my stack?" now surfaces the #1 cause of the owner-reported faint-field "gibberish": when
- **v0.178.2** — The "why frames were left out" high-drop verdict now names the *dominant actual cause* (soft focus →
- **v0.178.1** — ⭐ Fixed the "One frame vs your stack" reveal rendering its two halves under different tone curves.
- ~~**Calibration exposure-mismatch warning was silenced exactly when a wrong-shaped bias disabled dark-scaling.**~~
- **QA re-audit record (Scout 2026-07-23, branch `claude/kind-mccarthy-49jli6`).** Adversarial correctness sweep
- **v0.141.0** — NEW BEGINNER FEATURE / friendliness (PRIORITY 3 — "annotated results"; Builder 2026-07-21,
- **v0.139.0** — NEW BEGINNER FEATURE / autonomy (PRIORITY 2/3 — pre-stack reassurance; Builder 2026-07-21,
- **v0.137.0** — NEW BEGINNER FEATURE / autonomy (PRIORITY 2/3 — "drop files, walk away, get told when it's
- **v0.136.7** — Stacking-engine correctness (PRIORITY 1 — sub-pixel alignment consistency; Builder 2026-07-17,
- **v0.136.6** — Friendliness (PRIORITY 3 — beginner-facing frames table; Builder 2026-07-17, branch
- **v0.136.5** — Calibration-engine robustness (PRIORITY 4 — image-quality/consistency; Builder 2026-07-17,
- **v0.132.1** — Stacking-engine correctness (PRIORITY 1 — data-integrity of a beginner-facing diagnostic;
- **v0.132.0** — Beginner feature / friendliness (PRIORITY 3 — "should I wait or walk away?"; Builder 2026-07-16,
- **v0.131.3** — Stacking-engine correctness (drizzle edge/floor polish — focus #1; Builder 2026-07-16, branch
- **v0.123.0** — Beginner feature / friendliness (PRIORITY 3 — "enjoy & share a good image"; Builder 2026-07-14,
- **v0.121.5** — Engine robustness (calibration-engine contract-hardening — focus #1; Builder 2026-07-14, branch
- **v0.121.4** — Engine robustness (stacking-engine hardening — focus #1; Builder 2026-07-14, branch
- **v0.121.3** — Engine robustness (stacking-engine hardening — focus #1; Builder 2026-07-14, branch
- **v0.119.8** — Bug fix (**upgrade-safety / data-integrity — §9, top priority class**; Scout 2026-07-14,
- **v0.119.6** — Bug fix (data integrity / autonomy — PRIORITY 2/3; Builder 2026-07-14, branch
- **v0.119.5** — Bug fix (friendliness/trust — PRIORITY 3; Builder 2026-07-14, branch
- **v0.114.0** — Beginner feature (friendliness/workflow — PRIORITY 3; Builder 2026-07-13). "Share card"
- **v0.113.2** — Robustness (Builder 2026-07-13). Harden `session_recap._parse`: coerce a tz-naive timestamp
- **v0.113.1** — Autonomy/image-quality/correctness (Builder 2026-07-13). Re-QC a frame whose Stage-1 cache
- **v0.113.0** — Autonomy/friendliness/image-quality (Builder 2026-07-13). Cross-session quality-drift nudge:
- **v0.109.26** — Correctness/data-retention (image-quality/autonomy; Builder 2026-07-12; found by an
- **v0.109.25** — Determinism/idempotency (image-quality/autonomy; Builder 2026-07-12; found by an
- **v0.109.24** — SECURITY: fixed an unauthenticated path-traversal / arbitrary-file-read in the SPA static
- **v0.109.17** — Data-integrity bug (autonomy/image-quality; Builder 2026-07-11; found + reproduced by an
- **v0.109.16** — Autonomy (PRIORITY 2; Builder 2026-07-11): the **unattended slice** of the pre-flight
- **v0.109.15** — Editor (PRIORITY 1): the **Compare** toggle now disables itself while previewing a trim crop,
- **v0.109.14** — Watcher auto-stack no longer redundantly re-stacks an already-current target after a manual
- **v0.109.12** — Job-worker robustness: `_persist` no longer risks killing the single worker on a
- **v0.109.11** — Job-state correctness bug (Builder 2026-07-11; found by an adversarial webapp-orchestration
- **v0.109.10** — QC-engine correctness hardening (PRIORITY: stacking/QC-engine data-integrity; Builder
- **v0.109.9** — Friendliness / UX bug (PRIORITY 3; Builder 2026-07-11; found by the frontend non-editor route
- **v0.109.8** — Friendliness / display bug (PRIORITY 3; Builder 2026-07-11; found by the frontend non-editor
- **v0.109.7** — Editor bug (PRIORITY 1; Builder 2026-07-11; found by the same frontend editor-logic audit —
- **v0.109.6** — Editor bug (PRIORITY 1; Builder 2026-07-11; found by an adversarial audit of the frontend
- **v0.109.5** — Security / invariant hardening (Builder 2026-07-11; found by an adversarial audit of the
- **v0.109.2** — Friendliness / consistency (PRIORITY 3; Builder 2026-07-11): the History card's **Adjust**
- **v0.109.1** — Two safe, self-contained hardening fixes (Builder 2026-07-11): (1) **image quality** —
- **v0.109.0** — Editor (PRIORITY 1; Builder 2026-07-11): the editor's no-recipe fallback view now uses the
- **v0.108.4** — Editor robustness (PRIORITY 1; Scout 2026-07-11): `recipe_from_dict` no longer 500s on a
- **v0.108.1** — Image-quality / trust (PRIORITY 4; Builder 2026-07-11): surface the colour-cal *clamp* warning.
- **v0.108.0** — Friendliness / trust (PRIORITY 3; Builder 2026-07-11): surface Auto's colour-calibration outcome
- **v0.107.10** — Friendliness / trust (PRIORITY 3/4; Builder 2026-07-11): surface *which* colour-calibration
- **v0.107.9** — Autonomy / image-quality (PRIORITY 2/4; Builder 2026-07-11): when Auto's colour calibration
- **v0.107.5** — Autonomy (PRIORITY 2; found by the same 2026-07-11 auto-stack audit): finish the v0.107.1
- **v0.107.4** — Autonomy / "just works" (PRIORITY 2; found by a fresh adversarial audit of the auto-stack
- **v0.107.2** — Image-quality/correctness (Scout, #238): clamp `_solve_gray_star`'s per-channel colour-cal
- **v0.107.3** — Stacking-engine memory safety (found by a fresh adversarial audit of the stacker
- **v0.107.0** — Editor (PRIORITY 1): one-click **"Neutralize background"** fix for a residual sky
- **v0.106.0** — Image quality / trust (PRIORITY 4): library-wide "does Auto land the background neutral?"
- **v0.105.0** — Image quality / trust (PRIORITY 4): the unattended auto-edit now measures the finished
- **v0.104.1** — Friendliness (PRIORITY 3 / trust): total integration time on the Target detail page.
- **v0.104.0** — Feature (editor, PRIORITY 1 / trust): sky-background colour-cast readout. The
- **v0.103.17** — Fix (editor, PRIORITY 1): the editor's undo/redo hook (`useUndoable`) misbehaved under
- **v0.103.15** — Fix (editor, PRIORITY 1): the per-op "Split this op" / "Without this op" compare
- **v0.103.14** — Fix: the REST job endpoints silently stripped the server-classified `error_kind` (Builder
- **v0.103.13** — Actionable "why uncalibrated" advice on the History Info panel (Builder 2026-07-10). For a
- **v0.103.12** — Auto-enable *dark exposure-scaling* in the unattended chains (Builder 2026-07-10). The
- **v0.103.11** — Gate the auto-bound *dark* on a gain/temperature confidence match too, completing the
- **v0.103.10** — Gate the auto-bound *bias* on a gain/temperature confidence match (Scout 2026-07-10;
- **v0.103.9** — Fix drizzle frame-accounting counting an off-canvas stray sub as *used* (Builder

- **v0.103.8** — Carry the calibration-status trust line onto the editor's auto-note surface (Builder
- **v0.103.7** — Surface calibration provenance in plain language on the run Info panel (Builder 2026-07-10;
- **v0.103.6** — Auto-bind calibration: gate the auto-bound *flat* on a gain/temperature confidence match
- **v0.103.5** — Engine robustness (background flatten; Builder 2026-07-10, found by a fresh adversarial
- **v0.103.4** — Auto-bind calibration: dimension-gate the masters so an unattended stack can't
- **v0.103.2** — Stacking-engine correctness (drizzle reject; Builder 2026-07-10, found by a fresh
- **v0.103.1** — Editor/parity hardening (PRIORITY 1; Builder 2026-07-10, found by a fresh adversarial
- **v0.103.0** — One-click "Reject the N odd-target frames" on the mixed-pointing guard (autonomy/
- **v0.102.0** — Pre-flight "batch looks like two targets" guard on the Stack form too (autonomy/
- **v0.101.0** — Pre-flight "this batch looks like two targets" guard, first slice (autonomy/friendliness/
- **v0.100.0** — Honest per-run frame accounting + large-align-failure diagnosis (friendliness/trust,
- **v0.99.10** — Drizzle pre-run estimate reports the **real** output canvas size (stacking-engine
- **v0.99.9** — Honest per-pixel *frame count* for `coverage_min`/`coverage_max` on the **drizzle**
- **v0.99.6** — Honest per-pixel *frame count* for `coverage_min`/`coverage_max` under quality
- **v0.99.3** — Plain-language help on every advanced Stack-form knob (friendliness — priority 3,
- **v0.99.2** — Retry a transient QC error in the auto-pipeline (autonomy/robustness — priority 2,
- **v0.99.1** — Surface "N frames couldn't be quality-checked" on the Target page (friendliness/trust —
- **v0.99.0** — Auto-bind matching calibration masters to the *unattended* stack chains (autonomy +
- **v0.98.2** — Tonight planner (friendliness — priority 3, Builder dogfood-found 2026-07-09): the
- **v0.97.8** — Tonight planner (friendliness/autonomy — priority 3, Builder §4 top-up): show *when
- **v0.97.7** — Tonight planner (friendliness/trust): a dimmed per-row Moon cue explains *why* a
- **v0.97.6** — Tonight planner (autonomy/trust): the observability score now weights each target's Moon
- **v0.97.5** — Tonight planner (friendliness): the Moon card now shows *when* the Moon rises or sets
- **v0.97.4** — Tonight planner (friendliness): the Moon card now distinguishes a **waxing** from a
- **v0.97.3** — Tonight planner (friendliness): section-accurate empty states. The two target
- **v0.97.2** — Tonight planner (friendliness): the "Minimum altitude" picker no longer renders
- **v0.97.0** — ⭐ OWNER-REQUESTED "Tonight" night planner — widen the bundled catalog beyond Messier.
- **v0.96.0** — ⭐ OWNER-REQUESTED "Tonight" night planner, slice (b) — horizon / tree-cover mask: an opt-in `horizon_profile` (azimuth→min-clear-altitude points) shapes each target's usable window past low obstructions; `HorizonProfile` interpolates with 360° wrap, Settings gets a point editor, Tonight flags `horizon_active`. Additive, upgrade-safe (empty default = old flat-floor behaviour).
- **v0.95.0** — ⭐ OWNER-REQUESTED "Tonight" night planner, slice (a) — the offline astronomy core.
- **v0.94.17** — Friendliness: `post/target_id.py` now maps SIMBAD short OTYPE codes to plain words
- **v0.94.16** — Colour-calibration robustness: `post/color_cal.py::_solve_gaia` now clamps both solved
- **v0.94.15** — Engine/data-integrity fix (found by a fresh adversarial editor-pipeline audit): the
- **v0.94.14** — Friendliness polish: the Dashboard readiness banners' dismissal now keys on the
- **v0.94.13** — Friendliness (first-run): extended the Dashboard readiness banners to a
- **v0.94.12** — Friendliness/autonomy: a proactive, dismissible "plate-solving isn't set up"
- **v0.94.11** — Friendliness (cosmetic): the ASTAP "no star database" hint on Settings now
- **v0.94.10** — Project-DB robustness: opening an empty/foreign `project.sqlite` (a blank or
- **v0.94.9** — Ingest robustness: a transient Stage-1 copy failure (a NAS blip during
- **v0.94.8** — Stacking-engine data-integrity fix (current-focus §1): the bilinear debayer
- **v0.94.7** — Job-progress robustness (autonomy/friendliness): fixed two real `useJobEvents` SSE bugs
- **v0.94.6** — Editor/undo correctness (PRIORITY 1): fixed undo *over-reverting* a second use of the
- **v0.94.5** — Engine/NaN-coverage: `geometry.rotate` now guards degenerate sizes (`h < 3 or
- **v0.94.4** — Robustness/friendliness: `POST /api/calibration/masters` now returns 400 (not 500)
- **v0.94.3** — Engine/NaN-coverage: sub-pixel refine now marks the vacated edge NaN on a
- **v0.94.2** — Editor friendliness: surface the content classification in the "What Auto-process
- **v0.94.1** — Robustness: `detail.denoise` now guards a degenerate 1-px-thin image
- **v0.94.0** — Auto-preset classifier — *safer-first slice* (a preset **suggestion**, not a change
- **v0.93.4** — Extracted the RA 0°/360° unwrap heuristic into one shared dependency-free
- **v0.93.3** — Target aggregate RA is now 0°/360°-wrap-safe (`claude/happy-franklin-te45e2`).
- **v0.93.2** — Reference-frame selection is now RA 0°/360°-wrap-safe
- **v0.93.1** — Make the editor's `denoise-suggestion` recipe-aware, matching its
- **v0.93.0** — Show the auto-edit "why" note in the *editor* when opening a run a background
- **v0.92.0** — Carry the Auto "why" note onto the *autonomous* auto-edit paths
- **v0.91.0** — "Why these steps?" — surface the Auto recipe's *causal inputs*
- **v0.90.0** — "N new subs since your last stack — restack?" nudge on the Target page
- **v0.89.3** — Chain the auto-edit onto the watcher's background auto-stack
- **v0.89.2** — Graceful degradation for `background.final_gradient` on busy / dense-star
- **v0.89.1** — Two verified low-severity webapp-router robustness fixes (Scout,
- **v0.89.0** — Editor "Compare a look" follow-up: a "Switch to this look" action on the
- **v0.88.0** — Editor "Compare a look" split: a picker (Auto + built-in + saved presets)

- **Companion caution: Drizzle on with too few frames (v0.87.1, image-quality/PRIORITY 4).**
- **Proactive Drizzle nudge on the Stack form (v0.87.0, autonomy/image-quality/PRIORITY 2–4).**
- **Don't claim quality weighting influenced a min/max-reject stack (v0.86.2, image-quality/

- **Chain the auto-edit onto library-wide "Reprocess everything" (v0.86.1, autonomy/image-
- **Chain a one-click auto-edit onto the "Process target" result (v0.86.0, autonomy/editor/
- **Deep-link the one-click "Process target" result to its editor in one hop (v0.85.3,

- **Surface the one-click "Process target" job's outcome + a "View result" link on Jobs

- **"Ready to process?" getting-started callout for a fresh target (v0.85.1,

- **One-click "Process target" — QC + solve + auto-grade + stack in one job (v0.85.0,

- **De-flake the Stack-form photometric-nudge test that reddened main CI + fix the underlying

- **Clamp `background.final_gradient`'s box to the image size so Auto can't hard-fail on a

- **Extend the rejection-clipped trust line to the drizzle-reject path (v0.84.11, PRIORITY-4

- **Extend the rejection-clipped trust line to the min/max-reject path (PRIORITY-4

- **Surface how much the stack's rejection actually clipped — a trust line on History

- **Stacking hot path: per-frame weight/scale lookups honour a frame whose DB id is 0

- **Target page: recoverable error state instead of a broken shell when the target 404s

- **One-click actions on the three remaining advisory-only Stack-form rejection nudges

- **Plain-language "Build master" empty-folder failure (PRIORITY-3 friendliness; follow-up to

- **Robust server-side `error_kind` on failed jobs — makes the plain-language job-error

- **Plain-language job failure messages on the Jobs page (PRIORITY-3 friendliness; follow-up to

- **Plain-language job names + a guided empty state on the Jobs page (PRIORITY-3 friendliness).**

- **Robust server-side plate-solve setup classification — makes the star-database "not set up"

- **Actionable "plate-solving isn't set up" banner on the Target page (PRIORITY-3 friendliness +

- **QA — stacking-engine adversarial audit + one-click Auto dogfood (top current-focus areas),

- **Fix (PRIORITY-1 editor): a cropped/geometry-edited live preview letterboxed with spurious

- **Engine hardening (PRIORITY-1 stacking-engine QA): correct a stale `WelfordAccumulator`

- **One-click "Drop N outlier frames" + safety-cap notice on the Stack-form auto-grade hint

- **Surface the deep-rescan count on the finished reprocess-all job summary (follow-up to

- **Reprocess-everything slice (b): optional deep full rescan (re-QC / re-solve / re-grade

- **Proactively nudge dark exposure-scaling from the calibration store (PRIORITY-2 autonomy;

- **Surface dark exposure-scaling provenance on the run Info / History card (PRIORITY-4

- **Dark exposure-scaling — reuse a dark library shot at one exposure to calibrate subs

- **Make the remaining advisory Stack-form nudges one-click actionable (PRIORITY-2/3

- **Fix: mosaic canvas iterative-shrink dropped a good central frame instead of the real

- **Fix: a manual re-stack (or re-export/re-combine) under an existing basename silently

- **Fix: watcher could permanently drop a batch from auto-ingest when a file stabilised

- **Fix four more flaky Editor "From your data" tests that reddened main's CI (test-only,

- **Proactive "N targets are out of date" nudge — reprocessing after an upgrade is no

- **Fix: "Reprocess everything" silently overwrote each target's existing stack output

- **Stack form nudges to enable Photometric normalization when transparency varies a lot

- **Fix flaky Editor "Auto curve" test that was intermittently reddening main's CI.**

- **Surface photometric-normalization provenance on the run Info / History card

- **Photometric (multiplicative) frame normalization before combine — gain-match the

- **Per-op split before/after — drag a divider to see the image with vs without just

- **Personal default recipe — "my house style" one click away on every new run

- **Split before/after compare — drag a divider to see Original vs Edited in one

- **Reprocess-everything gains an "only outdated targets" filter (owner-requested

- **Stack runs record the producing app version ("made with vX") — provenance +

- **Recipe carry-over across re-stacks: one-click "Use my previous edit"** — the Seestar

- **Curves widget now previews the auto-contrast curve (read-only ghost) + "Bake to

- **"Cropped view — showing N% of the frame" indicator + one-click "Remove crop"** —

- **Fix: single-field stacks were misclassified as mosaics (Scout-verified

- **Jobs page surfaces the reprocess-all batch outcome in plain language** —

- **⭐ OWNER-REQUESTED — "Reprocess everything" (slice a): one-click restack of

- **Auto-process now gives its one-click result a gentle, data-driven contrast

- **Auto-process summary names the mosaic coverage-leveling step in plain language** —

- **Fix: SCNR "Protect" tooltip had gentler/stronger reversed (misled the most

- **Fix: a thin crop + downscale no longer crashes the editor preview/export with

- **Editor exports are marked display-space — no more re-edit double-stretch, and

- **"Auto curve" button names its goal + dims when already applied (data-driven

- **Data-driven "Auto curve" starting point for the Curves op (completes the

- **Every tonal control's landing shown on the histogram (Stretch/clip edges +

- **Fix flaky frontend CI at the root: run vitest test files sequentially

- **Data-driven "From your image" Strength + Black point for the asinh Stretch

- **Auto-process summary names the mosaic border trim in plain language** — small

- **Auto-process trims a mosaic's ragged low-coverage border (cleanly framed

- **Coverage overlay now follows the recipe's geometry ops (was frozen on the

- **Fix flaky frontend CI at the root: raise vitest `testTimeout` above

- **Gamma suggestion names the goal it solves for (not just a bare number)** — the

- **"Edited" dot on tuned op rows in the pipeline list** — after Auto-process or a

- **Editable numeric readout beside every editor slider** — the editor rendered

- **Fix (a11y): editor curve points are keyboard-operable** — the last open

- **Fix: trim-crop preview rectangle misaligned on a letterboxed preview** — the

- **Fix: deconvolution's live preview silently understated the export on large

- **Fix: editor overlay-zoom mislabel + keyboard access gaps (a11y)** — three

- **Fix: background/gradient op failures now surface in the editor (were a silent

- **Fix flaky `detail.sharpen` NaN test (route unsharp mask around skimage)** — the

- **Fix: "Use data defaults" toolbar and the per-param "✓ already set" indicator

- **Fix: star-mask overlay now reflects the display-space image the ops gate on

- **Fix: one slider/curve drag no longer floods (and evicts) the editor's undo

- **Fix flaky frontend CI (Editor Levels "From your image" / "Auto levels" tests)** —

- **Editor recipe with a non-mapping `params` no longer 500s** — a recipe body

- **One-click "Reset points" on the Levels op header** — the Levels header had

- **Data-driven midtone (gamma) point for the Levels op** — the Levels suggestion

- **Friendly labels on the last jargon-bare editor dropdown (denoise Method)** — the

- **Show the Levels black/white points as guides on the histogram** — while setting

- **Single-click "Auto levels" on the Levels op** — the data-driven Levels buttons

- **Editor: accurate data-driven value labels (Levels buttons + Auto's crossfaded

- **Smooth the Auto recipe's noisy/clean cliff (denoise ↔ sharpen crossfade)** —

- **One-click "From your image" black/white points for the Levels op** — the Levels

- **Test the PNG-render path also surfaces failed ops** — coverage follow-up to the

- **Warn about a degenerate Levels op (empty black↔white range)** — companion to

- **Guard the Levels op against a degenerate (white ≤ black) range** — the Levels

- **Surface failed ops on export, not just in the live preview** — the preview /

- **Fix stale/misleading maintainer comments & docstrings** — three inaccuracies a

- **Guard the Curves op against a degenerate (blank-the-image) curve** — a tone

- **Expose the Rotate op's `expand` control (was a dead read)** — `geometry.rotate`

- **Warn about a redundant second Stretch (double-stretch bug)** — `apply_recipe`

- **Show the proposed trim over the coverage heatmap** — when the user opened the

- **Show render progress for the full-res PNG download** — "Download full-res PNG"

- **Note the coverage overlay is for the uncropped frame when a crop is applied** —

- **Preview the "Trim border" rectangle before committing** — the one-click "Trim

- **Colour heatmap + legend for the coverage overlay** — the coverage-map overlay

- **Fix a flaky Stack-form vitest ("does not suggest min/max reject when already

- **"Trim border" selects the new Crop op + reports the kept fraction** — polish on

- **Coverage-map overlay in the editor (mosaic trust/explain)** — a Seestar

- **One-click "Trim to well-covered area" for mosaics** — a Seestar mosaic's union

- **Highlight/shadow clipping warning in the editor** — over-stretching is the

- **Explain the editor's TIFF export mode** — the Export panel's "TIFF" dropdown

- **Built-in presets prepend Coverage leveling on a mosaic** — a built-in preset

- **Tell the user when "Coverage leveling" will do nothing** — the op only

- **Auto-add Coverage leveling to the Auto recipe for mosaics** — now that the

- **Fix: "Coverage leveling" editor op was a permanent silent no-op** — the

- **Fix: star-mask overlay ignored the op's star size (always the default 4 px)** —

- **Fix: star-reduction over-shrank stars in the live preview vs export** — the

- **Auto-suggest the min/max reject count (k) from the streaked-frame count** — with

- **Warn when the min/max reject k is too aggressive for the frame count** — the

- **Show the k-count in the rejection badge for a top/bottom-k trim** — follow-on to

- **Top/bottom-k trimmed-mean reject** — generalised `MinMaxRejectAccumulator` to

- **"slower preview" chip in the Add-operation menu** — the `heavy` spec hint

- **Retire the now-dead "export only" preview scaffolding → "slower preview"** —

- **NaN-preservation regression tests for the spatial detail ops** — the

- **Fix: hot-pixel editor op silently did nothing on mosaic (NaN) images** — the

- **Show Auto's chosen data-driven values in the "What Auto-process did" note** —

- **Adaptive live-preview debounce for heavy editor ops** — dragging a slider

- **Data-driven saturation in the one-click Auto recipe** — Auto's final

- **"Your data" context chip in the editor header** — the four data-driven

- **Keep the old preview + "Updating…" badge while re-rendering (editor

- **Cancel superseded live-preview renders (editor responsiveness)** — the live

- **Direct pixel-transform + NaN-safety tests for the tone/colour editor ops** —

- **Built-in presets land sized to your data** — the built-in editor presets

- **"Apply data-driven defaults" one-click on the editor** — a user hand-building

- **Dim the "From your data" suggestion button when the param already matches** —

- **Complete + enforce plain-language help on every editor control** — finished the

- **Plain-language help on the remaining jargon-bare editor sliders** — v0.56.17

- **Data-driven sharpen radius in the one-click Auto recipe** — when Auto-process

- **Star-size-from-stars suggestion for the star-reduce op** — the `stars.reduce`

- **Sharpen-radius-from-stars suggestion** — the editor's Sharpen op made the user

- **Data-driven denoise strength in the one-click Auto recipe** — when Auto-process

- **"Preview is downscaled" hint in the editor** — the live preview always runs on

- **Preview↔export parity for the background ops** — v0.56.19 corrected the spatial

- **Auto-process note clears when the recipe changes** — follow-up to v0.56.18's

- **Preview↔export parity for spatial detail ops** — the live preview runs on a

- **Explain what Auto-process did** — after Auto-process builds a recipe the user

- **Per-op "Reset to defaults" (already shipped)** — the backlog listed this as an

- **Plain-language help on the jargon-heavy editor ops** — several detail/tone ops

- **Per-op "without this op" preview compare** — the editor's Compare button shows

- **Progressive disclosure of the "Add operation" menu** — the menu listed all ~19

- **Auto-place a newly-added op on the correct side of the stretch** — adding an op

- **"No stretch step" nudge in the editor pipeline** — if a recipe has ops but no

- **Friendly names for enum dropdowns (editor + Stack/Settings forms)** — enum

- **Grey out stretch params that don't apply to the chosen curve** — the Stretch op

- **Stage-conflict caution + one-click fix in the editor OpList** — ops declare a

- **Combine-method facet on the Gallery** — a "All / Drizzle / Min-max / σ-clip /

- **One-click "Turn on min/max rejection" on the Stack-form nudge** — the

- **Gentle green-cast removal in the one-click Auto recipe** — an OSC Seestar

- **Guided empty-pipeline nudge in the editor** — a first-timer opening the editor

- **"Export only" flag for preview-approximate editor ops** — the Deconvolution op

- **Plain-language "Combined:" line in the History Info panel** — the Info panel

- **Combine-method badge in the Compare view** — the `RejectionBadge` (v0.56.1)

- **Min/max-reject nudge on the Stack form for small streaked stacks** — below

- **Rejection-method badge on History/Gallery cards** — a stack can be combined

- **Min/max (extremes) rejection for small stacks** — the order-statistic fix

- **Capped exponential backoff for Seestar reconnects** — the poll loop

- **"You have calibration masters but aren't using them" nudge on the Stack

- **Calibration-status filter chip on the Gallery** — building on the searchable

- **Gallery search matches calibration status** — building on this run's

- **Seestar reconnect hygiene (fd-leak fix)** — the manager's poll loop

- **Calibration chip on History/Gallery cards** — a stack now records which

- **Per-target noise-σ trend sparkline** — the History page now shows a small

- **Recommend a master bias for the bias+flat (no-dark) workflow** — completes

- **Record which calibration masters were applied in the FITS header** — a

- **Bias-only calibration for lights when no dark is chosen** (bias slice (a))

- **"Compare with previous run" action on the History page** — the Compare view

- **"Which stack is cleaner" verdict in the Compare view** — when both compared

- **Configurable job-history retention** — the job-history cap (how many finished

- **Compare-two-stacks web view** — a new `/compare?a=<safe>:<run>&b=<safe>:<run>`

- **Noise-improvement readout vs the previous stack** — each History card now

- **Newest/Cleanest sort on the Gallery** — extends the History-page noise sort

- **Newest/Cleanest sort on the History page** — completes the noise series: the

- **Stamp the background-noise σ into the master FITS header** — extends the

- **Per-stack noise-floor readout + "cleanest stack" badge** — `run_stack` now

- **Editor processing chain in the History Info panel** — the run Info endpoint

- **Full editor-recipe HISTORY provenance in exported FITS** — an editor export

- **Code-split the frontend vendor bundle** — the eager app bundle was one

- **"From your image" denoise-strength suggestion** — the editor's noise-

- **Record the deconvolution PSF σ in the exported FITS header** — when an

- **PSF-from-stars for editor deconvolution** — the deconvolution op made the

- **Auto-grade hint on the Stack form** — the Stack form now calls the

- **Nudge quality weighting when frame quality varies a lot** — the Stack form

- **"N trailed frames" badge on the Target view** — mirrors the "N streaked"

- **Auto-grade: automatic, explained frame-quality grading** — the QC layer

- **Plain-language hints on the Target metric columns** — the FWHM, Stars, Ecc.

- **Transparency-night badge on History/Gallery cards** — completes the

- **Surface the quality-weighting summary in the run Info panel** — a

- **Eccentricity factor in quality weighting** — `compute_frame_weights` gained a

- **Library search matches notes + persistent filter view** — the Library

- **Transparency-night hint on the Stack form** — completes the transparency

- **Weight the stack by frame transparency** — `compute_frame_weights` gained a

- **Inline reject-reason chip on rejected frame rows** — rejected rows in the

- **"Reject worst by transparency" bulk action** — building on this run's

- **Editor undo/redo keyboard shortcuts** — the editor's undo/redo buttons now

- **Star-mask preview toggle in the editor** — a new

- **Compute the dead `transparency_score` frame metric** — the column has been

- **Undo the last bulk reject + reject-reason breakdown on the Target view** —

- **Calibration mosaic-edge NaN/coverage audit** — completes the NaN/coverage

- **Suggest the reference canvas when a non-drizzle mosaic is over budget** —

- **Warn when the stack budget exceeds available RAM** — `/api/system` now

- **One-click "reject all streaked frames"** — the "N streaked" badge on the

- **De-flake `Editor.test.tsx`** — `main`'s CI was intermittently red on the

- **Stack memory budget as a Setting** — a new `max_stack_memory_gb` setting

- **Mono mosaic-edge NaN/coverage audit** — added a regression test that stacks

- **Suggest a fitting drizzle scale when over budget** — the `stack-estimate`

- **Streaked-frame count badge on the Target view** — an orange "N streaked" badge

- **Frame count / mosaic flag inline in the Stack estimate** — the pre-run sizing

- **Reclaim streaked subs** — new opt-in `keep_streaked_frames` setting (default

- **Large-stack sigma-kappa hint** — completes the sigma-clip guidance pair. The

- **Show/search run labels in the Gallery** — the gallery response now carries

- **Drizzle memory estimate in the Stack form** — subsumed by the pre-run stack

- **Pre-run stack estimate endpoint** — new `GET /targets/{safe}/stack-estimate`

- **Outlier-safe drizzle** — new opt-in `drizzle_reject`: two-pass κ-σ

- **Editable notes/label on History cards** — the long-standing `notes` column

- **Mono single-frame edge test** — verified the mono stack path on a

- **Low-frame sigma-clip caution** — the Stack form now shows an inline caution

- **Integration time inline on History cards + Reuse settings from Gallery** —

- **Fix red CI (pytest-qt import crash)** — CI had been failing on every merge:

- **Integration time on Gallery cards** — stack runs now record their effective

- **Reuse stack settings from a previous run** — new

- **Warn on a mismatched calibration master pick** — the Stack form now shows an

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
