"""JobRunner serial helper (process pool path is exercised end-to-end via QC)."""

from seestack.core.jobs import run_serial


def _square(x: int) -> int:
    return x * x


def _bad(x: int) -> int:
    raise ValueError(f"oops {x}")


def test_run_serial_collects_results():
    out = run_serial(_square, [(1,), (2,), (3,)])
    assert [r.value for r in out] == [1, 4, 9]
    assert all(r.error is None for r in out)


def test_run_serial_captures_errors():
    out = run_serial(_bad, [(1,), (2,)])
    assert all(r.value is None for r in out)
    assert all(r.error and "ValueError" in r.error for r in out)
