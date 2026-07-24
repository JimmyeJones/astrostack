"""The "how hard is this target for a Seestar?" expectation-setter."""

from __future__ import annotations

from seestack.nightplan import load_catalog
from seestack.objectinfo import identify_object
from seestack.target_difficulty import (
    DifficultyHint,
    target_difficulty,
)


def test_curated_object_returns_its_level_and_a_sentence():
    # M42 (Orion) is the classic easy beginner nebula.
    d = target_difficulty("M42", "nebula")
    assert d is not None
    assert d.level == "easy"
    assert d.label == "Easy"
    assert d.text  # a non-empty, self-contained sentence


def test_faint_large_object_reads_challenging():
    # M33 is the textbook low-surface-brightness "trap" for a beginner.
    d = target_difficulty("M33", "galaxy")
    assert d is not None
    assert d.level == "challenging"
    assert d.label == "Challenging"


def test_star_clusters_are_easy_by_type_rule_without_curation():
    # No cluster is in the curated table; the type rule must still rate them easy.
    for cid, ctype in (
        ("M13", "globular cluster"),
        ("M45", "open cluster"),
        ("M24", "star cloud"),
        ("M73", "asterism"),
        ("M40", "double star"),
    ):
        d = target_difficulty(cid, ctype)
        assert d is not None, cid
        assert d.level == "easy", cid


def test_type_rule_is_case_insensitive():
    d = target_difficulty("M13", "Globular Cluster")
    assert d is not None and d.level == "easy"


def test_unvetted_object_self_hides():
    # A galaxy we didn't curate and which isn't a cluster gets no verdict — we
    # never guess a difficulty from data we don't have (no magnitude/SB in catalog).
    assert target_difficulty("NGC 9999", "galaxy") is None
    # A nebula with no curated entry likewise self-hides.
    assert target_difficulty("NGC 9998", "nebula") is None


def test_id_normalisation_is_separator_insensitive():
    # The curated table is keyed on a normalised id, so spaces/underscores/case in
    # the catalog id or a folder-derived id never miss.
    for cid in ("NGC 7000", "ngc7000", "NGC_7000", "ngc 7000"):
        d = target_difficulty(cid, "nebula")
        assert d is not None, cid
        assert d.level == "challenging", cid


def test_missing_type_still_resolves_curated_objects():
    # A curated object doesn't depend on the type string at all.
    d = target_difficulty("M31", None)
    assert d is not None and d.level == "easy"


def test_missing_type_and_uncurated_self_hides():
    assert target_difficulty("NGC 1234", None) is None


def test_levels_are_only_the_three_known_buckets():
    for cid, level in _iter_curated_levels():
        assert level in {"easy", "moderate", "challenging"}, cid


def test_every_catalog_object_gets_a_valid_or_absent_verdict():
    # Run the resolver over the *real* bundled catalog: every object must either
    # get one of the three buckets or cleanly self-hide (None). No crashes, no
    # stray levels — and clusters/star-fields must all resolve (type rule).
    cluster_types = {
        "globular cluster", "open cluster", "star cloud", "asterism", "double star",
    }
    for obj in load_catalog():
        d = target_difficulty(obj.id, obj.type)
        if d is None:
            # Only non-cluster, uncurated objects may self-hide.
            assert obj.type.lower() not in cluster_types, obj.id
            continue
        assert isinstance(d, DifficultyHint)
        assert d.level in {"easy", "moderate", "challenging"}
        assert d.label and d.text


def test_object_info_carries_the_difficulty_verdict():
    # End-to-end through identify_object: a matched object surfaces its verdict.
    info = identify_object("M_31")
    assert info is not None
    assert info.difficulty is not None
    assert info.difficulty.level == "easy"

    # A challenging one too.
    info = identify_object("M33")
    assert info is not None
    assert info.difficulty is not None
    assert info.difficulty.level == "challenging"


def _iter_curated_levels():
    from seestack.target_difficulty import _CURATED

    yield from _CURATED.items()
