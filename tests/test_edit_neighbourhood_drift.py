"""Every neighbourhood filter in the editor is a *physical* size, or is listed here.

The live preview runs on a **decimated proxy** and the export on the real pixels,
so any radius the editor measures in pixels describes a different patch of sky on
each. ``tests/test_edit_proxy_parity.py`` measures that op by op — but only for
the ops somebody remembered to add, which is how ``tone.scnr``'s green-excess
smoothing sat unscaled for five months on the one-click Auto path while a file
whose whole subject is this class stood beside it (fixed in v0.453.3; a 0.68x
divergence at the owner's own proxy step, invisible to every summary statistic
the whole-recipe parity test measures because it is *localised*).

So the rule is pinned by the source rather than by memory, in the same shape as
``test_no_float_to_integer_pack_truncates_anywhere_in_the_app``: walk
``seestack/edit`` for calls to a scipy-ndimage neighbourhood filter, resolve what
each one was handed as its ``sigma`` / ``size`` / ``footprint``, and require that
it traces back to ``proxy_scale`` — or that it is named below with the reason it
does not have to.

**A new filter call is not a bug; being un-triaged is.** Adding an entry is the
correct fix whenever the size genuinely is not a physical length, but write down
*why*, because that sentence is what the next reader needs and the
number-in-a-constant cannot give them.
"""

from __future__ import annotations

import ast
from pathlib import Path

#: The scipy.ndimage calls whose second argument is a neighbourhood.
_FILTERS = frozenset({
    "gaussian_filter", "gaussian_filter1d", "uniform_filter", "uniform_filter1d",
    "median_filter", "maximum_filter", "minimum_filter", "percentile_filter",
    "grey_opening", "grey_closing", "grey_erosion", "grey_dilation",
    "binary_dilation", "binary_erosion", "binary_opening", "binary_closing",
    "convolve", "correlate",
})

#: Keyword names that carry the neighbourhood, in the order we prefer them.
_SIZE_KW = ("sigma", "size", "footprint", "structure", "weights")

#: Names that make an expression provably about full-resolution pixels. Anything
#: assigned from one of these, at any depth inside the enclosing functions,
#: counts as scaled.
_SCALE_AWARE = ("scaled_px", "_scaled_box", "scnr_noise_sigma",
                "bilateral_sigma_spatial", "proxy_scale")

#: ``file::function::filter(argument)`` → why this one is not a physical length.
#: Keyed on the argument's own source text on purpose: a site that keeps its name
#: but changes what it is handed comes back here for a fresh decision.
_UNSCALED_BY_DESIGN: dict[str, str] = {
    "seestack/edit/coverage_trim.py::_border_trim_rect::binary_dilation(None)":
        "No size argument at all — the default 3x3 structure is *connectivity* "
        "('does this poor-coverage blob touch the outside?'), not a length. One "
        "pixel of adjacency is the right question at every scale, and the rect "
        "this feeds is expressed in fractions of the canvas.",

    "seestack/edit/ops/detail.py::_box_blur3::uniform_filter(width)":
        "A private helper: ``width`` is derived from the ``sigma`` it was "
        "handed, and its one caller (``_chroma_denoise``) passes "
        "``ctx.scaled_px(radius)`` floored at ``_CHROMA_SIGMA_FLOOR``. The "
        "scaling is real, it just lives one call up where this scan cannot "
        "follow it. Pinned behaviourally by "
        "test_the_colour_blotch_smoothing_previews_what_it_exports.",

    "seestack/edit/presets.py::_extended_chroma::uniform_filter(_CHROMA_SMOOTH_PX)":
        "``classify_target``'s cues, not a render. Measured across proxy steps "
        "1/2/3/5/8 on one unchanging synthetic sky: chroma 0.032 on a galaxy and "
        "0.447 on a nebula at *every* step, and the verdict never moves. The box "
        "is there to separate a region's colour from per-pixel grain, and grain "
        "is per-pixel at every scale, so the answer is already scale-robust.",

    "seestack/edit/presets.py::classify_target::uniform_filter(_GEOM_SMOOTH_PX)":
        "Same sweep, same answer: ext_frac 0.0254/0.0254/0.0254/0.0255/0.0253 "
        "across steps 1-8 on the galaxy scene, and galaxy and nebula classify "
        "identically at every step.",

    "seestack/edit/presets.py::classify_target::grey_opening(np.ones((7, 7), dtype=bool))":
        "The star/diffuse separator, and the one site where scale does show — "
        "but only by *declining*. Galaxy and nebula hold their verdict from step "
        "1 to 8; a sparse star cluster decimates below the 'essentially blank' "
        "floor at step 5+ and ``classify_target`` returns None rather than "
        "guessing, which is the honest degradation and needs a >=7500 px canvas "
        "to reach. It suggests a preset chip; it never changes the Auto recipe "
        "except through a stored taste profile, per archetype.",
}


