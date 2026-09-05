# Process notes & QA sweep records

Where the *history of how this project is developed* lives, so
[`IMPROVEMENTS.md`](IMPROVEMENTS.md) can stay a **working list**.

Nothing here is open work. Put a block here when it is a record rather than a
task:

- a **collision diary** or any other "what this run learned about running runs"
  note;
- a **QA sweep record**, including (especially) a clean one — a clean-sweep entry
  at the top of "Bugs (fix these first)" is the first thing every triaging agent
  reads, and it is not a bug;
- a **released claim** from "In progress", once the run that made it has finished.

Newest first, one dated block each. Reading order does not matter: nothing here
is a queue.

---

## DOGFOOD BASELINE — running-app probe at v0.352.1 (Builder 2026-09-05)

`scripts/agent-dogfood.sh` on a scratch data root with the bundled sample loaded
and stacked, Playwright full-page at 1440 px and 420 px plus the overflow probe.
**Nothing overflowing, no console errors.** Tallest pages, full-page scroll
height:

| page | phone (420) | desktop (1440) |
|---|---|---|
| `/targets/<T>` | **3,014 px** | 2,010 px |
| `/life-list` | 3,008 px | 1,453 px |
| `/targets/<T>/edit/1` | 2,815 px | 1,841 px |
| `/` | 1,785 px | — |
| `/targets/<T>/stack` | 1,748 px | — |

**The IA number has now been stable across three measurements and ~14 versions.**
The v0.338.1 probe recorded in `AGENTS.md` §1 put the tallest page — the Target
page — at **3,014 px on a phone**, and this run measures **3,014 px**, exactly.
That is a third independent reading agreeing with the standing advice in that
banner: **do not open a speculative IA slice.** (The +26 px the second run of the
day shows is the v0.352.2 panel-count line this run deliberately added, not
drift.)

**What the pass found**, both filed and shipped rather than left here: the
"coverage vs panel count" lead closed by measurement (the sample derives a
40′ × 26.7′ field from its own `pixscale_arcsec`, so 15 % coverage ↔ 3×3 = 9
panels, which agree — the lead was written against the pre-v0.352.0 S50 count),
and the real bug behind the screenshot, that the panel count had nowhere left to
appear once the measured verdict suppressed the predicted line (v0.352.2). Full
write-ups in `IMPROVEMENTS.md` → "Bugs (fix these first)".

**Worth knowing for the next dogfood run:** the sample's frames *do* carry
`pixscale_arcsec` (5.0 on 480 × 320), so the derived-field path is exercised by
the sample, not only by a real library. A framing/mosaic number read off the
sample is therefore trustworthy — which is why the pre-v0.352.0 2×2 stood out.

---

## Released "In progress" claims and collision diaries (moved 2026-09-04)

*Moved wholesale out of `IMPROVEMENTS.md` → "In progress", which had grown to 420
lines carrying **zero live claims** — every header said "claim released" or "run
finished". A section whose only job is to say what is being worked on right now
cannot do it while buried under a diary of what was worked on last week, and the
diary is worth keeping. Verbatim, newest first as it stood.*

> **Builder 2026-09-03, branch `claude/sweet-babbage-axt93w` — claim released, shipped as v0.328.6.** The
> second slice of the full-size loupe — an additive-field channel for the three `background.*` ops, which the
> v0.328.2 fitted-parameter channel explicitly could not carry. Full write-up on the loupe entry under
> "⭐ Editor — make it excellent".

