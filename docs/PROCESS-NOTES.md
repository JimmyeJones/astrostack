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