def _enclosing_chains(tree: ast.AST) -> dict[int, list[ast.AST]]:
    """node id → its enclosing functions, innermost first.

    ``ast.walk`` cannot give this, and it matters: ``detail.py``'s sharpen and
    deconvolution both scale their radius in the outer function and filter inside
    a nested ``run``, so a scan that only looks at the innermost scope reports
    two false positives and teaches the reader to ignore it.
    """
    out: dict[int, list[ast.AST]] = {}

    def visit(node: ast.AST, chain: list[ast.AST]) -> None:
        for child in ast.iter_child_nodes(node):
            sub = [child, *chain] if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef)) else chain
            out[id(child)] = sub
            visit(child, sub)

    visit(tree, [])
    return out


def _assignments(fn: ast.AST) -> dict[str, list[str]]:
    """Every ``name = <expr>`` inside one function, as source text."""
    out: dict[str, list[str]] = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out.setdefault(target.id, []).append(ast.unparse(node.value))
        elif (isinstance(node, ast.AnnAssign) and node.value
                and isinstance(node.target, ast.Name)):
            out.setdefault(node.target.id, []).append(ast.unparse(node.value))
    return out


def _traces_to_proxy_scale(text: str, assigns: dict[str, list[str]],
                           depth: int = 0) -> bool:
    if any(word in text for word in _SCALE_AWARE):
        return True
    if depth > 3:
        return False
    try:
        names = {n.id for n in ast.walk(ast.parse(text, mode="eval"))
                 if isinstance(n, ast.Name)}
    except SyntaxError:      # pragma: no cover — an unparseable size expression
        return False
    return any(_traces_to_proxy_scale(value, assigns, depth + 1)
               for name in names for value in assigns.get(name, []))


