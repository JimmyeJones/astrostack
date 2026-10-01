"""scripts/check-commit-identity.sh — the guard that keeps a personal email out
of this public repository's history (AGENTS.md §10).

Two holes the 2026-09-30 audit found (B-F3, B-F6):

* it read ``git log`` through a process substitution, whose failure ``set -e``
  never sees — so an *invalid* revision range (CI's ``github.event.before`` after
  a force-push, a typo) checked nothing and exited 0, which reads as "clean";
* it looked only at the author and committer fields, never at the message, so a
  ``Co-authored-by:`` trailer carrying the address sailed through.

Every repository here is a scratch one; the addresses are RFC 2606 examples and
never anyone's real one.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check-commit-identity.sh"
pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None,
                                reason="needs bash and git")

GOOD = "noreply@anthropic.com"


def _git(repo: Path, *args: str, email: str = GOOD, name: str = "Claude") -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
        # No global/system config may leak an identity or a hooks path in.
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(repo.parent),
    }
    r = subprocess.run(["git", "-C", str(repo), *args], env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, (args, r.stderr)
    return r.stdout.strip()


def _commit(repo: Path, message: str, *, email: str = GOOD) -> str:
    (repo / "f.txt").write_text(message)
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", message, email=email)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _commit(repo, "root commit")
    return repo


def _check(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=repo,
                          capture_output=True, text=True)


def test_a_clean_range_passes(repo: Path) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "fix: something\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    r = _check(repo, f"{base}..HEAD")
    assert r.returncode == 0, r.stderr


def test_a_personal_author_email_is_refused(repo: Path) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "oops", email="someone@example.com")
    r = _check(repo, f"{base}..HEAD")
    assert r.returncode == 1
    assert "REFUSED" in r.stderr
    # The log is as public as the commit: only the domain is shown.
    assert "someone@" not in r.stderr and "***@example.com" in r.stderr


def test_an_invalid_revision_range_is_an_error_not_a_pass(repo: Path) -> None:
    """B-F3: ``deadbeef..HEAD`` used to check nothing and exit 0."""
    r = _check(repo, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef..HEAD")
    assert r.returncode != 0, "an unreadable range passed as clean"
    assert "cannot list revisions" in r.stderr
    # …and a range that names no revisions at all, the same.
    r = _check(repo, "no-such-branch..HEAD")
    assert r.returncode != 0


def test_a_personal_email_in_a_trailer_is_refused(repo: Path) -> None:
    """B-F6: the message body is published with the commit too."""
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "feat: thing\n\nCo-authored-by: Some One <someone@example.com>")
    r = _check(repo, f"{base}..HEAD")
    assert r.returncode == 1
    assert "message mentions ***@example.com" in r.stderr
    assert "someone@" not in r.stderr


def test_a_personal_email_in_the_body_text_is_refused(repo: Path) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "docs\n\nReported by owner@example.org, thanks.")
    r = _check(repo, f"{base}..HEAD")
    assert r.returncode == 1
    assert "***@example.org" in r.stderr


def test_ordinary_text_that_merely_contains_an_at_sign_passes(repo: Path) -> None:
    """Not every ``x@y`` is an address: package pins, host-style names, retina
    file names and decorators must not turn a clean push red."""
    base = _git(repo, "rev-parse", "HEAD")
    _commit(repo, "\n".join([
        "chore: bump deps",
        "",
        "react@18.2.0 and vite@5.x; the logo is logo@2x.png; the cron runs",
        "as root@nas; @app.get is a decorator and the mail goes via noreply@github.com.",
        "Co-Authored-By: Claude <noreply@anthropic.com>",
        "Signed-off-by: 12345+octocat@users.noreply.github.com",
    ]))
    r = _check(repo, f"{base}..HEAD")
    assert r.returncode == 0, r.stderr


def test_the_pre_push_mode_still_checks_the_pushed_range(repo: Path) -> None:
    base = _git(repo, "rev-parse", "HEAD")
    head = _commit(repo, "bad\n\nCo-authored-by: X <x@example.com>")
    r = subprocess.run(["bash", str(SCRIPT), "--pre-push"], cwd=repo,
                       input=f"refs/heads/main {head} refs/heads/main {base}\n",
                       capture_output=True, text=True)
    assert r.returncode == 1 and "REFUSED" in r.stderr
    # A push whose remote side is unknown to us is refused, never waved through.
    r = subprocess.run(["bash", str(SCRIPT), "--pre-push"], cwd=repo,
                       input=f"refs/heads/main {head} refs/heads/main "
                             f"{'c' * 40}\n",
                       capture_output=True, text=True)
    assert r.returncode == 1


def test_the_ci_job_falls_back_to_a_real_range_never_to_pass() -> None:
    """The workflow's ``identity`` job verifies both ends of the range before
    using it and, when ``before`` is unusable, checks the pushed commits against
    the tags instead of skipping — read as text, since the job cannot run here."""
    ci = (SCRIPT.parents[1] / ".github" / "workflows" / "ci.yml").read_text()
    job = ci.split("identity:", 1)[1].split("\n  version:", 1)[0]
    # The comments explain the history ("used to exit 0"); judge the commands.
    job = "\n".join(ln for ln in job.splitlines() if not ln.lstrip().startswith("#"))
    assert "rev-parse -q --verify" in job
    assert "--not --tags" in job
    assert "merge-base" in job
    # No branch of the job may end in "nothing to check".
    assert "exit 0" not in job
