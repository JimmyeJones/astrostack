#!/usr/bin/env python3
"""What does an automatic drizzle cost in wall-clock? — the instrument.

``seestack/stack/autodrizzle.py`` decides, unattended and on by default, that a
deep dithered target should be re-stacked onto a ×1.5 canvas *with* drizzle's
own two-pass outlier rejection. ``drizzle_path``'s module docstring says that is
"slower per frame than reproject + accumulate, especially with ``scale > 1``"
and that "two-pass rejection roughly doubles that again" — two multipliers, no
numbers, on the one path that runs on the owner's deepest targets (5,477 and
35,894 subs) with nobody watching. This script is the number.

It times **four** real ``run_stack`` runs over the same synthetic subs, so the
two claims can be separated rather than lumped:

1. plain reproject + weighted mean (the picture he gets today),
2. drizzle ×1.0, single pass — drizzle's own cost, with no canvas growth,
3. drizzle ×1.5, single pass — the canvas's share,
4. drizzle ×1.5 + two-pass rejection — what auto-drizzle actually asks for.

**Read the ratios, not the seconds.** The absolute seconds-per-sub belong to the
machine this ran on; the *ratio* between two runs over identical frames is what
transfers to the owner's box, and ``seestack.stacktime.estimate_from_runs``
already measures his own seconds-per-sub per ``stack_cost_class`` from his
finished runs. Multiply the two.

**Run it at more than one frame count.** A single count cannot separate the
per-sub rate from the fixed start-up cost (open the project, pick a reference,
build the canvas, write the outputs), and the two have very different
multipliers — which is why ``stacktime.MIN_BASIS_FRAMES`` exists. Two counts
give a slope; the per-sub ratio is the slope ratio, and it is larger than the
whole-run ratio because the fixed cost is nearly the same for both paths.

Usage (frame size, then one or more frame counts)::

    python scripts/measure_drizzle_cost.py --size 1920x1080 12 24 36

Measured 2026-10-12 on a 4-vCPU container, 1920×1080 subs on one pointing
(``OMP_NUM_THREADS=1``), seconds for the whole ``run_stack``:

===  ======  ===========  ===========  ============  =============
  N   plain  ×1.0 1-pass  ×1.5 1-pass  ×1.5 2-pass    2-pass/plain
===  ======  ===========  ===========  ============  =============
 12   14.83        22.88        33.55         76.50          ×5.16
 24   23.77        46.51        52.10        130.51          ×5.49
 36   33.51        70.06        86.94        212.69          ×6.35
===  ======  ===========  ===========  ============  =============

Per-sub slopes over that span: plain **0.78 s**, ×1.0 single-pass 1.97 s, ×1.5
single-pass 2.23 s, ×1.5 two-pass **5.68 s** — so the marginal cost of an
automatic drizzle is about **×7** a plain sub, of which ~×2.9 is drizzle plus the
canvas and a further ~×2.5 is the second pass. ``drizzle_path``'s "roughly
doubles that again" is right and slightly understated. The ×1.5 single-pass
column is the noisy one on a shared container (its 12→24 and 24→36 slopes
disagree by ~2×); the two columns the decision turns on are the first and last.

**Do not shrink the subs to make it quick.** At 320×240 the whole thing is
under four seconds a run, which is *below this measurement's own noise floor*:
the first timed run pays the lazy imports and allocator warm-up the other three
then reuse, so the plain column comes back slower at 16 subs than at 8 and its
slope goes **negative**. The ratios printed from that are meaningless (and the
script says so when it sees one). Measure at the Seestar's own 1920×1080, which
is the size the owner's subs are and the size the cost is being claimed about.

This is a **finder, not a gate**: nothing asserts a clock. Wall-clock
assertions under an eight-way ``pytest -n`` load are the flake
``docs/AGENT-ENVIRONMENT.md`` warns about, so the measurement lives here and the
conclusion lives in prose beside the constants it prices.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seestack.io.project import FrameRow, Project  # noqa: E402
from seestack.stack.stacker import StackOptions, run_stack  # noqa: E402

#: The four runs, in the order that lets each claim be read off a difference.
CONFIGS: tuple[tuple[str, dict], ...] = (
    ("plain (reproject + weighted mean)", {}),
    ("drizzle x1.0, single pass", {"drizzle": True, "drizzle_scale": 1.0}),
    ("drizzle x1.5, single pass", {"drizzle": True, "drizzle_scale": 1.5}),
    ("drizzle x1.5, two-pass reject", {"drizzle": True, "drizzle_scale": 1.5,
                                       "drizzle_reject": True}),
)


def _build(root: Path, *, width: int, height: int, n: int) -> Project:
    """A single-field target of ``n`` sub-pixel-dithered subs.

    One pointing on purpose: the canvas is then one frame, so the per-pixel depth
    *is* the frame count and the timing is not entangled with a mosaic's union
    canvas. The dither is what drizzle needs to do real work.
    """
    from tests.synth import make_synth_wcs_text, write_seestar_fits

    proj = Project.create(root / "proj", name="M_42")
    raws = root / "raws"
    raws.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        shift = ((i * 0.37) % 3.0, (i * 0.53) % 3.0)
        path = write_seestar_fits(raws / f"f{i}.fit", width=width, height=height,
                                  add_wcs=True, seed=11, noise_seed=200 + i,
                                  n_stars=40, star_shift=shift)
        proj.add_frame(FrameRow(
            source_path=str(path), cached_path=str(path),
            width_px=width, height_px=height, bayer_pattern="RGGB",
            wcs_json=make_synth_wcs_text(width=width, height=height,
                                         crpix_shift=shift),
            ra_center_deg=83.6, dec_center_deg=-5.4, exposure_s=10.0,
        ))
    return proj


def measure(root: Path, *, width: int, height: int, n: int,
            workers: int) -> dict[str, float]:
    proj = _build(root, width=width, height=height, n=n)
    try:
        out: dict[str, float] = {}
        base = None
        print(f"\n{n} subs @ {width}x{height}, {workers} workers")
        for label, extra in CONFIGS:
            opts = {"background_flatten": False, "suppress_hot_pixels": False,
                    "max_workers": workers,
                    "output_name": f"out_{len(out)}"}
            opts.update(extra)
            t0 = time.perf_counter()
            run_stack(proj, StackOptions(**opts))
            dt = time.perf_counter() - t0
            base = dt if base is None else base
            out[label] = dt
            print(f"  {label:36s} {dt:8.2f}s  {dt / n * 1000:8.1f} ms/sub"
                  f"  x{dt / base:5.2f}")
        return out
    finally:
        proj.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    ap.add_argument("counts", nargs="*", type=int, default=[12, 24],
                    help="frame counts to measure (two or more give a slope)")
    ap.add_argument("--size", default="1920x1080",
                    help="sub size WxH (default the Seestar's own 1920x1080)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=None,
                    help="scratch directory (a temporary one by default; it is "
                         "written to, so never point it at a real library)")
    args = ap.parse_args()
    width, height = (int(v) for v in args.size.lower().split("x"))

    rows: dict[int, dict[str, float]] = {}
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(args.out) if args.out else Path(tmp)
        for n in args.counts:
            rows[n] = measure(base / f"n{n}", width=width, height=height, n=n,
                              workers=args.workers)

    counts = sorted(rows)
    if len(counts) >= 2:
        lo, hi = counts[0], counts[-1]
        print(f"\nper-sub slope over {lo} -> {hi} subs")
        plain = None
        for label, _ in CONFIGS:
            slope = (rows[hi][label] - rows[lo][label]) / (hi - lo)
            plain = slope if plain is None else plain
            print(f"  {label:36s} {slope:7.3f} s/sub  x{slope / plain:5.2f}")
        if plain is not None and plain <= 0:
            print("\n!! The plain path's own slope is not positive, so these runs "
                  "are below\n   this measurement's noise floor (the first timed "
                  "run pays the warm-up the\n   others reuse). Every ratio above "
                  "is meaningless. Measure bigger subs --\n   1920x1080, the size "
                  "the owner's are -- or more of them.")
            return 1
        print("\nThe last ratio is what an automatic drizzle costs per sub. "
              "Multiply it by\nthis target's own measured seconds-per-sub "
              "(seestack.stacktime.estimate_from_runs).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