def _scan() -> tuple[list[str], list[str]]:
    """``(scaled, unscaled)`` keys for every neighbourhood filter in the editor."""
    repo = Path(__file__).resolve().parent.parent
    scaled: list[str] = []
    unscaled: list[str] = []
    for path in sorted((repo / "seestack" / "edit").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        chains = _enclosing_chains(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (node.func.attr if isinstance(node.func, ast.Attribute)
                    else getattr(node.func, "id", ""))
            if name not in _FILTERS:
                continue
            arg = next((ast.unparse(kw.value) for kw in node.keywords
                        if kw.arg in _SIZE_KW), None)
            if arg is None and len(node.args) > 1:
                arg = ast.unparse(node.args[1])
            chain = chains.get(id(node), [])
            assigns: dict[str, list[str]] = {}
            for fn in reversed(chain):        # outermost first; inner shadows
                for key, values in _assignments(fn).items():
                    assigns.setdefault(key, []).extend(values)
            owner = getattr(chain[0], "name", "<module>") if chain else "<module>"
            key = (f"{path.relative_to(repo).as_posix()}::{owner}::"
                   f"{name}({arg})")
            (scaled if _traces_to_proxy_scale(arg or "", assigns)
             else unscaled).append(key)
    return scaled, unscaled


def test_every_editor_neighbourhood_filter_is_scaled_or_explained():
    """The drift guard itself."""
    _, unscaled = _scan()
    surprises = [key for key in unscaled if key not in _UNSCALED_BY_DESIGN]
    assert not surprises, (
        "these neighbourhood filters inside seestack/edit are sized in raw "
        "pixels, so the live preview and the export apply them over different "
        "patches of sky (the tone.scnr class, v0.453.3). Scale the size by "
        "`ctx.scaled_px(...)` — with a floor, and measure what the floor costs "
        "— or add the site to _UNSCALED_BY_DESIGN with the reason:\n  "
        + "\n  ".join(surprises))


def test_the_drift_guard_can_see_an_unscaled_filter():
    """Arm the trap, so the guard above can never rot into an assertion that
    nothing can fail (AGENTS.md §8: a test whose fixture cannot exhibit its bug
    is green for the same reason a broken build is).

    This is the pre-v0.453.3 spelling of ``_scnr``, run through the same
    resolver: a module constant handed straight to ``gaussian_filter``.
    """
    source = (
        "def _scnr(rgb, params, ctx):\n"
        "    g_s = gaussian_filter(g, sigma=_SCNR_NOISE_SIGMA, mode='nearest')\n"
    )
    tree = ast.parse(source)
    chains = _enclosing_chains(tree)
    call = next(n for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "gaussian_filter")
    assigns: dict[str, list[str]] = {}
    for fn in reversed(chains[id(call)]):
        assigns.update(_assignments(fn))
    arg = next(ast.unparse(kw.value) for kw in call.keywords if kw.arg == "sigma")
    assert _traces_to_proxy_scale(arg, assigns) is False

    # …and the shipped spelling passes, so the resolver is not simply strict.
    fixed = ast.parse(
        "def _scnr(rgb, params, ctx):\n"
        "    sigma = scnr_noise_sigma(float(ctx.proxy_scale))\n"
        "    g_s = gaussian_filter(g, sigma=sigma, mode='nearest')\n"
    )
    fixed_chains = _enclosing_chains(fixed)
    fixed_call = next(n for n in ast.walk(fixed)
                      if isinstance(n, ast.Call)
                      and getattr(n.func, "id", "") == "gaussian_filter")
    fixed_assigns: dict[str, list[str]] = {}
    for fn in reversed(fixed_chains[id(fixed_call)]):
        fixed_assigns.update(_assignments(fn))
    assert _traces_to_proxy_scale("sigma", fixed_assigns) is True


def test_the_resolver_follows_a_radius_scaled_in_an_outer_scope():
    """``detail.sharpen`` and ``detail.deconvolve`` scale their radius in the op
    body and filter inside a nested ``run``. A scan that reads only the innermost
    scope calls both of them offenders — and a guard that cries wolf twice on
    correct code is a guard people switch off."""
    scaled, unscaled = _scan()
    for site in ("seestack/edit/ops/detail.py::run::gaussian_filter(radius)",
                 "seestack/edit/ops/detail.py::run::gaussian_filter((ring, ring, 0))",
                 "seestack/edit/ops/tone.py::_scnr::gaussian_filter(sigma)"):
        assert site in scaled, f"{site} should resolve to proxy_scale"
        assert site not in unscaled


def test_the_exemption_list_has_no_stale_entries():
    """An entry that no longer matches any call site is a sentence nobody will
    read again and a hole nobody will notice — the exemption outlives the code it
    was written about. Delete it when the site goes."""
    _, unscaled = _scan()
    stale = sorted(set(_UNSCALED_BY_DESIGN) - set(unscaled))
    assert not stale, (
        "these _UNSCALED_BY_DESIGN entries no longer match any filter call — "
        "the site moved, was renamed, or is now scaled. Remove them:\n  "
        + "\n  ".join(stale))


def test_every_exemption_says_why():
    """A reason, not a shrug. The list is only worth having if each line tells
    the next reader what was checked."""
    for key, reason in _UNSCALED_BY_DESIGN.items():
        assert len(reason) > 80, f"{key}: give the reason, not a label"