> **⚠️ PROCESS NOTE + Builder 2026-09-02, branch `claude/zen-mccarthy-olkjpm` — collision TEN, two of three
> tasks duplicated by one other Builder inside the same hour, and the first where the *stand-down decision was
> settled by measurement instead of argument*. Run finished; claims released.**
> The `…-t59xya` Builder's PR **#682** landed **A1** as v0.326.1 and the planner's `_times_grid` overhang as
> v0.325.3 — both of which this run had independently built. **Theirs are on `main` and ship; mine are dropped,
> not re-litigated.** What is new is *how* that was decided, and it is cheap enough to be the standing method:
> **run your own test file against their shipped code in a `git worktree` of `origin/main`.** That took two
> minutes and answered the only question that matters — does mine catch anything theirs doesn't?
> * **A1 — 22 of my 23 tests passed on theirs.** The single failure was a *design* difference, not a defect
>   (on a bright image with no headroom mine returns the identity where theirs still pins the sky and scales
>   the shoulder — theirs keeps doing something useful, and is shipped). Decisive for the one place I thought I
>   was ahead: I had added a **noise-aware lift anchor** (`max(p50, sky + 3σ)`) after measuring the mode still
>   reading **0.1357 for a 0.1738 sky** post-spike-fix. Their code passes every sky-movement test I wrote,
>   which means my 0.1357 came from an **unrealistic fixture** — a star-poor scene whose 99.5th percentile is
>   the sky itself, so `autostretch` normalises against the background and spreads it unnaturally wide. **A
>   fixture that isn't shaped like the owner's data manufactures bugs as readily as it hides them**, which is
>   the same lesson A1 itself taught from the other end. The extra layer was therefore speculative hardening,
>   not a fix, and shipping it would have been churn on the on-by-default path. Dropped.
> * **`_times_grid` — theirs is better.** Near-identical clipping, but their `minutes_above_min_alt` sums a
>   per-sample interval array where mine capped `count × step` at the window length. Theirs is the honest
>   quantity; mine was a bound on a wrong one.
>
> **Two genuinely additive pieces were re-applied on top of theirs, in their names, each verified to fail on
> pre-fix code first** (the test for "is this additive?" is not "did I write it" but "does it catch something"):
> the two **sweeps** in `tests/test_edit_curve.py` — across the five stretch targets Auto and the presets
> actually use, and across four stack depths — which pin the audit's own quantified claims (the two branches
> were wrong in *opposite directions*, so a single-point test can sit on one branch and pass while the other
> rots; **9 of the 9 sweep cases fail on pre-fix code**); and the **XS friendliness item their own run filed**
> as the gap it opened (the ghost curve's unexplained fallback branch), built and tested here rather than left
> for another run. Both fold into their fixture rather than standing up a parallel one.
>
> **The one thing that did not collide is the one worth noting for the rotation:** **A3** (plate-solving
> writing `.wcs`/`.ini` sidecars into `incoming/`) — nobody has touched `seestack/solve/` in 25 commits. It was
> filed "verified by code reading, **not reproduced** — no ASTAP binary", and both overlapping runs went
> to the top of the *editor* queue instead. The audit's R5 finding predicted exactly this: sweeps land where
> the code is easy to read, and the findings that survive are the ones needing an **external process, a
> mosaic-shaped canvas, or a proxy scale** to exhibit. If two Builders are running, the cheapest
> de-confliction available is for the second to take the item whose repro needs a *stub binary or a fixture*
> rather than the one whose repro is a function call.

> **⚠️ PROCESS NOTE + Builder 2026-09-02, branch `claude/zen-mccarthy-46ejou` — collision NINE, and the first
> where an entire run was duplicated: all three tasks, by one other Builder, inside the same hour. Run finished,
> everything stood down bar one additive fix.**
> The other Builder's PR **#678** landed **v0.325.0** carrying *the same three items* this run built: the asinh
> full-res parity bug, the `bootstrap_solve` rescued-sub centre bug, and "Plan my week". Not merely the same
> items — the same *shape*, down to an identically-named test
> (`test_rescued_subs_store_their_own_centre_not_the_references` in both). **Theirs is on `main` and ships;
> mine is dropped, not re-litigated**, and PR #679 was rewritten rather than merged. Their versions are equal
> or better at every point, checked rather than assumed:
> * **asinh parity** — theirs is a strict superset. It anchors `render_stack_png` *as well as*
>   `render_preview_png_full_res`, which closes the History-lightbox site at a non-1024 `size` that mine only
>   *filed* as a follow-on idea. (That idea is therefore **not** filed — it would have been open work that was
>   already done.)
> * **rescued-sub centre** — near-identical, and theirs uses `all_pix2world`, so a SIP/distortion term in the
>   solution is honoured. Mine used `wcs_pix2world`.
> * **Plan my week** — theirs extracts the night walk as a shared `upcoming_dark_windows`, so the week view and
>   `next_observing_windows` *cannot structurally* drift about which night is which; mine re-implemented the
>   anchor and pinned the agreement with a test instead. Theirs is the better answer. Placement differs (their
>   card on the Tonight page vs. my nested `/tonight/week` route) and **that is not worth re-opening** — the
>   card is shipped, works, and the "put a feature inside the grouping, not one more banner" rule they cite is
>   the standing one. Filed as an idea under "Friendliness" only if the Tonight page later measures as
>   overlong; it is not a defect today.
>
> **What this run actually shipped, and why it is not churn:** one genuinely additive finding, on top of their
> work — `plan_week`'s 40-target cap kept the first forty targets **alphabetically**
> (`Library.list_targets` is `ORDER BY name COLLATE NOCASE`), so a big library's week was planned around
> whatever sorts first and the owner's deepest project could be silently dropped. That is "finish what I've
> got" answered with the wrong "got". It now keeps the most-shot targets. See the Shipped entry.
>
> **The process lesson, and it is a new one.** The claim-by-site discipline from collisions six–eight cannot
> help here: **both runs started within minutes of each other, from the same front-of-queue backlog, and each
> claimed only in its own first commit — which the other could not see because neither had pushed yet.** The
> backlog is a blackboard read at the *start* of a run; two runs that start together read the same board. The
> only mitigations that would actually have worked are outside a single run's control: (a) stagger the Builder
> schedule so two never start inside the same few minutes, or (b) **push the claim commit before writing any
> code, and re-`git fetch origin main` again immediately before the *first* implementation edit, not only
> between tasks** — the second is cheap and this run did not do it. Recommended for the next Builder: after
> claiming, fetch once more before the first line of code; if `main` has moved, re-read it before starting.

> **Builder 2026-08-31, branch `claude/wizardly-feynman-0lyyjh` — second claim, by site.** The top open item
> under "Friendliness": **"How's my stack?" tells every deep stack its edges are ragged**. Sites:
> `seestack/stack/stacker.py` (`coverage_thin_fraction` + the `add_stack_run` call),
> `seestack/io/project.py` (schema **20**, additive `coverage_thin_frac`), `seestack/stackhealth.py` (the
> coverage note and the "even coverage" strength), `tests/test_stackhealth.py` and a new
> `tests/test_coverage_thin_fraction.py`. — **claim released, shipped as v0.320.2.**

> **Builder 2026-08-31, branch `claude/wizardly-feynman-0lyyjh` — claim released, shipped as v0.320.1.** The top open item under
> "Image quality": **per-panel reference patches, so sub-pixel refinement reaches a mosaic's *other* panels**
> (filed by the v0.319.9 run as the deeper limitation it deliberately left). Sites I am editing:
> `seestack/stack/stacker.py` (the `options.subpixel_refine` setup block that builds `ref_patch`, and `_pass`/
> `_align_for_stack`'s refine plumbing), `seestack/stack/align.py`
> (`_apply_subpixel_shift_windowed`'s too-small-overlap skip → an honest `stats` flag),
> `seestack/stack/reference.py` (a pure `pick_central_frame` extracted from `pick_reference_frame`, so a panel
> can pick its own reference the same way the target does), and
> `tests/test_subpixel_mosaic_reference.py`. Guard: a single-field stack must be bit-for-bit unchanged —
> `pointing_groups` returns `None` when there is no sound split, which is the single-field case by
> construction.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-7y6nlj` — claim released, shipped as v0.317.0.**
> The top open item under "Autonomy & friendliness": **record how many *nights* went into a stack**, so a
> caption can say "over 4 nights" instead of naming two dates. The entry offered two shapes and named the
> read-time one honest; it is, with one refinement — **night dates cannot be what gets stored**, because a
> night date is already the answer to "for which longitude?". *Hours* are the smallest thing that still
> supports re-bucketing, and a 500-sub night is five of them. Full write-up on the entry under "Autonomy &
> friendliness". Sites touched: `seestack/stack/stacker.py`
> (`_capture_hours`, the `add_stack_run` call), `seestack/io/project.py` (schema **19**, additive
> `capture_hours_json`), `webapp/capture_nights.py` (`capture_night_count`), the four run-shaped API payloads
> (`webapp/schemas.py` `StackRunOut`, `webapp/routers/gallery.py` `GalleryItem`/`BestPicture`,
> `webapp/routers/stats.py` `RecentStack`), `seestack/nameplate.py` (`NameplateFields.nights`),
> `webapp/pipeline.py` (`_nameplate_fields`) and `frontend/src/format.ts` (`captureNightsClause`).

> **Builder 2026-08-30, branch `claude/compassionate-galileo-vsy9vz` (second task) — claim released, shipped
> as v0.314.0.** The follow-on the v0.313.0 work exposed, filed and taken in the same run: the acquisition
> **nameplate** — the caption baked into a shared or printed picture — had *no date at all*, on any picture
> the app has ever exported. It read a `DATE-OBS` card the stacker never wrote (this module's own docstring
> claimed it did). Sites: `seestack/nameplate.py` (`format_acq_range`, `NameplateFields.date_end_iso`),
> `seestack/stack/stacker.py` (`_header_meta` stamps `DATE-OBS`/`DATE-END`), `webapp/pipeline.py`
> (`_nameplate_fields`) and its three call sites. Full write-up on the entry under "Autonomy & friendliness".

> **Builder 2026-08-30, branch `claude/compassionate-galileo-vsy9vz` — claim released, shipped as v0.313.0.**
> The date-honesty class filed under "Autonomy & friendliness" as the generalisation of the v0.311.3 "First
> light" bug, taken at the instance that was a **wrong fact on shared output**: the ready-to-post caption and
> the OS share sheet both asserted a picture was "shot on" / "captured" the run's `timestamp_utc`, i.e. when
> the **stack ran**. The app now records when a stack's subs were taken (schema 18) and every caption reads
> that or says nothing. Full write-up on the entry under "Autonomy & friendliness"; the rest of the sweep
> (provenance lines, the keepsake, the Sky footprint line) is still open there.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-q6uois` — run finished, both claims released.**
> **Shipped one, and stood the other down as a duplicate — this was collision number seven, and it is the one
> the claim-by-site discipline could not have prevented.** Read the process note under "Autonomy &
> friendliness" before picking a North-up follow-on.
> **v0.308.2** (under "Autonomy & friendliness") — the rejection tint over a North-up view. The entry's **alpha
> caution turned out not to apply**, and checking it first — as the entry told the next agent to — is the whole
> reason this was XS and not an afternoon: at the point the endpoint turns anything it holds the **drop-count
> plane**, not the RGBA PNG, so the transparent tint is *rendered at* the rotated size rather than rotated. No
> alpha ever passes through a rotate. The call worth carrying forward is **two turns, not one composed angle** —
> the picture takes the baked turn and then the on-the-fly one, and composing them into a single angle lands on
> a different pixel grid (`np.rot90`'s pixel-centre midpoint vs. `PIL.rotate(expand=True)`'s bounding box).
> A new shared `thumbnail.preview_north_up_remainder_deg` is now the single answer to "what rotation will the
> picture actually receive?", so the preview and the tint cannot drift.
> **Stood down, wholesale:** the run's other claim, **"North up" as a *view* control**, which the
> `…-1bqxek` Builder shipped as **v0.308.0** while this run was building it — **their version is on `main` and
> ships**; mine is dropped rather than re-litigating placement. Theirs puts the control in the **lightbox**,
> which is a better answer than my card-header one (it dodges both filed cautions instead of re-solving them,
> and keeps the header at the three controls v0.293.0 fixed as the phone's limit), and takes the availability
> fact off the **annotations** response rather than the dedicated header-only `…/orientation` endpoint mine
> added — one source of that fact is right, and theirs got there first. **One genuinely additive piece is
> re-applied on top of theirs, in their names:** a `NorthUpViewToggle.test.tsx`, which their commit didn't have
> — the preference's failure modes (a store that throws, a value from a build that spelled it differently) and
> the control's a11y contract were untested.
> The bug queue was checked first and is still genuinely dry: every entry under "Bugs (fix these first)" is
> ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data (the `astap_timeout_s`
> ladder-budget half stays declined — it needs a real cloudy night's subs no agent has).
> Claiming in the run's **first** commit, **by site**, cost under a minute and was pushed immediately. It did
> not help: see the process note.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-1bqxek` — run finished, both claims released.**
> Shipped three, each its own independently-green commit:
> **v0.307.0** (under "Friendliness") — the **"My life list is 14,584 px tall on a phone"** dogfood finding, and
> the entry's own cheap diagnosis was right: the whole bundled catalog was drawn eagerly into one grid. Grouping
> the captured objects ahead of the rest and putting the to-shoot tail behind one count took it to **3,008 px**
> (**−79 %**; desktop 5,236 → 1,453 px), **re-measured with the same probe** as the entry demanded. It was the
> tallest page in the app by nearly 3× and is now level with the Target page. Nothing removed: picking "Still to
> shoot" — the filter that already existed — still lists every one of them, unshortened, and a test pins that.
> **v0.308.0** (under "Autonomy & friendliness") — **North up as a *view*.** The design call worth knowing is
> *where*: putting the toggle in the **lightbox** rather than on the card answers both of the entry's cautions
> outright instead of re-solving them — a plain `<img>` has no pins, scale bar, compass or rejection tint to fall
> out of register — and it keeps the Target card's header row at three controls, which v0.293.0 already
> established is the phone's limit. The endpoint field is taken from `applied_north_up_deg` rather than
> re-derived, and it reports **null** where the turn would do nothing, so the control never appears where it
> would visibly do nothing.
> **v0.308.1** (under "Features that serve real workflows") — a **plain untruth in shipped copy**, found while
> sizing the full-size-zip idea: the card said "Download all" gives you "the full-size pictures themselves", and
> the archive holds each target's **1024 px preview**. Copy fixed and pointed at the per-picture Full-res PNG.
> **Stood down, with the reasoning recorded on its entry:** the *feature* half of that idea. Its filed "prefer
> the TIFF" is a trap — a stack's TIFF is written **linear**, so it opens looking black, and only an editor
> export writes a display-space one. The real full-size picture is the full-res PNG, which has **no file on
> disk**. The honest shape is a job with staged output (an **L**), not `?full=true` on a streaming endpoint.
> The bug queue was checked first and is still genuinely dry: every entry under "Bugs (fix these first)" is
> ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data.
> Claiming in the run's **first** commit, **by site**, and pushing it immediately cost under a minute; `main` had
> not moved by merge time and there was no collision.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-aj7ysy` — run finished, all three claims
> released.** Shipped three, each its own independently-green commit:
> **v0.306.2** (under "Autonomy & friendliness") — the one thing the v0.305.0 Adjust-trapdoor fix deliberately
> left alone: on a **processed** run the panel showed a live render of the linear master, i.e. a picture
> *neither* of its two buttons writes. The picture now follows the button — stored bytes until a slider
> actually moves — and the North-up caution the entry raised was **answered rather than dodged**:
> `…/preview` learned an optional `north_up` that turns the *saved bytes* on the way out, so the rotation can
> be previewed on the picture it belongs to. Deliberately not a flag on `stackArtifactUrl`, whose test pins
> that the stored PNG/FITS/TIFF stay WCS-aligned.
> **v0.306.3** (under "Features that serve real workflows") — slice 1 of the sky-coverage follow-up: the
> sentence is on the Dashboard, asserted **against the shared helper itself** rather than a copy of its
> wording, so the two surfaces cannot drift. Building it exposed that "See it on My map →" would have landed
> on the real-sky atlas (the Sky page picks its map from `localStorage`), which is half of what the slice was
> for — so `/sky` took a `?view=` read once through a new pure `initialSkyMode`.
> **v0.306.4** (under "Autonomy & friendliness") — the Scout's `POST /api/scan` confinement, with the grep the
> entry demanded done first (**nothing passes a `root`**: the frontend posts `{}`, and the startup and
> post-upload scans pass none). The design call worth knowing is that the check is **lexical, not
> `resolve()`-based** — a symlinked NAS share inside `incoming/` is normal on this box and the scan already
> follows such links, so a strict resolve check would refuse a real setup to close nothing; a test pins the
> symlink case so nobody "hardens" it into a break.
> **Three follow-ons filed**, all turned up by the work rather than invented: North-up as a *view* control
> anywhere a picture is shown (the server half now exists, and it is read-only — today the only way to see
> your picture that way is to overwrite it); turning the rejection tint with the same helper, with the alpha
> question that has to be checked first; and the finding that a **sub-folder scan root files its frames as
> "Unsorted"**, so `root` reads like a "re-scan one target" shortcut and is not one.
> The bug queue was checked first and is still genuinely dry: every entry under "Bugs (fix these first)" is
> ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data.
> Claiming in the run's **first** commit, **by site**, and pushing it immediately cost under a minute; `main`
> had not moved by merge time and there was no collision.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-1m28nv` — run finished, all claims released.**
> Shipped three, each its own independently-green commit:
> **v0.305.0** (under "Autonomy & friendliness") — the **History → "Adjust" → Save trapdoor**: on a
> "Process target" run, saving replaced the processed picture with a plain stretch of the linear master,
> silently, and a user who opened the panel only to tick **North up** paid the same price. Both filed halves:
> the warning, and a `keep_processed` save that re-bakes the run's own recipe (rotated, if asked) so the one
> control anybody wants there stops flattening the picture. It also *mends* a drifted run rather than
> declining on it. The plain slider save is untouched, and a test pins that beside the new one.
> **v0.305.1** (same section) — the **"counted less in your stack"** promise. Took the *plumbed* option and
> found the identical sentence on the sibling **focus** card, so both were fixed together. The key call:
> `latest_stack_weighting` reads the newest genuine stack's **FITS provenance** (`WGTMODE`), not
> `options_json` — a run can ask for weighting and have an order-statistic min/max combine ignore it
> (`WGTSKIP`), which for the reader is the same as never asking. A test pins exactly that case.
> **v0.306.0** (under "Features that serve real workflows") — the run's new beginner feature, **"how much of
> the sky have you actually seen?"** under My map. The entry warned it needed an equal-area projection pass;
> it doesn't — `|det(pixel_scale_matrix)|` is the solid angle of one pixel, so the area is exact *before*
> anything is projected, and nothing about how the map is drawn can move it (a test renders the map between
> two reads and asserts it didn't budge).
> **Confirmed pre-existing, not mine:** the pytest quirk the `…-fj2p70` Builder filed reproduced again — a
> hand-picked file list interleaving `tests/webapp/…` and `tests/…` paths lost `tests/webapp/conftest.py`
> and errored every webapp test with `fixture 'client' not found`. Re-running the same files without the
> interleave passed. It still looks exactly like "my change broke everything"; the note is worth keeping.
> Claiming in the run's **first** commit, **by site** (file + function, not just the lead), cost under a
> minute; `main` had not moved by merge time and there was no collision.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-ezix3s` — run finished, all claims released.**
> Worked the standing **"sweep the engine for a POSITION-DEPENDENT metric compared across a whole target"** QA
> lead, and shipped three, each reproduced before fixing:
> **v0.304.2** (top of "Bugs") — a perfectly clear three-panel mosaic scored **0.5008** on the per-run
> `transparency_ratio` and got a **"Hazy night"** badge on History, Gallery and Compare, telling the owner to
> reject their haziest subs on a night when nothing about the weather changed.
> **v0.304.3** (under "Image quality") — the bulk **"reject worst N%"** cut ranked target-wide, so all six of
> its rejections landed in the *sparsest panel*: "drop my haziest 10%" was really "delete a sixth of this
> panel's coverage".
> **v0.304.4** (under "Autonomy & friendliness") — the filed *"first zoom clip is a silent wait"*: a shared
> `DownloadMenuItem` that holds the menu open with a spinner while the server builds the file, keeping the
> plain-link fallback for a browser with no blob path.
> **Stood down, wholesale:** this run also fixed `transparency_trend` (the "clouds rolled in" verdict on the
> same mosaic), and so did the `…-xkjuvl` Builder, concurrently — **theirs landed on `main` first, so mine was
> dropped entirely at merge time** and `main`'s implementation ships. The sixth such collision; the process
> note on it (under "Image quality") has the one defence that would actually have helped, which is *naming the
> site* in the claim, not just the lead.
> **The lead is now closed:** the rest of its candidate list — `stackhealth`, `_fwhm_quality_drift`,
> `best_frame` — was swept and came back clean, recorded on the entry so nobody re-treads it.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-6jgh4j` — run finished, claim released.**
> **Shipped two, the second found by measuring the first.**
> **v0.312.0** (under "Features that serve real workflows") — the filed slice (a): the "what stacking removed"
> tint on the full-screen viewer, on the Gallery and the Target hero. The entry's "ship the stand-down gate
> before the feature" was checked first and turned out **not to apply** — History withdraws the tint because
> opening **Adjust** swaps in a live render of the linear master, and neither of these surfaces has such a
> state — which is what kept it small. The one real piece of work was geometric, and it is a CSS trap worth
> knowing: wrapping the picture and the overlay in a shared positioned box makes the picture's
> `max-height: 100%` resolve against an auto-height ancestor, i.e. no cap, and a tall picture overflows the
> viewer. The overlay is a **sibling** instead, `inset: 0` + `margin: auto`, sharing one fit object and one
> transform string with the picture.
> **v0.312.1** (top of "Bugs") — and then I measured what I had just amplified, and it was **wrong**: the tint
> normalised its alpha against the map's *non-empty* pixels, which stops being the signal as the sub count
> rises. On real 64-sub engine output it washed **94 %** of the frame cyan while the caption called those marks
> satellite trails. Fixed by subtracting the map's own uniform noise floor, inert by construction on every
> sparse map and fenced off where the resize didn't average.
> **Two things stood down with numbers rather than left open:** the sibling **"N spots instead of a
> percentage"** idea (no minimum blob area separates marks from speckle across the sub counts this app is for —
> the summed map has thrown that information away), and the **Compare North-up** entry, whose argument against
> "turn each by its own angle" is recorded there as backwards, with the geometric cost that is the real
> objection and the solved-ness gap that makes its preferred shape harder than it reads.
> **One QA lead filed**, generalised from the bug: sweep every statistic that normalises against its own
> non-empty subset, because that subset stops being the signal as the library grows — the same class as the
> position-dependent-metric sites, along the *how much data went in* axis instead.
> The bug queue was checked first and was dry when the run started: every entry under "Bugs (fix these first)"
> was ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data.

_(nothing else claimed — claim an item here with your branch name)_

> **Builder 2026-08-30, branch `claude/compassionate-galileo-xkjuvl` — run finished, all claims released.**
> **Shipped one, and stood two down as duplicates — read the process note below, this was collisions six AND
> seven in one run.** The one that landed is the **position-dependent-metric sweep** (**v0.304.1**, under
> "Image quality"), which found a real **fourth site** in the bug class behind v0.270.2 / v0.271.0 / v0.272.1:
> the "Clouds & haze" card called a mosaic's move to an emptier panel *"clouds rolled in after 22:21 UTC"*
> (measured 1000 → 450 before, 720 → 720 after). Everything else the QA lead named was swept and is recorded
> as cleared, with the reasoning, in that entry — don't re-tread it.
> **Stood down:** the **recipe-drift guard** and both **"Tonight, live" follow-ons**, both of which the
> `…-fj2p70` Builder shipped concurrently (v0.302.1 / v0.304.0) while this run was building them. Their
> versions are on `main` and this branch takes them wholesale rather than re-litigating naming — but **three
> things this run built that theirs didn't** are re-applied on top of *their* code, in their names: the
> **Adjust → Save** half of the drift (the reachable one — it needs no editor round-trip at all), the
> **`reference-sub` gate** that had been answering where its own info endpoint said "hidden", and
> `AUTO_EDIT_BAKED_LOOK_PREFIX` **registered in `run_meta.py`** so deleting a run takes its stamp with it
> instead of leaving an orphan row. Write-ups are folded into their entries.
> The bug queue was checked first and is still genuinely dry: every entry under "Bugs (fix these first)" is
> ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-fj2p70` — run finished, all three claims
> released.** Shipped all three: the **recipe-drift stamp** (**v0.302.1**, write-up under "Autonomy &
> friendliness") so nothing silently assumes a re-edited "Process target" run's preview still shows its saved
> recipe; the run's new beginner feature, the **zoom clip** (**v0.303.0**, under "Features that serve real
> workflows") — the backlog's "Reveal", renamed because that word already means the one-frame-vs-stack card
> everywhere here — slices (a)+(b), engine → two endpoints → a Save/share item on History and the Target
> page; and both **"Tonight, live" follow-ons** (**v0.304.0**, under "Autonomy & friendliness"), the
> keep-awake reusing the slideshow's helper by *extracting* it rather than copying, and the one line naming
> the other targets from the same night.
> The bug queue was checked first and is still genuinely dry: every entry under "Bugs (fix these first)" is
> ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data.
> **Three notes filed for whoever comes next:** the first zoom clip on a run is a silent lazy build behind a
> plain link (fix shape filed); a corner target can't be centred in its own clip, by design, and the shape
> that would fix it; and a ⚠️ process note about a **pre-existing** pytest quirk — a hand-picked file list that
> interleaves `tests/webapp/…` and `tests/…` paths can lose `tests/webapp/conftest.py` and make every later
> webapp test error `fixture 'client' not found`. It reproduces on untouched `origin/main`, it looks exactly
> like "my change broke everything", and it cost real time this run.
> Claiming in the run's **first** commit and pushing immediately (per the five duplicate-collision process
> notes) again cost under a minute; no collision.

> **Builder 2026-08-30, branch `claude/compassionate-galileo-lcagow` — run finished, all claims released.**
> Shipped two: the ~~invisible reveal on "Process target"~~ dogfood finding (**v0.301.0**, write-up under
> "Features that serve real workflows"), taking the *honest full fix* rather than the interim copy slice — the
> reference sub goes through the run's own stored recipe, so both halves carry identical processing; and both
> cheap taps on **"Your universe"** (**v0.302.0**) — the catalog blurb on the read-out, and **fly to it**.
> The bug queue was checked first and is still genuinely dry: every entry under "Bugs (fix these first)" is
> ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data.
> Claiming in the run's **first** commit and pushing immediately (per the five duplicate-collision process
> notes) again cost under a minute; no collision.

> **Builder 2026-08-29, branch `claude/compassionate-galileo-4txqj1` — run finished, both claims released.**
> Shipped two: **"Share your glow-up"** (**v0.300.0**, write-up under "Features that serve real workflows") —
> all three filed slices, a new pure `seestack/beforeafter.py`, the `before-after.jpg` endpoint and the
> download button on the reveal card; and the **tofu-glyph guard** (**v0.300.1**, under "Friendliness") —
> `tests/glyphs.py` plus a walk over every caption builder in the seven modules that import `ImageDraw`. No
> current caption was affected, which is the honest outcome for a guard filed after its one live instance was
> fixed.
> **Verified in a running app, not just in tests:** `scripts/agent-dogfood.sh` booted a real install with the
> bundled sample, and the composed JPEG came back correct on a plain stack — which is also how the dogfood
> finding below was found (the reveal, and now the share, self-hide on every one-click "Process target" run).
> Filed under "Features that serve real workflows" with the measurement, the honest fix, and the interim
> slice. **Pruned** the Scout's "close the loop when auto-grade brings frames back" idea: grepped before
> starting it and found it already shipped end to end (`auto_regraded_back` → `autoRegradedBackNote`).
> The bug queue was checked first and is still genuinely dry — every entry under "Bugs (fix these first)" is
> ✅ shipped, a ⚪ audit non-finding, or explicitly stood down pending owner data. A fresh adversarial read of
> `stack/accumulator.py` (all three accumulators, the k-set insertion, the min/max drop schedule and its
> coverage semantics) found nothing — recorded so nobody re-treads it this month.
> Claiming in the run's **first** commit and pushing immediately (per the five duplicate-collision process
> notes) cost under a minute; no collision, and `main` never moved while the run ran.

> **Builder 2026-08-29, branch `claude/compassionate-galileo-92mr4d` — run finished, claim released.**
> Shipped one, deep: **"See what stacking removed"** (**v0.299.0**, write-up under "Features that serve real
> workflows") — all three filed slices, engine → endpoint → History toggle, across `stacker.py`,
> `drizzle_path.py`, `output.py`, the memory guard, a new endpoint and the run card. Two findings worth
> carrying forward are in that entry: **min/max rejection is deliberately not mapped** (its drop is structural,
> so a map of it is a canvas-wide wash implying damage that isn't there), and the tint needs a **percentile**
> scale plus an **area-averaging** resize or a single hot pixel and the noise-tail speckle between them bury the
> satellite trail the overlay exists to show. Two follow-ons filed under Ideas (the Gallery lightbox, and a
> connected-component "N spots" count).
> **Stood down** on *"Finish what you started"* after measuring the reshaped slice a previous Builder left on
> it: marginal noise gain is `1 − √(t/(t+1))`, strictly decreasing in `t`, so the proposed "biggest gain per
> hour" sort is **exactly** "least-shot target first" and would stop that card ever finishing anything. The
> ⚠️ note now on that entry has the measured table, why the *line* version was declined too (the Target page
> already answers it from **measured** grain, and `/tonight` carries no `noise_sigma`), and the one shape that
> would earn its place if the owner asks.
> The bug queue was checked first and is genuinely dry: every entry under "Bugs (fix these first)" is either
> ✅ shipped or a ⚪ audit non-finding, and the one live item (the ASTAP ladder's 3× per-frame timeout) is
> explicitly stood down pending owner data — see the Builder note on it. Claiming in the run's **first** commit
> and pushing immediately (per the five duplicate-collision process notes) cost under a minute; no collision.
> **Builder 2026-08-29, branch `claude/compassionate-galileo-1i6x9x` — run finished, all three claims released.**
> Shipped: the finish forecast's **`want` horizon** so a 4+-night goal finally gets a date (**v0.297.1**, under
> "Autonomy & friendliness"), the **one storage alert** a flaking drive now gets instead of two (**v0.297.2**,
> same section), and the run's new beginner feature — **"Tonight, live"** at `/live` (**v0.298.0**, under
> "Features that serve real workflows"). Claiming in the run's **first** commit and pushing immediately (per
> the five duplicate-collision process notes) cost under a minute; no collision this run.
> Two follow-ons filed below, both spotted while building the live page.

> **Builder 2026-08-29, branch `claude/compassionate-galileo-gwhwwd` — run finished, claim released.**
> Shipped three: the stack run's read errors rolled up into a counted sentence on History and the Jobs
> result (**v0.296.5**, under "Image quality"), the two "Show and tell" follow-ons — keep-awake and
> "start the show here" (**v0.296.6**, under "Autonomy & friendliness"), and the observability-aware
> **"When will I finish this?"** forecast (**v0.297.0**, under "Features that serve real workflows").
> **Stood down** on *"Does my colour look right?"* — its premise doesn't hold: measured against the real
> bundled catalog, all 157 entries carry one flat `nebula` type, so emission and reflection (the two
> families whose colour expectations disagree) aren't separable offline. The ⚠️ note now on that entry
> has the measurement and the data task that has to come first.
> Claiming in the run's **first** commit and pushing immediately (per the five duplicate-collision process
> notes) again cost about a minute; no collision this run, and `main` never moved while it ran.

> **Builder 2026-08-29, branch `claude/compassionate-galileo-u3wi1n` — claim released, shipped.**
> Shipped: the ⭐ owner-clarified **real universe map** (true 3D by distance) as **"Your universe"**
> (**v0.296.0**, write-up under "Features that serve real workflows"), **"your last stack didn't run, here's
> the setting that would fix it"** (**v0.296.1**, under "Autonomy & friendliness" — read its note about the
> filed shape missing the unattended case), and the object-label de-confliction that keeps a crowded field
> readable (**v0.296.2**, under "Friendliness"). Claiming in the run's *first* commit and pushing immediately
> (per the five duplicate-collision process notes) cost under a minute; no collision this run.

> **Builder 2026-08-29, branch `claude/compassionate-galileo-eypoyg` — run finished, all claims released.**
> Shipped: the two-pass error-list loose end (**v0.294.3**), "what would it take to print bigger?"
> (**v0.295.0**), and the framing nudge on "Point here tonight" (**v0.295.1**). **Stood down** on *"the picture
> a beginner actually shares is 1024 px wide"* — sizing it against the code showed an **L**, not the filed
> S–M; the ⚠️ Builder note now on that entry has the three pieces, the cache the recipe path needs, and the
> test blast radius. Also pruned *"Was my focus sharp last night?"* as already shipped twice over.
> Claiming in the run's **first** commit and pushing it immediately (per the five duplicate-collision process
> notes) cost about a minute and is worth doing.

