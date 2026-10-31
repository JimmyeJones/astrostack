"""``webapp.run_measure_memo`` — the per-run memo behind the Auto feedback chips."""

from types import SimpleNamespace

from webapp import run_measure_memo as memo


def _run(tmp_path, rid=1, name="master.fits"):
    fp = tmp_path / name
    fp.write_bytes(b"x" * 10)
    return SimpleNamespace(id=rid, fits_path=str(fp), is_mosaic=True)


def test_a_value_comes_back_as_a_copy_the_caller_cannot_edit_the_memo_through(tmp_path):
    memo.clear()
    run = _run(tmp_path)
    key = memo.key_for("classify", tmp_path, run)
    memo.store(key, {"cls": "nebula", "scores": [1.0]})
    got = memo.lookup(memo.key_for("classify", tmp_path, run))
    got["scores"].append(2.0)
    assert memo.lookup(key) == {"cls": "nebula", "scores": [1.0]}


def test_the_key_moves_with_every_file_and_flag_the_measurement_reads(tmp_path):
    memo.clear()
    run = _run(tmp_path)
    key = memo.key_for("taste", tmp_path, run)
    memo.store(key, ("nebula", {}))
    # a coverage sibling appearing is a different picture to measure
    (tmp_path / "master_coverage.fits").write_bytes(b"c")
    assert memo.lookup(memo.key_for("taste", tmp_path, run)) is memo.MISS
    # ...and so is a back-filled mosaic flag, and another kind of answer
    run2 = SimpleNamespace(id=run.id, fits_path=run.fits_path, is_mosaic=None)
    assert memo.key_for("taste", tmp_path, run2) != memo.key_for("taste", tmp_path, run)
    assert memo.key_for("classify", tmp_path, run) != memo.key_for("taste", tmp_path, run)


def test_a_missing_value_is_a_miss_and_none_is_a_value(tmp_path):
    memo.clear()
    run = _run(tmp_path)
    key = memo.key_for("classify", tmp_path, run)
    assert memo.lookup(key) is memo.MISS
    memo.store(key, None)
    assert memo.lookup(key) is None
    assert memo.lookup(None) is memo.MISS
    memo.store(None, 1)  # an unbuildable key is simply not remembered


def test_the_store_is_bounded(tmp_path):
    memo.clear()
    keys = []
    for i in range(memo.MAX_ENTRIES + 5):
        run = _run(tmp_path, rid=i, name=f"m{i}.fits")
        k = memo.key_for("classify", tmp_path, run)
        memo.store(k, i)
        keys.append(k)
    assert memo.lookup(keys[0]) is memo.MISS
    assert memo.lookup(keys[-1]) == memo.MAX_ENTRIES + 4
    memo.clear()