---

## QA sweep & audit records moved out of "Bugs" (2026-09-05 bulk move)

The 24 records below were cut verbatim out of `IMPROVEMENTS.md` →
"Bugs (fix these first)", where a clean-sweep record was the first thing every
triaging agent read. None of them is a bug; they are kept so a Scout can rotate
away from ground that has already been swept.

- **⚪ SWEEP RESULT — the rest of the wrong-denominator class is CLEAN; here is the list so nobody re-walks it
  (Builder 2026-09-03, the same sweep that turned up the readiness bug above).** *(No code change wanted.)*
  The class's rule, from the v0.331.2 note: *any per-pixel or per-crop quantity compared against a
  whole-target total is wrong on a mosaic*. Every remaining consumer of `n_frames_used` and of
  `total_exposure_s` was read against it:
  - **`stackhealth.rejection_blind`** — already fixed; it compares against `coverage_max`, the deepest pixel,
    and says *"with no more than N subs overlapping at any one spot"* in the mosaic branch.
  - **`stackhealth.noise_vs_expected` / `noise_yardstick_frames`** — fixed in v0.331.2 / v0.332.0.
  - **`noiseReductionBadge`** — fixed in v0.332.2 (the entry further down).
  - **`stackhealth.roughly_aligned`** — the denominator is `n_frames_used` and that is **right**: a
    roughly-aligned sub is a whole frame, and the population it comes from is the contributing frames. Not a
    per-pixel quantity at all.
  - **`portfolio.py`** (best-picture scoring) and **`restackgain.py`** — both compare target-level facts
    against other *target-level* facts (frame counts against the library's max, a run's count against the
    accepted count). Nothing per-pixel enters.
  - **`imaging_log`'s `n_subs`** — a stated fact about the run, not a claim about a pixel. Correct as it is.
  - **`readiness.noiseReductionHint`** — measured above: the panel count cancels. Correct on a mosaic.
  **All four wrong-denominator instances the sweep found are now shipped**: the readiness goal — the one live
  instance this note used to point at — was fixed in v0.334.0 by the `webapp/field_fulls.py` route the entry
  above named. **If the class is ever re-swept, the generative question is not "does this use
  `n_frames_used`?" but "does this compare a *cleanliness/depth* quantity against a *whole-target* total?"** —
  which is why the fourth instance was in `total_exposure_s` and survived three sweeps that all grepped for
  the frame count.

- **⚪ SCOUT QA RE-AUDIT (2026-09-04, stacking engine core + full-app dogfood) — swept and CLEAN; no new
  verified bug. Recorded so the next Scout rotates away from this ground rather than re-treads it.** Led the
  rotation with `seestack/stack/*` + `seestack/calibrate/*` as AGENTS.md §1 asks, re-read adversarially end to
  end for NaN/coverage semantics, rejection/weighting math, memory bounds and error paths — and it holds,
  confirming the 2026-09-01 note one entry below: `accumulator.py` (all three accumulators; the any-channel
  frame count, the MinMaxReject k-set insertion + count-band degrade, Welford's NaN-for-`n<2` variance),
  `weighting.py` + `photometric.py` (per-panel `pointing_groups` split, geometric-mean floor, the `1/s²`
  photometric-into-combine fold), `calibrate/{apply,masters}.py` (no-data-pedestal→0, flat floor, the
  `bias + (dark−bias)·ratio` exposure-scaling with its two no-data masks, `_bias_applies` never
  double-subtracting), `drizzle_path.py` (the frame-count `neff` gate vs pixfrac-deflated weight, float64
  variance + resolution floor, per-channel reject tally + scatter map), `mosaic.py` (wrap-safe circular-mean
  outlier rejection, px/MP caps), `pointings.py` (union-find single-linkage + ≥2-substantial gate), `align.py`
  (windowed inset/valid mask, the order-1 NaN-propagation ring on both sub-pixel shift paths), and the κ-σ
  pass-2 keep-mask (`_kappa_sigma_keep_mask` — both σ-unknown and mean-unknown widen to keep-all). Combine
  dispatch (`auto_reject_method` / `combine_method` / `auto_reject_depth`) traced clean. **Dogfood pass**
  (`scripts/agent-dogfood.sh`, real app + bundled sample stacked): probe reports **nothing overflowing, no
  console errors**; tallest page 3014 px (phone Target) — bit-for-bit the AGENTS.md §1 baseline, so no IA
  regression. One non-bug surfaced and filed as **log hygiene** under "Infra / maintainability": ~20 benign
  `astropy.stats` NaN warnings per stack (verified result-preserving). Baseline suite green this run
  (**4423 passed, 2 skipped**). **Next Scout: rotate onto the webapp routers not swept recently — `stack.py`/`editor.py`,
  `upload.py`/`scanner.py` ingest, `video.py` — per the 2026-09-02 note directly below; the engine core is
  drained.**

- **⚪ SCOUT QA RE-AUDIT (2026-09-02, webapp routers / ingest / plate-solve / render — swept, mostly CLEAN;
  three verified findings filed above, the rest clean.** This run rotated off the (drained, re-confirmed-clean)
  stacking engine core onto the areas the 2026-09-01 note flagged as higher-marginal. Traced adversarially and
  found **clean**: `seestack/io/ingest.py` (dedup by realpath, the in-place-swap / same-capture / incomplete-
  rewrite recovery, fingerprint backfill), `webapp/watcher.py` (`StabilityTracker` re-arm on in-place rewrite,
  stranded-batch re-offer), `seestack/solve/astap.py` (the 3-rung ladder, timeout-token classification,
  `.ini`/`.wcs` parsing), `seestack/solve/runner.py` (no cross-frame WCS leakage, serial DB apply, RA hours-vs-
  degrees end-to-end), `seestack/qc/noise_ratio.py` + `grading.py` + `metrics.py` (robust z-score / per-panel
  split / caps; the green-channel Bayer layouts; NaN-safe medians), `seestack/render/orient.py` (north-up
  rotation transforms, snap↔PIL split), `webapp/routers/plan.py` (the whole night-planner surface),
  `webapp/routers/gallery.py`/`stats.py` best-picture ranking + night accounting (one low-sev zip-dedup bug
  filed), and `seestack/render/thumbnail.py`/`deepening.py`/`zoomclip.py` (the one asinh full-res parity bug
  filed above; the STF path, NaN-aware downscale, deepening's frozen-STF replay and zoomclip's frame maths all
  clean). Baseline suite green this run (**3844 passed, 2 skipped**). Next Scout: rotate onto the webapp
  **stack.py**/**editor.py** routers, **upload.py**/**scanner.py** ingest, and **video.py** — not swept this run.

- **⚪ SCOUT QA RE-AUDIT (2026-09-01, stacking engine core) — swept and CLEAN; no new verified bug.
  Recorded so the next Scout can rotate away from this ground rather than re-tread it.** Read
  adversarially this run, end to end, hunting NaN/coverage semantics, rejection/weighting math,
  memory bounds and error paths: `seestack/stack/accumulator.py` (all three accumulators — the
  WeightedSum any-channel frame count, the MinMaxReject k-set insertion + graceful count-band
  degrade, and Welford's NaN-for-`n<2` variance contract), `seestack/stack/weighting.py` +
  `photometric.py` (the per-panel `pointing_groups` split, the geometric-mean weight floor, the
  `1/s²` photometric-into-combine variance fold), `seestack/calibrate/{masters,apply}.py` (the
  no-data-pedestal → 0 sanitisation, the flat floor, the exposure-scaling `bias + (dark−bias)·ratio`
  with its two no-data masks, `_bias_applies` never double-subtracting), `seestack/stack/drizzle_path.py`
  (the frame-count `neff` gate vs pixfrac-deflated weight, the float64 variance + resolution floor,
  the per-channel reject tally + scatter map), `seestack/stack/mosaic.py` (wrap-safe circular-mean
  outlier rejection, the px/MP canvas caps), `seestack/stack/pointings.py` (union-find single-linkage,
  the ≥2-substantial-groups soundness gate), `seestack/stack/align.py` (windowed reproject inset/valid
  mask, the order-1 NaN-propagation ring on both sub-pixel shift paths, the `REF_PATCH_MIN_COVERAGE`
  stand-down), and `seestack/stack/output.py` (linear-percentile pack, `_autostretch_for_export` ↔
  saved-preview parity via the shared `EXPORT_AUTOSTRETCH_TARGET_BG`). QC feeders `noise_ratio.py`
  and `grading.py` spot-checked too. Every file carries dense prior-audit provenance and its edge
  cases hold. Baseline suite green this run (**3799 passed, 2 skipped**). The genuinely novel-bug
  surface in the engine core is drained; the higher-marginal QA value has moved to the webapp
  routers / ingest / plate-solve, which this run did not sweep.

- **⚪ AUDIT NOTE (Builder 2026-08-27, swept immediately after fixing the debayer bug — NON-finding, recorded so
  nobody re-treads it) — "a `!= 0` / `> 0` value test standing in for a validity mask" is a bug *class*, and the
  debayer was the only place in the engine where it was wrong.** The pattern is only a bug where **0 is a
  legitimate datum**; everywhere else in `seestack/` it is used where 0 genuinely *means* "none", and is
  correct. Swept and cleared: `drizzle_path.py:375` (`np.where(wht > 0, img, np.nan)` — `wht` is accumulated
  deposit weight, so 0 really is no coverage); `bg/coverage_leveling.py:280` (`cov_int > 0` — a frame count);
  `bg/per_frame.py:453` (`n > 0` — a bin population, paired with the same `np.maximum(n, 1.0)` normalisation);
  `calibrate/masters.py:101` (`mad > 0` — a zero MAD legitimately means "no spread, clip nothing");
  `stack/weighting.py` (`star_count > 0` — zero stars really is unusable). *(Confidence: read, not reproduced —
  each was traced to why 0 means "none" there. Filed as a note, not a bug.)* If a future change makes any of
  those quantities able to be a *measured* zero, this is the shape of the mistake to look for.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #21, branch `claude/vigilant-knuth-gcb43u`) — led with the stacking
  engine per the rotation. Ran my own adversarial reads of `accumulator.py`, `weighting.py`, `photometric.py`,
  `stacker.py` (κ-σ two-pass + min/max wiring + output/preview parity) and `render/thumbnail.py`
  (asinh/STF stretch parity), plus **three parallel adversarial audits**: (1) `drizzle_path.py` + `mosaic.py`;
  (2) `calibrate/apply.py` + `masters.py` + `align.py`; (3) `stacker.py` rejection/combine + `reference.py` +
  `pointings.py`. **Result: the stacking engine core stays clean (11th consecutive sweep)** — no verifiable
  data-integrity bug. Only ONE new verified finding, cosmetic: the `estimate_stack` outlier-exclusion
  discrepancy (pre-run UI estimate only; pixels untouched) — **found, fixed and shipped this run (v0.287.2)**,
  see the SHIPPED entry directly above. Baseline green before starting
  (full headless suite: **3144 passed, 2 skipped, 0 failed**). **Traced NON-findings (recorded so they aren't
  re-chased):** drizzle var-moments share weights so `E[v²]−E[v]²` is Jensen-nonneg; drizzle rejection floor /
  `neff`=true-frame-count / `wht>0 ⇒ count≥1` all sound; drizzle CRPIX `(crpix−0.5)·s+0.5` and half-open
  in-bounds edges correct; mosaic RA-wrap uses circular mean + haversine (wrap/pole-safe); calibrate
  exposure-scaling `bias+(dark−bias)·(t_l/t_d)`, flat floor→1.0, pedestal sanitize→0 all correct and no
  double-bias; `_sigma_clip_mean` mad==0→tol=0 rejects a minority spike while all-NaN degrades to NaN;
  κ-σ pass-2 keep-mask widens to keep-all on σ-unknown (+inf tol) and mean-unknown (keep) so pass-2 data is
  never turned into a NaN gap; photometric `pscales` applied once per fresh array in BOTH passes (no double-
  apply — `align_one` has no caching) with the `1/s²` correction folded only into `combine_weights`;
  `WeightedSum` keeps Σ-weights (`coverage`) separate from the true frame count (`frame_coverage`) and the
  diagnostics/leveling read the honest count; min/max k-insertion sort + band schedule + `rejection_counts`
  match `result()` exactly; asinh/STF both normalise over covered pixels with a robust 99.5th-pct ceiling and a
  soft highlight rolloff, NaN excluded from every stat. **Low-severity edge notes (NOT filed — cannot affect a
  real Seestar run):** CPU vs GPU reproject `cval` (NaN vs 0.0) diverge only on ≤12-px synthetic frames where
  the 3-px edge inset is skipped; `win_valid` is left stale after a sub-pixel refine but every accumulator
  recomputes `valid = np.isfinite(window_image)`, so the stale True at a now-NaN pixel is still excluded
  (benign by contract). Editor/webapp not re-audited this run (drained + clean per #18-#20).**

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #20, branch `claude/vigilant-knuth-upgplg`) — led with the stacking
  engine per the rotation (my own adversarial read), then fanned three parallel audits across the
  **less-recently-swept** subsystems: (1) plate-solve (`seestack/solve/astap.py`, `runner.py`, `bootstrap.py`);
  (2) render / export-parity (`seestack/render/*`, `seestack/stack/output.py` + their `stack.py`/`pipeline.py`
  callers); (3) webapp routers + pipeline auto-stack chain + the `incoming/` guardrail. Also dogfooded the live
  app end to end (`scripts/agent-dogfood.sh`). Result: **THREE verified, reproduced bugs filed at the top of
  this section** — the plate-solve garbage-`.wcs`-stored-as-solved (broken-UX/data-integrity), the full-res PNG
  discarding a saved asinh Adjust (broken-UX), and the Sky-map overlay north-up misalignment (broken-UX/overlay).
  The **stacking engine core stays clean** (10th consecutive sweep) and the **webapp router/pipeline layer +
  `incoming/` read-only guardrail are clean** (independent re-confirmation of audit #19's verdict).**
  **My own engine reads (all NON-findings, traced to guards):** `accumulator.py` — `WeightedSum`/`Welford`/
  `MinMaxReject` all NaN-aware; the min/max k-set insertion sort maintains the k smallest/largest correctly and
  the "full ≥2k+1 / single 3..2k / mean 1-2 / NaN 0" degradation bands are exact with no inf−inf; `frame_coverage`
  counts any-channel contribution so per-channel κ-σ never under-counts. `stacker.py` — `_kappa_sigma_keep_mask`
  widens to keep-all on both σ-unknown (NaN std → +inf tol) and mean-unknown (NaN mean → keep) so pass-2 data is
  never turned into a NaN gap; the two-pass `n_used=min(p1,p2)` guard raises rather than writing a silent all-NaN
  master, with the `not cancel()` clause protecting a routine cancel. `photometric.py` / `weighting.py` /
  `pointings.py` — the mosaic per-panel split (position-dependent metrics judged per panel, seeing/tracking
  target-wide) is sound; `combine_weights_with_photometric` folds the correct `1/s²` inverse-variance term and
  returns the same object (byte-for-byte) when photometric is off; `cluster_pointings` single-linkage union-find
  is wrap- and pole-safe on unit vectors. **Dogfood (happy path clean):** the Target-page IA refactor has landed
  (picture + frames above the fold, banner wall behind a "1 more note" disclosure); Stack and Editor pages read
  clearly with sane defaults and plain-language guidance; no console errors, no overflow, clean boot+stack in the
  server log. Baseline stacking subset green before starting (`test_stack_pipeline`, `test_accumulator`,
  `test_mosaic`, `test_drizzle`, `test_calibrate`, `test_fits_loader` — 218 passed).

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #19, branch `claude/vigilant-knuth-1azkk1`) — led with the stacking
  engine per the rotation, running **four** parallel adversarial audits plus my own read of the stack→result
  autonomy path and the preview↔export stretch. Areas: (1) stacker rejection math + reference pick
  (`stacker.py`, `reference.py` — κ-σ two-pass, per-channel rejection, weight×photometric folding, NaN/coverage,
  memory bounds, dtype); (2) drizzle + mosaic + pointings + output (`drizzle_path.py`, `mosaic.py`,
  `pointings.py`, `output.py` — kernel weight/coverage normalisation, WCS→pixel scaling, seam/bbox, gap=NaN);
  (3) calibrate + align (`calibrate/apply.py`, `masters.py`, `stack/align.py` — sigma-clip master build, dark
  exposure-scaling, flat divide-by-zero, raw-Bayer domain, GPU/CPU cval parity); (4) watcher + ingest + scanner
  + QC (`watcher.py`, `io/ingest.py`, `io/scanner.py`, `qc/*` — stability re-arm, mid-write/0-byte/truncated
  fingerprint, the `incoming/` read-only guardrail, streak/auto-grade reconcile). **Result: the engine and the
  hot path are CLEAN on the corruption axis — no new verified wrong-result or data-loss bug (9th consecutive
  engine sweep).** The `incoming/` read-only contract holds: the only filesystem write touching an incoming path
  anywhere in the four ingest/watcher files is the `shutil.copy2(src, cached)` in ingest's stage-1 copy (source =
  read, destination = library cache) — no `unlink`/`move`/`rename`/`truncate`/`replace`/`open('w')` resolves into
  `incoming/`. Baseline stacking-subset green before starting (`test_accumulator`, `test_stack_pipeline`,
  `test_mosaic`, `test_drizzle{,_reject}`, `test_calibrate`, `test_windowed_stack`, `test_photometric_stack` —
  225 passed).
  **Two low-severity observations, TRACED but deliberately NOT filed as verified bugs** (recorded so a future
  audit doesn't re-tread them):
  1. **κ-σ `n_frames_used` can be *undercounted* (never over) when pass 2 aligns more frames than pass 1.**
     `stacker.py:1893` sets `n_used = min(n_used_p1, n_used_p2)`, surfaced as `n_frames_used` (`:2187`) and
     `n_align_failed` (`:2195`). A frame that throws a transient load error in pass 1 but succeeds in pass 2
     (the exact NAS-blip case the `mean`-unknown keep-guard in `_kappa_sigma_keep_mask` was added to support)
     *does* contribute pixels to the final image (kept where only it covers, via the NaN-mean widening), yet
     `min()` credits only the smaller pass-1 count — so History's NFRAMES / integration time reads slightly low.
     **Not filed because:** the pixels are correct (no corruption); `min()` is the *right* conservative choice
     for the more consequential reverse case (a frame that aligned in pass 1 but failed pass 2 contributed only
     to the reference, not the final image, and `min()` correctly excludes it); the trigger is a rare cross-pass
     I/O race, not reachable by frame content or config; and the error direction is always fail-safe
     (understates, never overstates, integration time). A tidy fix would count `wsum.frame_coverage.max()` (the
     true per-pixel contributing-frame count) instead of `min(p1,p2)`, but that is a hot-path semantics change
     for a cosmetic gain — left for a Builder to weigh, not urgent. Distinct from the v0.136.4 empty-guard fix on
     the same line (that raised on `n_used==0`; this is about the *value* when both are >0). Confidence: traced.
  2. **Streak self-heal re-accepts a still-streaked `auto:streak` frame when streak auto-reject is *off*.**
     `qc/runner.py:115-127`: the `elif prior_reason == "auto:streak"` branch re-accepts on any non-override
     re-QC without also checking `not m.streak_detected`, though its docstring says it fires only when the frame
     is "now clean". Because it's an `elif` under `if auto_reject and m.streak_detected`, it is **unreachable for
     a still-streaked frame on the default path** (`auto_reject_streaks=True`, `scanner.py:562` — the first `if`
     wins). It only differs when a user has *disabled* streak auto-reject, and there re-accepting a previously
     auto:streak frame is arguably the intended semantics (the user opted out of streak rejection, and the
     stack's own per-pixel κ-σ/drizzle rejection still cleans any real trail). **Judged by-design, not a bug**;
     if anything the docstring could add "(or streak auto-reject is now off)". Confidence: traced, low.
  My own reads (all NON-findings): the walk-away auto-stack chain (`pipeline.py` — `_auto_stack_frame_count`,
  `_auto_stack_readability_hold`, `_readability_recovered`, `_auto_stack_degraded_recheck`,
  `_auto_stack_calibration_recheck`) traces correct — the readability preflight holds without stamping, the
  degraded-heal fingerprint fires once and won't re-fire on a heal that comes out thin, and every crash-loop
  marker is cleared on a survivable failure; and the preview↔export stretch (`output._autostretch_for_export` →
  `thumbnail.autostretch`, `_to_uint16_linear`) is NaN-aware everywhere, computes stats over covered pixels only,
  and clamps the MTF midtone — a mosaic's no-data gaps can't skew the black point.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #18, branch `claude/vigilant-knuth-qtz5h4`) — led with the stacking
  engine per the rotation, then fanned three parallel adversarial audits across less-recently-swept areas: the
  **background/gradient** subsystem (`seestack/bg/*`), the **calibration master build+apply**
  (`seestack/calibrate/*`), and the **job manager + video-stacking + library-merge** path (`webapp/jobs.py`,
  `routers/video.py`, `webapp/video.py`, `seestack/io/merge.py`). Result: **one verified, reproduced broken-UX
  bug** in the video re-sharpen path (filed at the top of this section — crop+sharpen stills refuse every
  re-sharpen while advertising the control as editable); **bg, calibrate, and the jobs core all CLEAN.** The
  engine core stays clean (8th consecutive engine sweep). Also shipped the debayer exact-0 fix (v0.284.5,
  above).**
  **What was read adversarially and traced (each a NON-finding except the video bug — traced to a guard):**
  **bg/gradient** (`coverage_leveling.py`, `final_gradient.py`, `per_frame.py`, `sky_poly.py`, `hot_pixels.py`)
  — NaN=no-coverage preserved bit-for-bit through `level_by_coverage`, `suppress_hot_cold_pixels`,
  `subtract_background`, and `final_gradient` (no NaN→0, no number→NaN, inputs copied before mutation); the
  detrend-before-threshold + `_MIN_DETECT_AREA` small-detection drop + faint-extended second pass guard object-
  mask starvation; `fit_sky_poly` requires ≥`n_terms*4` tiles and SVD-`lstsq`, returns `None` on degenerate
  input; the cross-level `polyfit` is try/except-wrapped and every filled offset is `np.clip`-ed to the measured
  `[lo,hi]` envelope (no manufactured seam). *(One GPU-only observation — `_subtract_background_gpu` fills a
  fully-masked tile with the luminance median rather than neighbouring tiles — was traced but is **unreproducible
  without cupy** and nil-impact on fully-NaN tiles, so it is deliberately NOT filed as a bug; noted as a
  low-priority hardening idea below for a GPU-capable follow-up.)*
  **calibrate** (`masters.py`, `apply.py`) — sigma-clip-mean matches intent (MAD clip about the median, mean of
  survivors; `mad==0`/spike `tol=0` branch verified), exposure-scaled dark `bias+(dark−bias)·ratio` sign correct
  and no-data bias/dark pixels restore the right no-correction identity on both scaled and unscaled paths (no
  spurious pedestal), flat divide floors zero/neg/sub-floor/NaN/inf to 1.0, uint16→float32 promotion before any
  subtraction (no wrap), mismatched-shape masters skipped, empty-bundle path returns a fresh array, shared
  masters never mutated. Independently reproduced the four-way no-data pixel matrix.
  **jobs/video/merge** (`webapp/jobs.py`, `routers/video.py`, `webapp/video.py`, `seestack/io/merge.py`,
  `seestack/video/*`) — `_recover_interrupted` runs in `__init__` before `start()` and flips both `running` and
  `queued` → `interrupted`, so no job is left stuck running across a restart; the single-worker cancel↔claim race
  is resolved under one `RLock`; `_persist` serialization and the DB write are both guarded so neither kills the
  worker; ffmpeg `iter_frames` reads exactly one frame at a time with a `finally` that kills+reaps the subprocess
  (memory-bounded, no handle leak, cancel unwinds promptly); the two-pass `select=not(mod(n,stride))` filter
  decodes identical frames in both passes; and **`incoming/` stays strictly read-only** — the video path only
  reads it (via ffmpeg) and writes solely under `<data_root>/video/…`, `merge.py` copies into the *destination*
  project and never touches `incoming/` or rewrites a stored `source_path`. Client capture ids are re-sanitized
  server-side; no client filesystem path reaches disk.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #17, branch `claude/vigilant-knuth-s4y5o3`) — a **depth** sweep that
  led with the stacking engine (`seestack/stack/*` + `seestack/calibrate/*`) across three parallel adversarial
  traces, plus a live-app dogfood. Result: the engine core is clean for the **7th** consecutive sweep; one
  low-severity **debayer** imperfection filed above (genuine exact-0 samples excluded from neighbour
  interpolation — `fits_loader.py`, reproduced) and one cosmetic note below.** Baseline green before starting
  (full headless suite: **3094 passed, 2 skipped** in 11:46). Live app booted + sample stacked end-to-end via
  `scripts/agent-dogfood.sh` (happy path clean: no overflow, no console errors; the Target-page IA refactor has
  landed — picture + frames above the fold, banner wall consolidated behind a "1 more note" disclosure).
  **What was read adversarially and traced to a guard (every item a NON-finding except the debayer one filed
  above):**
  **Accumulators** (`accumulator.py`) — `WeightedSum`/`MinMaxReject`/`Welford` all NaN-aware; the min/max k-set
  insertion sort maintains the k smallest/largest correctly and the ±inf identities never form an inf−inf NaN in
  `result()`; the count-band degradation (≥2k+1 → full trim, 3..2k → single drop, 1-2 → mean, 0 → NaN) is exact;
  `frame_coverage` counts a frame via `valid.any(axis=2)` so a per-channel κ-σ drop can't under-count "frames
  per pixel".
  **Weighting/photometric** (`weighting.py`, `photometric.py`) — geometric-mean weight stays in [min,1];
  per-panel positional medians self-disable on a single field; `combine_weights_with_photometric` folds the
  correct `1/s²` inverse-variance correction and returns the same object (byte-for-byte) when no scaling is
  active.
  **Drizzle/mosaic/pointings** (`drizzle_path.py`, `mosaic.py`, `pointings.py`) — NaN gaps stay NaN (never 0);
  off-canvas frames deposit nothing; `_clip_tolerance` regimes all correct; CRPIX super-res scaling
  `(crpix−0.5)·scale+0.5` and canvas bbox pad are exact; union-find pointing clustering wrap-safe.
  **Align/calibrate** (`align.py`, `calibrate/apply.py`, `calibrate/masters.py`) — flat divide floors zero/neg/
  sub-floor pixels to 1.0; dark exposure-scaling `bias+(dark−bias)·ratio` restores no-data pixels; a frame that
  raises mid-stack is skipped cleanly (never touches the accumulator); reproject no-WCS raises, non-intersecting
  footprint → None; all-float32 (no uint16 wrap).
  **Stacker/output** (`stacker.py`, `output.py`) — κ-σ pass-1/pass-2 keep masks correct (NaN mean → keep, NaN
  std → tol=+inf keep-all for single-coverage edges); memory guard `_estimate_peak_bytes` matches the real plane
  counts; preview↔export share `_autostretch_for_export`; NaN→black consistently across FITS/TIFF/PNG.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #15, branch `claude/vigilant-knuth-ilxa69`) — a **depth** sweep that
  led with the stacking engine and then rotated onto the **QC metric layer** (`seestack/qc/*`) that feeds
  weighting/photometric/grading, plus the stack **output/parity** path. Result: CLEAN — no verified bug this run,
  the **sixth** consecutive clean engine sweep (#10–#15). Baseline green (full headless suite: **3068 passed, 2
  skipped** in 11:30). Live app booted + sample stacked end-to-end via `scripts/agent-dogfood.sh` (happy path
  clean).**
  **What was read adversarially and traced this run (every item below is a NON-finding — traced to a guard, not a
  bug). The engine combine/drizzle/photometric/mosaic/calibrate paths re-confirmed as in #14; new-this-run
  coverage is the QC + output layer:**
  **QC metrics** (`qc/metrics.py`) — `green_channel` promotes the raw Bayer mosaic to float32 *before* averaging
  the two green sites, so summing two bright 16-bit green pixels can't wrap mod 2¹⁶ and corrupt exactly the bright
  stars QC leans on; all four Bayer layouts map G to the correct sites; `median_star_flux`'s `flux[-top_k:]` is
  slice-safe below `top_k` stars; `median_eccentricity`/`median_fwhm` drop non-finite rows before the median so
  one NaN source can't poison the whole frame's metric.
  **QC grading** (`qc/grading.py`) — the `reconsider` pass grades over the *combined* (accepted + previously
  auto-graded) set, which is invariant under auto-grade's own accept/reject moves, so recommendations are a fixed
  point (no reject↔re-accept churn) and the `max_reject_fraction` rail is cumulative for free; the total order
  `(-worst_z, frame_id)` makes the cap boundary deterministic; `star_count==0` (log-undefined, low-is-bad) is
  treated as maximally bad while the same non-positive value on a high-is-bad metric is correctly skipped; the
  per-panel rail bounds the damage inside one mosaic panel before the target-wide cap.
  **QC streaks** (`qc/streaks.py`) — the probabilistic Hough is seeded (`_HOUGH_SEED`) so `streak_count` written
  to the DB is deterministic and QC stays idempotent; compact bright blobs (stars) are removed by an
  elongation+length test on the pixel covariance before line-fitting, so a dense star field isn't mistaken for a
  trail.
  **QC noise-ratio** (`qc/noise_ratio.py`) — the √N "cut your noise ~N×" badge measures a *raw* neighbour-diff
  MAD σ (`Var(Iᵢ₊₁−Iᵢ)=2σ²`) over covered pairs only, with a `_MIN_PAIRS` floor and a two-pass object-drop so a
  bright extended target doesn't inflate the background σ; returns `None` rather than a bogus ratio when either
  side can't be measured.
  **QC sky-quality** (`qc/sky_quality.py`) — the "brighter than usual?" read normalises each frame's sky by
  exposure, keys on the *dominant* (gain, exposure) group so a mixed-setting session can't read as a sky change,
  buckets by observing night (noon-to-noon) with `MIN_FRAMES_PER_NIGHT`/`MIN_NIGHTS` floors, and stays silent
  (returns `None`) rather than guessing when there's no "usual" to compare against.
  **weighting** (`weighting.py`) — geometric mean keeps the weight in `[min_weight, 1.0]`; each factor guards its
  own zero divisor (`frame_sky<=0`, `frame_ecc==0`) as neutral; the position-dependent trio (stars/sky/transp) is
  taken per mosaic panel and the `combine_weights_with_photometric` inverse-variance `1/s²` correction only fires
  on a genuinely-applied scale (returns the same object untouched when photometric is off — byte-for-byte).
  **stack output / preview↔export parity** (`stack/output.py`) — an editor export is stamped `SSDISPLY`
  display-space and written verbatim (no double-stretch) across FITS/TIFF/PNG; `_sanitize_basename` blocks path
  traversal from the web "output name"; `_archive_existing_outputs` moves the whole run set to one timestamped
  basename (siblings stay siblings) rather than overwriting, and the `_framecov` sibling is only written when it
  differs from the weighted coverage map — so an ordinary unweighted stack's output set is exactly the size it
  always was, and the sky-leveling pass reads the honest frame count on a weighted/drizzle mosaic.
  **pointings** (`pointings.py`) — single-linkage union-find on unit vectors is wrap-safe (RA 359↔1) and pole-safe;
  `pointing_groups` returns `None` (one target-wide population, today's behaviour) unless ≥2 groups each carry
  `min_members` eligible frames, so a single-field/unsolved/tightly-packed target is unaffected by every per-panel
  path that gates on it.
  **What was read adversarially and traced this run (every item below is a NON-finding — traced to a guard, not
  a bug):**
  **stack combine** (`accumulator.py`, `stacker.py`) — the `WeightedSumAccumulator` any-channel frame-count
  (`covered = valid.any(axis=2)`) equals `valid[...,0]` in the all-or-nothing common case; the
  `MinMaxRejectAccumulator` k-set insertion-sort keeps the true k smallest/largest and is tie-safe on a
  saturated star core (each extreme *value* subtracted once); the κ-σ two-pass `_kappa_sigma_keep_mask` widens
  to keep-all on both NaN-σ (single-coverage mosaic edge) and NaN-mean (pass-1/pass-2 coverage divergence), so
  the clip can never turn real pass-2 data into a NaN hole; the pass-1 Welford accumulator is `del`-freed before
  pass 2 allocates, so peak stays at the 4 canvas planes the OOM guard charges; `frame_cov=None` is handled by
  every downstream consumer (min/max coverage is already an exact frame count).
  **drizzle** (`drizzle_path.py`) — `_clip_tolerance` computes the variance in float64 to dodge the
  catastrophic-cancellation trap on ~counts² operands, gates rejection on the true **frame count** (`self._count`,
  not the pixfrac-deflated `out_wht`), and disables clipping below the float32 resolution floor so a bright flat
  region can't be punched into NaN; the half-open `[-0.5, N-0.5]` bounds correctly admit edge-band pixel centres;
  `result()` returns `out_img` directly (already a running weighted mean — dividing again would deflate flux).
  **photometric** (`photometric.py`) — neutral-fallback everywhere (no/≤0 transparency → scale 1.0, <3 measured
  frames → whole run neutral), each scale clipped to `[1/max_ratio, max_ratio]`, and mosaic panels normalised
  against *their own* pointing-group median (not one target-wide median that would read intrinsic panel star-field
  differences as haze).
  **mosaic** (`mosaic.py`) — the wrap-safe circular-mean centre RA (`_circ_mean_ra_deg` via `atan2`) is used
  consistently in both outlier passes, so a frame straddling RA=0 isn't flung to ~180° and wrongly rejected;
  MAX_CANVAS_PX + megapixel budget + "never drop >half" guards all hold.
  **calibrate/apply** (`apply.py`) — no-data dark/bias pixels are remembered *before* sanitising to 0 and
  restored to "no correction" on the exposure-scaling path (`bias + (dark−bias)·ratio` never scales a sanitized 0
  into a spurious pedestal); flat non-finite → NaN sentinel (floored to 1.0), never the dark's 0; `apply_raw`
  honours the "returns a fresh array" contract even on the empty-bundle path; the exposure/temperature mismatch
  advisories gate on the *same* `_dark_scaling_applies` predicate the scaling path uses.
  **coverage leveling** (`bg/coverage_leveling.py`) — the per-level detrend-before-threshold, the level-local
  rescue of a starved level's sky, the "too structured to be sky" refusal, and the gapped-extrapolation clamp to
  the measured envelope are all correct; a single-coverage-level (ordinary single-field) stack is byte-for-byte
  unchanged.
  **walk-away orchestration** (`webapp/pipeline.py`) — `_auto_stack_readability_hold` holds (without stamping the
  attempt) when stacking now would land below the min-frames floor *or* thinner than the target's best existing
  stack, gated on `unreadable > 0` so a healthy install is untouched; the crash-loop marker is cleared on a
  *recoverable* exception so a transient I/O error doesn't disable auto-stack forever.
  **Also cross-checked with two independent adversarial subagents** over `align.py`/`pointings.py`/`reference.py`/
  `weighting.py` and `solve/*`/`calibrate/masters.py`: both returned CLEAN with every flagged suspicion traced to
  a real guard (CPU/GPU reproject `cval` parity via the valid-mask inset; union-find path-compression termination;
  sky/ecc divide-by-zero guards; `mad==0` sigma-clip using `tol=0` not `+inf`; uint16→float32 promotion before
  every combine; the `solved = returncode==0 and sidecar.exists()` stale-sidecar gate). Curation + new ideas
  filed alongside (a new beginner feature + an improvement idea — see below).

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #13, branch `claude/vigilant-knuth-ns5hys`) — a **breadth** sweep:
  led with the stacking engine per the rotation, then fanned four independent adversarial audits across the
  areas due for rotation (render, QC, stack combine/weighting/output, and the guardrail-critical webapp
  render/stack/gallery routers), and closed with a **live mixed-quality auto-stack dogfood**. Result: CLEAN
  across the board — no verified bug this run, the fourth consecutive clean engine sweep (#10–#13). Baseline
  green (full headless suite; see the run's commit). Also curated two Ideas entries that had shipped since they
  were filed (see the Autonomy & friendliness section) and added a new beginner feature + two improvement
  ideas.**
  **What was read adversarially and traced (each finding below is a NON-finding — traced to a guard, not a bug):**
  **render** (`thumbnail.py`, `deepening.py`, `orient.py`, `colormap.py`) — every stretch/percentile stat is
  NaN-excluding (`np.nanmin`/`np.nanpercentile`/`_robust_median_sigma(finite)`), uncovered pixels only ever
  become 0/black at the *final display* step (`np.nan_to_num`), never inside a reduction; `np.rot90(k)` verified
  equivalent to `PIL.rotate(k·90)` for the 2×2 and negative-angle cases (no axis/sign error); MTF/asinh
  midtones clamp away from their singularities so no clip/invert path; the baked `_preview.png` and
  `render_preview_png_full_res` share `_autostretch_for_export`, so preview↔export match; the `_downsample_rgb`
  NaN→`nanmin` floor is confirmed no-op on its only two callers (both feed a raw NaN-free sub) — matches the
  latent-not-live note already in this file. **QC** (`streaks.py`, `noise_ratio.py`, `sky_quality.py`,
  `metrics.py`, `runner.py`) — all four Bayer layouts map the two green sites correctly and `green_channel`
  promotes to float32 *before* the add (no uint16 wrap); FWHM border check uses the right axis extents; every
  median metric appends only finite fits so a NaN can't sort a frame to best/worst; streak accept/reject sign
  correct and `detect_streaks` needs area≥8 ∧ major≥80px ∧ elongation≥4 (round stars can't qualify, stationary
  extended targets are re-accepted by `reconcile_streak_rejections`); MAD-on-constant/empty → `None`, not a
  divide. **stack combine/weighting/output** (`accumulator.py`, `weighting.py`, `photometric.py`,
  `pointings.py`, `channel_combine.py`, `output.py`) — `WeightedSum` returns NaN wherever `_weight==0` (gap
  survives), all five quality factors are `clip(min_weight,1)` so the geometric mean is provably in
  `[min_weight,1]`, `combine_weights_with_photometric` folds `1/s²` only on a genuinely-applied scale
  (`s>0 ∧ |s−1|>1e-9`, `s∈[0.5,2]`), photometric `scale=clip(ref/transparency,lo,hi)` guards both `ref>0` and
  `transparency>0`, `pointing_groups` self-disables on a single field (byte-for-byte the OSC path), `_count` is
  uint32 (no overflow), and float32 accumulation error is sub-0.1 ADU at realistic sub counts. **webapp routers**
  (`stack.py`, `pipeline.py`, `gallery.py`) — `{safe}` resolves only through `Library.find_target` (404s an
  unknown, never composes a path), all served artifact paths come from the run row not the client,
  client `output_name` passes through `_sanitize_basename` (`../../etc/passwd`→`etc_passwd`), render query
  params clamp via `_clamp`/typed ints (no NaN crash), every encoder `nan_to_num`+`clip` before uint8, the
  auto-edit vs editor-export full-res render forks correctly (parity), and the gallery/best-pictures/video-stills
  list endpoints all degrade per-item under `except…continue` (the v0.277.6 boundary holds).
  **Live dogfood (the part code review can't do):** built a 14-sub dithered synthetic target (two satellite
  streaks, one hazy sub, per-frame independent noise) and ran the real `run_stack(auto_reject=True,
  quality_weighted=True, photometric_normalize=True)`. Result clean and trustworthy — auto-reject fired
  (`REJFRAC≈0.016`, clipping the streaks), 96.9 % finite with the ragged dither corners correctly NaN, no
  inf/garbage, sky-subtracted linear output centred near zero (median ≈ 2.2 ADU) with star cores preserved
  (p99.9 ≈ 1146 ADU). The stack→result path is doing the right thing end to end.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #12, branch `claude/vigilant-knuth-f9chv3`) — led with the stacking
  engine again, then rotated onto the data-integrity path the last real bug lived in (scanner + ingest), and
  **closed with a live end-to-end auto-stack dogfood** rather than pure code review. Result: CLEAN — no verified
  bug this run. Baseline green: full headless suite **2965 passed, 2 skipped** (822 s), and a 208-test targeted
  re-run over the audited engine areas (accumulator, quality-weighting, photometric-normalize, qc-grading,
  mosaic, drizzle, drizzle-reject, calibrate) passed in 58 s.
  **What was read adversarially and traced:**
  **weighting.py** — the geometric-mean-of-factors keeps every weight in `[min_weight, 1]`; the
  per-panel positional-median split (`group_by_pointing`) self-disables on a single field so an OSC target is
  byte-for-byte unchanged; `combine_weights_with_photometric` folds the `1/s²` inverse-variance correction only
  on a genuinely-applied scale (`|s−1|>1e-9`) and returns the *same object* when photometric is off.
  **photometric.py / pointings.py** — `_pointing_references` normalises each mosaic panel against itself and
  returns `None` (one target-wide reference) unless ≥2 groups each carry `min_frames`; single-linkage
  clustering on unit vectors is wrap/pole-safe. **accumulator.py** — `WeightedSum`/`MinMaxReject`/`Welford`
  all keep NaN = "no coverage" (uncovered → NaN, not 0/0), the min/max k-set sums each side's ±inf identities
  *before* combining so an uncovered pixel can't form inf−inf, and `frame_coverage` counts a frame on **any**
  channel so per-channel κ-σ never under-counts. **mosaic.py** — wrap-safe circular-mean centres, MAD outlier
  drop capped at ½ the frames, and both the pixel-dimension and megapixel budgets fail fast. **drizzle_path.py**
  — the reject gate reads the true `frame_coverage`, not the pixfrac-deflated weight, and the float64
  catastrophic-cancellation floor disables clipping where variance is below ULP(m²). **calibrate/apply.py** —
  no-data dark/bias/flat pixels sanitize to the correct "no correction" identity on both the plain and
  exposure-scaling paths; `apply_raw` honours its "returns a fresh array" contract even on the empty-bundle
  path. **qc/grading.py** — per-panel yardstick fallback to target-wide is sound; the reconsider pass is a
  fixed point over the invariant combined set; the per-panel *and* global reject caps are deterministic.
  **io/scanner.py + io/ingest.py** — the v0.277.4 parent-scoped sibling skip holds; the in-place content-swap
  recovery (`_same_capture` requires a *positive* DATE-OBS match, else conservatively "changed") and the
  fingerprint backfill are correct, and `incoming/` stays strictly read-only (copy, never move). **nightplan
  `session_moon`** — midpoint eval, `end<start` swap, and the shared `_moon_geometry` are consistent with the
  forward-looking warning.
  **Live dogfood (the part code review can't do):** built a 20-sub dithered synthetic target (one satellite
  streak, per-frame independent noise) and ran the real `run_stack(auto_reject, quality_weighted,
  photometric_normalize)`. The result was clean and trustworthy — auto-reject resolved to κ-σ and clipped the
  streak (`rejection_fraction≈0.016`), coverage/NaN handled exactly as designed (97.6 % finite; the ragged
  dither-edge corners are NaN, `coverage_min=0` at the extreme corner, `coverage_max=20`), sky-subtracted
  linear output centred near zero (median ≈ 1.4 ADU), no inf/garbage. The stack→result path is doing the right
  thing end to end.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #11, branch `claude/vigilant-knuth-bsx6dh`) — led the rotation with the
  stacking engine's combine/reject + calibrate + auto-reject resolution, then swept the guardrail-critical
  routers the #10 note pointed at (gallery, stack, **upload**) and the render/proxy path. Result: the engine,
  calibration, routers and render all came back CLEAN again; no verified bug this run. Environment healthy — a
  219-test targeted subset across the audited areas passed (`test_accumulator`, `test_qc_grading`, `test_scanner`,
  `test_stack_pipeline`, `test_gallery`, `test_autostack_hold`, `test_one_sub_vs_stack`; 141 s), and a full
  headless run was green through 50 % (0 failures) before the container reclaimed the background runner twice —
  a resource/harness limit, not a test failure. What was read adversarially and, where a trigger was
  constructible, traced:**
  **accumulator.py** — the `MinMaxRejectAccumulator` k-set insertion keeps `_mins` ascending / `_maxs` descending
  (traced insertion of 5→3→4 at k=2 stays sorted), so `_mins[0]`/`_maxs[0]` are the true extremes the degrade
  bands rely on; the ±inf identities at uncovered slots are summed *per side before combining* so an uncovered
  pixel can't form an inf−inf NaN; the three-band schedule (`≥2k+1` full k-trim / `3≤cnt<2k+1` single min/max /
  `1–2` plain mean / `0` NaN) and the any-channel `frame_coverage` count (so per-channel κ-σ never under-counts a
  frame) are correct; `WelfordAccumulator.variance` is NaN for n<2 — the keep-single-coverage signal the clip
  widens on. **reference.py** — candidate RAs are unwrapped *before* the median/distance/span, so an RA=0
  straddler isn't flung ~180° and passed over for an edge frame; a no-wrap target is untouched. **stacker.py** —
  `_resolve_auto_reject` explicitly forces min/max below 4 frames so the reachable small-κ case
  (`sigma_kappa≲1.155` → `kappa_min_frames`=3) can't pick κ-σ and then silently fall through its `n≥4` gate to
  *no* rejection despite `auto_reject`; `_afford_drizzle_reject` forgives only the reject *pass* on the walk-away
  path (never the canvas — a canvas that doesn't fit is still refused with a named fix) and passes an explicit
  user tick straight through to refuse loudly. **calibrate/apply.py** — `_effective_dark` restores the plain dark
  at genuinely-no-data *bias* pixels and 0 at no-data *dark* pixels, so exposure-scaling can never inject a
  spurious `bias·(1−ratio)` pedestal into every calibrated light; `_bias_applies` / `_dark_scaling_applies` gate
  consistently across `validate`, `calibration_warnings` and `dark_scaling_provenance` (a wrong-shaped bias
  silences neither the warning nor scaling incorrectly); `apply_raw` honours the "returns a fresh array" contract
  even on the empty-bundle path so a caller can't mutate the shared source frame. **qc/metrics.py** —
  `green_channel` promotes to float32 *before* averaging the two green Bayer pixels, so summing two bright 16-bit
  greens can't wrap mod-2¹⁶ and corrupt exactly the stars QC needs; all four Bayer layouts map G correctly.
  **qc/grading.py** — the per-panel reject rail plus the deterministic `(-worst_z, frame_id)` total order make the
  `reconsider` pass a genuine fixed point (no reject↔re-accept churn at the cap boundary); `re_accept` reads the
  *post-cap* list on purpose. **solve/astap.py** — the 3-rung ladder falls through on a per-rung timeout (each rung
  gets the full `timeout_s`, the documented ≤3× cost the #4 note already tracks) and surfaces the tally-able
  `SOLVE_FAILED_TIMEOUT` only when *every* rung timed out; `_parse_astap_ini`'s hard `CRVAL*`/`CDELT2` key access
  sits inside the solved-only guard and its `KeyError` is caught → `solved=True` with null coords, handled
  downstream. **render/thumbnail.py + edit/proxy.py** — preview↔export both route through the STF /
  `_autostretch_for_export`; a display-space editor export is rendered verbatim (a second asinh would
  double-process it); `_nan_aware_area_downscale_plane` keeps a fully-uncovered block as NaN and reads each
  big-endian plane one at a time to stay RAM-bounded on a giant mosaic; the proxy cache is keyed on
  `src_mtime`+`PROXY_VERSION` and returns a writable copy off the memmap. **routers/upload.py** (guardrail-
  critical, §10) — traversal is refused twice (`safe_relpath` per-segment + `confined_dest` symlink-escape
  re-confirm), an *absolute* zip member is refused rather than silently de-slashed, the per-member write is capped
  at the archive's declared `file_size` (which is what makes the pre-write free-space guard *binding* against a
  zip bomb), `zipfile` CRC-verifies each member at EOF, every stream lands as a unique `.part` (concurrent
  same-name POSTs can't interleave) atomically renamed only when complete, and a final-flush ENOSPC still unlinks
  the temp — `incoming/` stays strictly create-new/read. **routers/gallery.py + stack.py** — every cross-target
  read degrades per-item (one corrupt project / bad run / unusable video meta costs one card, never the page); the
  noise-ratio measure slices the memmap window before the float cast (46 MB→0 MB peak); `full-res-png` renders the
  *saved recipe* for a display-space run so the download matches the clicked preview. **pipeline walk-away** —
  `_auto_stack_frame_count` compares against the *max* prior coverage and retries a marked attempt only when
  *fewer* subs are unreadable than last time; `_auto_stack_readability_hold` holds without stamping the marker;
  `_solved_accepted_count` and `_solved_accepted_unreadable` share the identical solved+accepted filter, so
  `readable = offered − unreadable` is exact. **This audit's conclusion:** the stacking engine, calibration,
  routers (upload included) and render are all hardened; the marginal QA value has moved off them — future runs
  should lead with the **editor-reload ↔ proxy-render interaction** and a **running-app dogfood** of the Target /
  Stack information architecture (the standing §1 friendliness priority), and re-audit the engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #10, branch `claude/vigilant-knuth-nozq4i`) — led the rotation back
  onto the stacking engine's per-frame geometry + the walk-away auto-orchestration layer the #8/#9 notes
  pointed at, since the combine/reject core has now come back clean three audits running. Result: the engine
  and the auto-stack helpers both came back CLEAN again; no verified bug this run. Baseline green before
  touching anything (full headless suite). What was read adversarially and, where a trigger was
  constructible, traced:**
  **align.py** — `reproject_rgb_windowed`'s inset/valid mask keeps the GPU `cval=0.0` blend strictly inside
  the trusted interior (valid requires `src ∈ [inset, N-1-inset]`, inset ≥3 for real frames, and the GPU
  path only runs ≥1.5 MP so tiny inset-0 synthetic frames never reach it); the sub-pixel refine propagates
  the NaN coverage ring with the *same* order-1 footprint (`cval=1.0`) so a darkened boundary pixel can't
  survive as covered-but-dimmed; the `SUBPIXEL_SHIFT_CAP_PX` window-pad guard stops a near-cap shift clipping
  real footprint-edge coverage. **mosaic.py** — the primary + iterative outlier passes both use the wrap-safe
  circular-mean centre RA (`_circ_mean_ra_deg`), never a plain corner-RA median, so a frame straddling RA=0
  can't be flung to ~180° and dropped as an outlier; the `max_excluded`/`n//2` caps keep a genuinely wide
  mosaic intact; both the px-dimension and the megapixel budget fail fast with actionable errors. **pointings.py**
  — the union-find single-linkage clusterer (path-halving `find`) is deterministic first-appearance labelled,
  unit-vector wrap/pole safe; `pointing_groups` returns `None` (→ target-wide, today's behaviour) unless ≥2
  substantial panels split, so a single field / unsolved / tightly-packed mosaic is byte-for-byte unchanged.
  **weighting.py** — `_positional_medians` keys the per-panel medians on `f.id` only for id-bearing frames
  (the loop skips `f.id is None` before indexing), falls back to the target-wide median per-metric for a thin
  panel, and `combine_weights_with_photometric` returns the *same* dict object (no `1/s²` fold) when no scale
  is active. **output.py / render/thumbnail.py** — preview↔export both route through `_autostretch_for_export`;
  `already_display` skips the double-stretch on editor exports across FITS/TIFF/PNG; `load_stack_rgb`'s
  memmap-per-channel NaN-aware area downscale keeps the RAM-bounded path and is bit-for-bit the old arithmetic;
  `asinh_stretch`/`autostretch` degenerate-image guards (`hi<=lo`, all-NaN) return black rather than dividing
  by zero; `_archive_existing_outputs` keeps coverage/preview siblings resolvable from one archived basename.
  **drizzle_path.py** — `_clip_tolerance` gates rejection on the true unweighted frame count (`self._count`),
  not the pixfrac-deflated weight, and disables it below the `_VAR_RESOLUTION_FACTOR·m²` cancellation floor
  rather than punching NaN holes through a bright flat region; out-of-bounds pixmap pixels (set to -1) carry
  zero weight and never double-count into the frame-coverage OR. **pipeline auto-orchestration** — the
  frame-count trigger, readability preflight/recovery, calibration-recheck and degraded-heal markers each
  fire once-per-situation, are written *before* the stack (crash-loop-safe) and cleared on a survivable
  failure; `_auto_stack_frame_count` compares against the *max* prior coverage (never a tiny editor-export
  run) and only retries a marked attempt when *fewer* subs are now unreadable. **scanner.py / project.py** —
  re-verified the #8 fix: `_apply_seestar_convention`'s sibling test is parent-scoped, `incoming/` stays
  strictly read-only (every mutation is `shutil.copy2` into the target cache), and
  `reject_seestar_output_frames`'s per-folder ≤2-frame size guard protects a real ≥3-sub bare `<T>/` folder
  (the documented 1–2-sub residual stays non-destructive and recoverable). **This audit's lead-worthy
  conclusion:** the stacking engine and the walk-away orchestration are both hardened; the marginal QA value
  has moved fully off them — future runs should lead with the routers (`stack.py`, `gallery.py`) and the
  editor-reload / proxy render path, and re-audit the engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #9, branch `claude/vigilant-knuth-um7mfa`) — adversarial re-sweep of the
  stacking engine's combine/reject core plus the auto-orchestration helpers the #8 note pointed at next. Result:
  the engine came back CLEAN again; found ONE verified §3 friendliness gap on the Stack form (filed under
  Friendliness, not here — it is not a wrong-result). Baseline green before touching anything (**2935 passed, 2
  skipped** — full headless suite) and the `agent-dogfood.sh` boot+stack+probe pass was clean (no overflow, no
  console errors; the sample stacked to a min/max 6-frame master exactly as `_resolve_auto_reject` predicts for a
  sub-11-frame stack).** What was read adversarially and, where a trigger was constructible, traced:
  **accumulators** (`accumulator.py`) — `WeightedSumAccumulator` any-channel frame count vs Σ-weight coverage
  split is correct; `MinMaxRejectAccumulator`'s k-set insertion sort + the three-band degrade schedule
  (`≥2k+1` / `3≤cnt<2k+1` / `1–2`) subtract each extreme *value* once (tie-safe) and never form an inf−inf NaN
  at an uncovered pixel; `WelfordAccumulator` variance is NaN for n<2 (the keep-single-coverage signal).
  **drizzle** (`drizzle_path.py`) — the `neff`-gated clip tolerance reads the true unweighted frame count (not
  the pixfrac-deflated weight), the `_VAR_RESOLUTION_FACTOR·m²` cancellation floor disables rejection on bright
  flats rather than punching NaN holes, and `result()` returns the library's running weighted mean un-re-divided.
  **κ-σ two-pass** (`stacker.py`) — `_kappa_sigma_keep_mask` widens to keep-all on both "no reference" cases
  (σ-unknown → +inf tol, mean-unknown → keep), pass 1 frees the Welford buffers before pass 2 (the 4-array peak
  the OOM guard charges), and `photometric_scales` is threaded into **both** passes so mean/σ and the clip test
  live in the same scaled domain. **calibrate/apply** — no-data dark/bias pedestals stay "no correction" on both
  the unscaled and exposure-scaled paths; `_bias_applies`/`_dark_scaling_applies` gate shape-mismatched masters
  consistently across `validate`, the warnings, and the provenance stamp. **weighting/photometric** — the
  per-panel-vs-target-wide median split (`group_by_pointing`) and the `1/s²` inverse-variance fold compose
  orthogonally; the geometric-mean weight stays in `[min_weight, 1.0]`. **output.py** — preview↔export both go
  through `_autostretch_for_export`; `already_display` skips the double-stretch on editor exports; the archive
  dance keeps coverage/preview siblings resolvable. **pipeline auto-orchestration** — the frame-count trigger,
  readability preflight/recovery, calibration-recheck and degraded-heal markers each fire once-per-situation and
  clear on a survivable failure (crash-loop-safe); `_stack_target`'s "user chose nothing" guards apply
  `auto_reject`/`quality_weighted`/`drizzle_reject` only when the merged options carry no explicit key.
  **qc** — `grade_frames`'s reconsider set is a fixed point (invariant combined set, deterministic total order,
  per-panel + global caps); `reconcile_streak_rejections`/`apply_qc_result_to_db` only ever *un*-reject an
  `auto:streak`/`qc_error` reason and never touch a `user_override`. **This audit's lead-worthy conclusion:** the
  combine/reject core and the auto-orchestration layer are both hardened; the marginal value has moved off the
  engine — future runs can lead with the render/proxy/editor-reload path and the routers (`stack.py`,
  `gallery.py`), and re-audit the engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #8, branch `claude/vigilant-knuth-gnif14`) — rotated the lead QA onto
  the still-un-swept-in-depth storage/config layer the #5–#7 notes flagged: the watcher-ingest-scanner path,
  `webapp/config.py` load/save + `deps.py`, and both DB migration paths (`project.py`, `library.py`).
  Result: found + FIXED one real WRONG-RESULT data-loss bug in the Seestar scanner (cross-parent `_sub` sibling
  collision → v0.277.4, see Shipped at top of Bugs), plus two verified LOW-severity robustness gaps filed
  below. The DB migrations, the config load path, and the render/preview path came back clean. Dogfood
  end-to-end clean.** Baseline green before touching anything (**2900 passed, 2 skipped** — full headless
  suite). What was traced (and, where a trigger was constructible, reproduced):
  **scanner/ingest** — `incoming/` is strictly read-only (every mutation is `shutil.copy2` into the target
  cache; no `unlink`/`rename`/`move`/truncate in `ingest.py`/`scanner.py`/`merge.py`/`watcher.py`); filename
  traversal neutralised (`CacheManager.stage1_path_for` names files `frame_{id:06d}` and keeps only the
  suffix); `_dedup_key` (realpath) symmetric so a re-scan can't double-add; `_same_capture` / `content_changed`
  in-place-swap recovery (force re-copy, reset QC, clear stale WCS) correct. The one real bug was the folder-
  *convention* sibling test being global rather than same-parent (fixed).
  **config/deps** — the bounds added in `ee81acf` (`watch_*`, `astap_timeout_s`, `cpu_workers`, `seestar_*`)
  are isolated by `_load_resilient`, which resets ONLY the out-of-bounds fields (verified: a legacy
  `seestar_poll_interval_s=0` config keeps `auth_*`, `auto_stack`, `site_lat`, …); no field's own default is
  self-rejecting; `open_target_project` resolves the client `safe` via a parameterised registry lookup +
  DB-stored `safe_name`, so no raw client path reaches the filesystem.
  **DB migrations** — drove a real oldest-layout (v1) in-memory `Project` through `_migrate_schema`: migrates
  v1→current, the pre-existing frame row survives, every expected column is present, and a second run is
  idempotent; every step is `ALTER TABLE ADD COLUMN` / `CREATE … IF NOT EXISTS` guarded by
  `try/except OperationalError`, zero backfill `UPDATE`s (no ordering hazard), no `DROP`/`DELETE`/rewrite;
  `library.py` additive columns all nullable and read-guarded with `in row.keys()`.
  **render/preview** — every stretch/normalisation anchor is NaN-aware (`np.nanmin`/`nanpercentile`/`nanmax`;
  autostretch writes only finite positions so gaps stay black); preview↔export use the same
  `_autostretch_for_export`; `rotate_image_north_up`'s `np.rot90` snap matches `PIL.rotate(expand=True)`
  (verified empirically); constant/flat/single-pixel images degrade to black rather than divide-by-zero.
  **This audit's lead-worthy conclusion:** the storage layer had the one remaining reachable data-loss bug;
  with it fixed, future runs can lead with `jobs.py` / `webapp/pipeline.py`'s remaining auto-orchestration
  helpers, and re-audit the engine + routers only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-27 #7, branch `claude/vigilant-knuth-yeeeim`) — re-audited the stacking
  engine's weighting/photometric/pointing math + the un-swept-in-depth routers the #6 audit flagged
  (`gallery.py`, `plan.py`, `stats.py`, `targets.py`, `video.py`) + `calibrate/masters.py`, adversarially.
  Result: engine core still CLEAN; one real on-path memory gap found and FIXED (masters 3-copy peak → v0.277.3,
  see Shipped); two low-severity latent robustness gaps filed below. Dogfood end-to-end clean.** Baseline green
  before touching anything (**2898 passed, 2 skipped** — full headless suite). Traced by hand and, where cheap,
  probed: `weighting.py` (geometric-mean of five clipped sub-weights, per-panel positional medians with
  target-wide fallback, the `1/s²` photometric variance fold), `photometric.py` (per-panel references, neutral
  fallback when <3 measured, `[1/max_ratio, max_ratio]` clamp), `pointings.py` (union-find single-linkage,
  wrap/pole-safe unit vectors, the ≥2-substantial-groups soundness gate), `reference.py` (RA-unwrap median,
  FWHM tiebreak), `align.py` (windowed-reproject inset valid-mask, order-1 sub-pixel-shift NaN-ring propagation
  with the `cval=1.0` mask, GPU/CPU `cval` parity), and `stacker.py`'s `kappa_min_frames` / `_resolve_auto_reject`
  (n<4 → min/max so `auto_reject` intent is always met) / `_kappa_sigma_keep_mask` (both σ-unknown and
  mean-unknown widenings) / `_afford_drizzle_reject` (walk-away forgiveness of the extra planes) — every
  NaN/coverage/rejection edge I could build was already handled and commented. The routers were swept via three
  focused sub-audits: `gallery.py`/`plan.py`/`stats.py` (path resolution, offset/limit clamps, empty-population
  medians, divide-by-zero, timezone/moon math, missing-column upgrade guards — all correct); `targets.py`/
  `video.py` (client `capture_id`/`safe` sanitised server-side, `incoming/` strictly read-only, ffmpeg decode
  guards, Pydantic-bounded numeric params, additive-column reads); `masters.py` (NaN/inf combine, `mad==0` tol=0
  rejection, uint16→float32 no-overflow, empty/n=1/all-identical, `incoming/` read-only — all sound). **This is
  the seventh consecutive essentially-clean engine-side audit.** Future runs can lead with the watcher-ingest
  storage layer / `deps.py` / `config.py` load path, or re-audit the engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-26 #5, branch `claude/vigilant-knuth-t39r9x`) — led the rotation back
  through the stacking engine's remaining un-swept surface (the accumulators, mosaic-canvas sizing, the
  drizzle path, the video/lucky-imaging stack) and the calibration apply path, all adversarially; came back
  CLEAN — no new verified bug. Also re-ran the running-app dogfood end to end (clean).** Baseline green before
  touching anything (**2872 passed, 2 skipped** — full headless suite). Read adversarially and, where cheap,
  traced breaking cases against the real code:
  `seestack/stack/accumulator.py` — `WeightedSumAccumulator`'s Σweights-vs-frame-count split (`coverage` vs
  `frame_coverage`, the any-channel `valid.any(axis=2)` count that stops per-channel κ-σ from under-counting a
  frame), the `_mask_bool` `(H,W)`→`(H,W,1)` broadcast, `MinMaxRejectAccumulator`'s ±inf k-set identities +
  the ≥2k+1 / 3..2k / 1..2 degrade bands + its structural `rejection_counts`, and `WelfordAccumulator`'s
  `n_safe` divide-guard and unbiased-variance-NaN-for-n<2 contract — all correct.
  `seestack/stack/mosaic.py` — the wrap-safe `_circ_mean_ra_deg`/`unwrap_ra_deg` per-frame centres, the
  robust median+MAD outlier pass with its "never drop >½ the frames" rail, the iterative dimension-cap drop
  loop and the megapixel budget, the half-open CRPIX shift — every RA=0-straddle and bad-solve edge I could
  build was already handled.
  `seestack/stack/drizzle_path.py` — the float64 `E[x²]−E[x]²` variance with its ULP(m²) resolution floor,
  the `neff`=true-frame-count gate (so pixfrac<1/scale>1 weight deflation can't silently disable rejection on
  a low-coverage edge), the Bessel correction applied only to the tol (not the floor test), the `[-0.5,N-0.5]`
  half-open pixel bounds, the any-channel `deposited` frame count, and `intersects` vs deposited-footprint —
  all correct and commented.
  `seestack/video/lucky.py` — the two-pass streaming grade→keep→align→average (flat memory bound), the
  argsort-stable tie-to-earlier keeper that makes "the sharpest frame is always a keeper and is the align
  reference" true by construction, the `_MAX_SHIFT_FRACTION` reject, `cval=np.nan` vacated-edge honesty, and
  the disk-appropriate linear `normalize_for_display` (percentile anchors, not an STF) — correct.
  `seestack/calibrate/apply.py` — the pedestal `nan_to_num` sanitisation with its no-data masks, the flat's
  NaN-not-0 sentinel + `_FLAT_FLOOR`, the `_bias_applies` "never double-subtract the bias through a dark"
  rule, `_effective_dark`'s exposure-scaling with both no-data-mask restorations, and the fresh-array
  contract; **confirmed both `apply_raw` call sites (`align.py:137`, `stacker.py:2183`) pass
  `light_exposure_s=info.exposure_s`, so dark exposure-scaling is never silently skipped for want of the
  exposure.** The one still-open unguarded gap here is the already-filed Bayer-pattern note below (a flat with
  a matching shape but a different CFA phase isn't refused) — trigger requires mixed-source masters, doesn't
  fire on normal Seestar input.
  The dogfood pass (`scripts/agent-dogfood.sh`: real app, bundled M42 sample stacked + auto-processed,
  Playwright 1440 px + 420 px across Target / Stack / Editor / Sky-so-far) reported **nothing overflowing, no
  console errors**; the sample stacks and auto-edits cleanly. **Also confirmed by grep that the walk-away
  `auto` chain already auto-enables `auto_reject`, `quality_weighted`, `photometric_normalize` (mosaic) and
  `drizzle_reject` (`webapp/pipeline.py` ~2417–2462) — so no "single-pass drizzle silently keeps trails"
  autonomy gap exists.** **This is the fifth consecutive clean engine-side audit** — the engine and its
  neighbours are drained. Front of the *actionable* bug queue is unchanged: the ASTAP per-frame timeout-budget
  behavioural half (item (b) at the top of this section), then the two trigger-gated hardening notes (watcher
  in-place re-arm; flat Bayer-pattern guard). Future Scout runs can lead with the still-un-swept-in-depth
  routers (`stack.py`, `editor.py`) / storage and re-audit the engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-26 #6, branch `claude/vigilant-knuth-izen6g`) — took the lead onto the two
  still-un-swept-in-depth routers the prior audits flagged (`stack.py` 2054 lines, `editor.py` 1579 lines),
  swept both adversarially end-to-end (each via a focused sub-audit that traced into the helpers), plus the
  storage / calibration routers by hand and re-ran the running-app dogfood. Result: essentially clean — the one
  latent-robustness gap above (now fixed) was the only actionable finding; no wrong-result or data-integrity
  bug.** Baseline green before touching anything (full headless suite). What was traced:
  `webapp/routers/stack.py` — `_clamp` bounds order at every call site (stretch/black 0..1, crop size 128..4096);
  the noise-crop `_crop_origin`/`_measure_noise_ratio` axis alignment (no transposed crop); the
  trigger→`submit_stack`→`_stack_target` option build (client `dark_path`/etc. popped before use, only master
  *ids* resolved server-side, `validate_stack_options` before submit, `coerce_stack_options` drops `None`/unknown
  so a cleared numeric field can't reach the dataclass); the download/`FileResponse` endpoints (paths from the DB
  row not the URL — no traversal via `kind`/`safe`; literal routes declared before the `/{kind}` catch-all;
  missing→404, corrupt FITS→422); resource cleanup (`proj`+`lib` closed in `finally` on every early-raise path);
  and the single-serial-worker JobManager making a double stack-trigger sequential, not concurrent.
  `webapp/routers/editor.py` — preview↔export parity (both build `EditContext` from the same inputs and run the
  identical op loop; the `already_display` suppression reads different *sources* — `run.options_json` vs the FITS
  `SSDISPLY` card — but both are written together by `_apply_editor_to_run`, and only the fallback autostretch
  reads it, mirrored on both paths; the only genuine preview≠export divergences — `gaia` colour-cal / deconv /
  star-reduce on the proxy — are intrinsic, deliberate, and disclosed to the user in op help + histogram flags);
  recipe coercion (`recipe_from_dict` drops unknown ops, coerces non-mapping params to `{}`, clamps every param —
  malformed input degrades to `Recipe()`); the cache is only the raw *linear* proxy keyed on `run_id`+mtime+version
  (no recipe-hash image cache to go stale; previews `no-store`); export `output_name` sanitised in
  `write_stack_outputs` (no traversal); overwrite archives-and-repoints rather than destroying data. Two truly
  unreachable latent nits noted and deliberately **not** filed (they need a hand-corrupted non-dict `options_json`
  or a non-list presets row, neither of which the app ever writes): `_run_display_space` and `delete_preset`'s
  missing `isinstance` guards. **The routers are now swept in depth and clean.** Front of the *actionable* bug
  queue is unchanged: the ASTAP per-frame timeout-budget behavioural half (item (b) at the top), then the two
  trigger-gated hardening notes (watcher in-place re-arm; flat Bayer-pattern guard). Future runs can lead with
  the remaining routers (`gallery.py`, `plan.py`, `stats.py`, `targets.py`, `video.py`) / the watcher-ingest
  storage layer, and re-audit the engine + editor only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-26 #4, branch `claude/vigilant-knuth-243xct`) — rotated the lead QA off the
  (drained) stacking engine per the prior audits' advice and swept the webapp routers + plate-solve + watcher/
  ingest/QC + the post-processing colour chain; the engine's neighbours hold up, with the two low-severity traced
  findings above the only new open items. Also dogfooded the running app end to end (clean).** Baseline green
  before touching anything (**2790 passed, 2 skipped**). Read adversarially and, where cheap, probed the real code:
  `seestack/post/color_cal.py` (gray-star / Gaia / background-neutral solvers — every scale clamped to
  `[0.05, 20]`, G locked to 1.0, NaN-aware `_apply_scale`, the per-detection `idx`/`matched` index alignment in
  `_solve_gaia` that a length-mismatch would otherwise silently break, the `MAX_CALIBRATION_STARS` cap that stops a
  bad mosaic sky estimate from spawning hundreds of thousands of spurious detections — all correct); the
  `webapp/routers/frames.py` list/preview/reject-summary endpoints (whitelisted `_SORTABLE`, clamped
  `offset`/`limit`, nulls-last sort in *both* directions, server-side path resolution + bayer/int validation on the
  preview so no filename separator or traversal reaches the cache path, `OperationalError`→503 read-only mapping);
  and the plate-solve + watcher/ingest/QC paths via focused sub-audits (the `_store_solve_failed_reason`
  preserve-guard that stops a re-QC-forever loop; the ladder's per-rung timeout fall-through vs fatal-error break;
  `-ra`=deg/15, `-spd`=dec+90 pole-safety; `incoming/` strictly copy-only — `shutil.copy2` the only mutation, no
  `unlink`/`rename`/`move`/truncate anywhere in ingest/watcher, filename traversal neutralised by
  `stage1_path_for` building the stem from `frame_id`; QC modified-z direction, the `min_frames` gate closing the
  empty-population/`_median([])` paths, the 25% rail only ever *reducing* rejections, per-panel fallback to
  target-wide stats). The dogfood pass (`scripts/agent-dogfood.sh`: real app, bundled M42 sample stacked, Playwright
  1440 px + 420 px across the Target / Stack / Editor / History / Library / planner routes) reported **nothing
  overflowing, no console errors**, and by eye the whole journey is polished and beginner-friendly — the Target
  page's IA (prioritised notes + "1 more note" disclosure, picture + actions + frames table above the fold, "Is it
  enough yet?" goal card), the well-defaulted Stack form, and the auto-processed Editor with its plain-language
  pipeline all read cleanly. **Backlog note:** the two items AGENTS.md §1's "2026-08-17 critical bug" paragraph and
  the #2/#3 audit notes call "the front of the bug queue" — the mosaic `photometric_normalize` auto-enable and the
  mosaic per-panel auto-grade — have **both since shipped** (v0.271.0 and v0.270.2), and the `_framecov.fits` prereq
  with them (v0.270.4); so the actionable bug queue is now the two traced findings above plus the older
  trigger-gated hardening notes (flat Bayer-pattern guard; non-windowed `reproject_rgb` inset), none of which fire
  on the normal path. Future Scout runs can keep the lead on the routers (`stack.py`, `editor.py` are still
  un-swept in depth) / video / storage and re-audit the engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-26 #3, branch `claude/vigilant-knuth-r0qxeh`) — re-audited the stacking
  engine + plate-solve + render adversarially (came back CLEAN), and dogfooded the running app end to end,
  where I found and FIXED one real friendliness bug (the mislabelled Lucky-imaging knob — see Shipped).**
  Baseline green before touching anything (2789 passed, 2 skipped). Adversarially re-traced the engine hot path
  and its neighbours, building breaking cases where I could: `accumulator.py` (WeightedSum any-channel
  frame-count vs Σ-weight `coverage`, MinMaxReject k-set tie-safety + the ≥2k+1 / 3..2k / 1..2 degrade bands,
  Welford unbiased-variance NaN-for-n<2), `drizzle_path.py` (the `neff`=true-frame-count gate that stops
  `pixfrac<1`/`scale>1` weight deflation from silently disabling rejection on low-coverage edges; the float64
  `E[x²]−E[x]²` variance with its ULP(m²) resolution floor; half-open `[-0.5, N-0.5]` pixel bounds;
  `intersects` vs deposited-footprint counting), `solve/runner.py` + `solve/astap.py` (the `_store_solve_failed_reason`
  preserve-guard that keeps a `qc_error`/`auto:grade:` prior reason from being clobbered into `solve_failed:`
  and re-QC'd forever; WCS-centre recovery when the `.ini` is unparseable; the adaptive ladder's per-rung
  timeout fall-through vs fatal-error break; `_parse_astap_ini` KeyError → caught → None), `qc/grading.py`
  (modified-z direction-awareness, the practical-significance floors, the per-panel `_pointing_groups` split +
  its per-panel cap, and the `reconsider` fixed-point over the invariant combined set), `stack/pointings.py`
  (union-find single-linkage, `-1` for unsolved, wrap/pole-safety), and `render/deepening.py` (one shared STF
  solved from the deepest *linear* master, `_fit_onto` letterboxing so a portrait night-1 and a landscape
  mosaic night-5 don't squash). Every NaN/coverage edge, rejection band, memory bound and preview↔export path I
  could construct a breaking case for was already handled and commented. **This confirms the engine remains
  drained** (matching the two prior 2026-08-26 audits). The dogfood pass (`scripts/agent-dogfood.sh`: real app,
  bundled sample stacked, Playwright 1440px + 420px) showed a clean Target-page IA (3 notes + a "1 more note"
  disclosure, picture + actions + frames table above the fold), a clean beginner-friendly Stack form, and an
  excellent well-hardened editor — no overflow, no console errors. The one real snag was the Lucky-imaging
  label (below). Front-of-queue for the Builder is unchanged: the two `photometric_normalize`/mosaic
  auto-grade items AGENTS.md §1 points at. Future Scout runs can lead with the webapp routers (`stack.py`,
  `editor.py`, `frames.py`) or ingest/watcher and re-audit the engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-26 #2, branch `claude/vigilant-knuth-xh4b6y`) — rotated the lead QA off
  the (already-drained) stacking engine and adversarially re-audited the subsystems the engine feeds and is
  fed by: QC (`qc/grading.py`, `metrics.py`, `streaks.py`, `noise_ratio.py`), ingest (`io/ingest.py`),
  the folder watcher (`webapp/watcher.py`), the render/output path (`render/orient.py`, `render/deepening.py`,
  `stack/output.py`) and the final-gradient/coverage-leveling bg passes (`bg/final_gradient.py`,
  `bg/coverage_leveling.py`). Came back CLEAN — no new verified bug.** Traced adversarially and, where cheap,
  *probed* the real code: `final_gradient.remove_final_gradient` on an all-NaN canvas (both modes → input
  returned, no crash), a 12×12 image (box clamp degrades, finite out), and `green_channel` on odd dims / a 1×1
  frame (empty array, no uint16 overflow — the float32-before-add cast holds). Re-verified the recently-shipped
  v0.270.4 `{base}_framecov.fits` path end to end: `output._same_map` writes the sibling *only* when Σ-weights ≠
  frame count, `proxy.load_frame_coverage` returns `None` when it's absent, and `coverage_leveling._level_context`
  falls back to the weighted map on `None` — so an unweighted run is byte-for-byte unchanged and a weighted one
  bins panels by the honest count. The per-panel auto-grade split (v0.270.2), the QC `cluster_pointings` None/
  unsolved handling, the ingest fingerprint/`_same_capture` benign-touch-vs-swap logic, the watcher
  stranded-batch re-arm, and the north-up rotation math all held under the edges I could construct. **Also
  confirmed the front-of-queue `photometric_normalize` Builder item's traced site is exact:** `is_mosaic_canvas`
  is set at `stacker.py:1259` and `compute_photometric_scales` is gated at `stacker.py:1321` — the one-line
  mirror `if options.photometric_normalize or is_mosaic_canvas:` lands *after* the canvas is known, and the
  1341–1344 comment already documents the coverage-map shift that v0.270.4 addresses. So both front-of-queue
  Builder items below are accurately shaped. **This confirms the drained state now extends past the engine into
  its neighbours;** future Scout runs can lead with the webapp routers / plate-solve (`solve/`) or re-audit the
  engine only occasionally.

- **⚪ QA AUDIT RESULT (Scout 2026-08-26, branch `claude/vigilant-knuth-7slpid`) — the stacking engine was
  deeply re-audited this run and came back CLEAN: no new verified bug found.** Adversarially traced the whole
  `seestack/stack/*` + `seestack/calibrate/*` hot path, trying to break each edge: `accumulator.py`
  (WeightedSum divide-by-weight NaN semantics, MinMaxReject k-set insertion + the ≥2k+1 / 3..2k / 1..2 degrade
  bands + tie-safety, Welford unbiased-variance NaN-for-n<2 contract), `align.py` (windowed reproject
  `FRAME_EDGE_INSET_PX` valid-mask inset, order-1 sub-pixel-shift NaN-ring propagation with `cval=1.0` mask,
  GPU/CPU `cval` parity), `stacker.py` (κ-σ two-pass keep-mask's σ-unknown/mean-unknown widenings,
  `_resolve_auto_reject` n<4 dispatch — the v0.270.3 fix holds, per-pass in-place photometric-scale multiply,
  `frame_cov` persistence + pass-2 empty-guard), `drizzle_path.py` (neff-gated clip tolerance, float64
  variance-resolution floor, unweighted frame-count coverage, half-open pixel bounds), `mosaic.py` (wrap-safe
  circular-mean outlier rejection, px/megapixel canvas caps), `photometric.py` / `weighting.py` (neutral
  fallbacks everywhere, inverse-variance 1/s² folding), `coverage_leveling.py` (per-level detrend → object
  mask → rescue → gapped-fit-clamp → interpolated fill) and `calibrate/apply.py` (pedestal `nan_to_num`
  sanitisation, exposure-scaling no-data-mask restores, fresh-array contract). Every NaN/coverage edge,
  rejection-math band, memory-bound and preview↔export parity path I could construct a breaking case for was
  already handled and commented. **This mirrors the editor's drained state: the stacking engine is now
  well-hardened.** Future Scout runs can rotate the lead QA subsystem to the webapp routers / watcher /
  ingest-QC / plate-solve / render and re-audit the engine only occasionally. The two trigger-gated hardening
  notes just below (flat Bayer-pattern guard; non-windowed `reproject_rgb` inset) stay open — neither fires on
  the normal Seestar path — plus the still-open mosaic auto-grade / `photometric_normalize` items AGENTS.md §1
  points at.
