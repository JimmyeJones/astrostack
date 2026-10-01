"""The release pipeline's two shell guards, run against scratch repositories:

* ``scripts/check-version-bump.sh`` — CI's "Version bump is sane" job. The
  2026-09-30 audit (B-F2) showed two PRs shipping under one number: both bumped
  0.492.4 → 0.492.5 with an identical hunk, the merge was clean, and the second
  was never tagged. The check now refuses a change that touches code without
  changing the version, a version already on main, and a version already tagged.
* ``scripts/release-tags.sh`` — the tagger. It used to tag only the tip and skip
  silently when the version was unchanged; it now goes red on "code changed,
  version didn't", refuses a backwards version, and tags every transition since
  the last tag, so runs can land in any order (B-F4/B-F5) and re-run for free.

Both are the workflows' whole logic; the YAML only picks the refs. What cannot
be exercised here is GitHub's own event payload and concurrency queue.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check-version-bump.sh"
TAGS = ROOT / "scripts" / "release-tags.sh"
pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("git") is None,
                                reason="needs bash and git")


def _env(home: Path) -> dict[str, str]:
    return {
        **os.environ,
        "GIT_AUTHOR_NAME": "Claude", "GIT_AUTHOR_EMAIL": "noreply@anthropic.com",
        "GIT_COMMITTER_NAME": "Claude", "GIT_COMMITTER_EMAIL": "noreply@anthropic.com",
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(home),
    }


class Repo:
    """A clone with a bare ``origin`` — what a checkout on the runner looks like."""

    def __init__(self, tmp_path: Path) -> None:
        self.home = tmp_path
        self.origin = tmp_path / "origin.git"
        self.path = tmp_path / "clone"
        self.git("init", "-q", "--bare", "-b", "main", str(self.origin), cwd=tmp_path)
        self.git("clone", "-q", str(self.origin), str(self.path), cwd=tmp_path)
        self.root = self.commit("first", version="0.1.0", code="a")
        self.push()
        # Like the real repository, the past is tagged: the walk has somewhere
        # to stop. (``--backfill`` is what a repository with no tags at all runs.)
        self.git("tag", "v0.1.0", "HEAD")
        self.git("push", "-q", "origin", "refs/tags/v0.1.0")

    def git(self, *args: str, cwd: Path | None = None) -> str:
        r = subprocess.run(["git", *args], cwd=cwd or self.path, env=_env(self.home),
                           capture_output=True, text=True)
        assert r.returncode == 0, (args, r.stderr)
        return r.stdout.strip()

    def commit(self, msg: str, *, version: str | None = None, code: str | None = None,
               docs: str | None = None) -> str:
        if version is not None:
            (self.path / "webapp").mkdir(exist_ok=True)
            (self.path / "webapp" / "__init__.py").write_text(f'__version__ = "{version}"\n')
        if code is not None:
            (self.path / "app.py").write_text(code)
        if docs is not None:
            (self.path / "docs").mkdir(exist_ok=True)
            (self.path / "docs" / "NOTES.md").write_text(docs)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def push(self) -> None:
        self.git("push", "-q", "origin", "HEAD:main")
        self.git("fetch", "-q", "origin")

    def head(self) -> str:
        return self.git("rev-parse", "HEAD")

    def origin_tags(self) -> dict[str, str]:
        out = self.git("ls-remote", "--tags", str(self.origin))
        return {ln.split("refs/tags/")[1]: ln.split()[0] for ln in out.splitlines()
                if "^{}" not in ln}

    def check(self, head: str, *refs: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(CHECK), head, *refs], cwd=self.path,
                              env=_env(self.home), capture_output=True, text=True)

    def tags(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(TAGS), "--push", *args], cwd=self.path,
                              env=_env(self.home), capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path)


# --------------------------------------------------------------------------- #
# check-version-bump.sh
# --------------------------------------------------------------------------- #

def test_a_bumped_code_change_passes(repo: Repo) -> None:
    base = repo.head()
    repo.commit("fix", version="0.1.1", code="b")
    r = repo.check("HEAD", base, "origin/main")
    assert r.returncode == 0, r.stderr + r.stdout


def test_a_docs_only_change_may_leave_the_version_alone(repo: Repo) -> None:
    base = repo.head()
    repo.commit("docs", docs="notes")
    r = repo.check("HEAD", base, "origin/main")
    assert r.returncode == 0, r.stderr


def test_code_changed_but_version_did_not_is_refused(repo: Repo) -> None:
    """B-F2: the second of two changes under one number looks exactly like this
    once main carries the first."""
    base = repo.head()
    repo.commit("fix without bump", code="b")
    r = repo.check("HEAD", base, "origin/main")
    assert r.returncode == 1
    assert "still 0.1.0" in r.stderr and "touches code" in r.stderr


def test_a_version_already_on_the_current_main_is_refused(repo: Repo) -> None:
    """The PR's recorded base is stale: main moved to 0.1.1 after the branch was
    cut, and the branch bumped to 0.1.1 too. Against the base it looks fine;
    against main as it is now it is a reuse."""
    base = repo.head()
    repo.commit("main moved", version="0.1.1", code="m")
    repo.push()
    repo.git("checkout", "-q", "-b", "pr", base)
    repo.commit("pr bump", version="0.1.1", code="p")
    assert repo.check("HEAD", base).returncode == 0            # what the old job saw
    r = repo.check("HEAD", base, "origin/main")
    assert r.returncode == 1
    assert "already on origin/main" in r.stderr


def test_a_backwards_version_is_refused(repo: Repo) -> None:
    base = repo.head()
    repo.commit("main moved", version="0.2.0", code="m")
    repo.push()
    repo.git("checkout", "-q", "-b", "pr", base)
    repo.commit("pr bump", version="0.1.9", code="p")
    r = repo.check("HEAD", base, "origin/main")
    assert r.returncode == 1 and "went backwards" in r.stderr


def test_a_version_that_is_already_a_tag_is_refused(repo: Repo) -> None:
    base = repo.head()
    other = repo.commit("released elsewhere", version="0.1.1", code="x")
    repo.git("tag", "v0.1.1", other)
    repo.git("checkout", "-q", "-b", "pr", base)
    repo.commit("pr bump", version="0.1.1", code="p")
    r = repo.check("HEAD", base)
    assert r.returncode == 1 and "already a released version" in r.stderr


def test_the_tag_of_this_very_push_is_not_a_reuse(repo: Repo) -> None:
    """On a push to main the tagger may already have tagged HEAD."""
    base = repo.head()
    repo.commit("fix", version="0.1.1", code="b")
    repo.git("tag", "v0.1.1", "HEAD")
    r = repo.check("HEAD", base)
    assert r.returncode == 0, r.stderr


def test_an_unchanged_tagged_version_on_a_docs_change_is_fine(repo: Repo) -> None:
    # v0.1.0 is tagged at the root (the fixture); a docs change keeps carrying it.
    base = repo.head()
    repo.commit("docs", docs="notes")
    r = repo.check("HEAD", base, "origin/main")
    assert r.returncode == 0, r.stderr


def test_an_unreadable_ref_is_an_error_not_a_pass(repo: Repo) -> None:
    r = repo.check("HEAD", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
    assert r.returncode == 2 and "cannot read" in r.stderr


# --------------------------------------------------------------------------- #
# release-tags.sh
# --------------------------------------------------------------------------- #

def test_a_bumped_push_is_tagged_at_its_tip(repo: Repo) -> None:
    before = repo.head()
    repo.commit("fix", version="0.1.1", code="b")
    repo.push()
    r = repo.tags(before)
    assert r.returncode == 0, r.stderr + r.stdout
    assert repo.origin_tags() == {"v0.1.0": repo.root, "v0.1.1": repo.head()}


def test_code_changed_but_version_did_not_goes_red_and_tags_nothing(repo: Repo) -> None:
    before = repo.head()
    repo.commit("bumped once", version="0.1.1", code="b")
    repo.push()
    assert repo.tags(before).returncode == 0
    before = repo.head()
    repo.commit("second change, same number", code="c")
    repo.push()
    r = repo.tags(before)
    assert r.returncode == 1
    assert "second change shipped under one version number" in r.stderr
    assert repo.origin_tags() == {"v0.1.0": repo.root, "v0.1.1": before}


def test_a_docs_only_push_is_not_an_error(repo: Repo) -> None:
    before = repo.head()
    repo.commit("docs", docs="notes")
    repo.push()
    r = repo.tags(before)
    assert r.returncode == 0, r.stderr
    assert "documentation only" in r.stdout


def test_a_backwards_version_goes_red(repo: Repo) -> None:
    repo.commit("up", version="0.2.0", code="b")
    repo.push()
    assert repo.tags().returncode == 0
    before = repo.head()
    repo.commit("down", version="0.1.5", code="c")
    repo.push()
    r = repo.tags(before)
    assert r.returncode == 1 and "went backwards" in r.stderr
    assert "v0.1.5" not in repo.origin_tags()


def test_a_missed_run_is_made_up_for_by_the_next(repo: Repo) -> None:
    """B-F4/B-F5: three merges in quick succession; the middle one's run was
    cancelled from the queue. The third run tags both."""
    repo.commit("A", version="0.1.1", code="a")
    repo.push()
    assert repo.tags().returncode == 0
    b = repo.commit("B (its run was lost)", version="0.1.2", code="b")
    repo.push()
    before = repo.head()
    c = repo.commit("C", version="0.1.3", code="c")
    repo.push()
    r = repo.tags(before)
    assert r.returncode == 0, r.stderr
    tags = repo.origin_tags()
    assert tags["v0.1.2"] == b and tags["v0.1.3"] == c


def test_runs_landing_in_the_wrong_order_still_agree(repo: Repo) -> None:
    """The later push's run goes first; the earlier push's run then finds its tag
    already there and does nothing — no error, no moved tag."""
    a_before = repo.head()
    a = repo.commit("A", version="0.1.1", code="a")
    repo.push()
    b = repo.commit("B", version="0.1.2", code="b")
    repo.push()
    assert repo.tags(a).returncode == 0                # B's run, first
    both = {"v0.1.0": repo.root, "v0.1.1": a, "v0.1.2": b}
    assert repo.origin_tags() == both
    # A's run, afterwards, on the same checkout (HEAD is B — the runner checks
    # out the branch as it is, which is why the walk matters).
    r = repo.tags(a_before)
    assert r.returncode == 0, r.stderr
    assert "Created 0 tags" in r.stdout
    assert repo.origin_tags() == both


def test_rerunning_is_a_no_op(repo: Repo) -> None:
    before = repo.head()
    repo.commit("fix", version="0.1.1", code="b")
    repo.push()
    assert repo.tags(before).returncode == 0
    r = repo.tags(before)
    assert r.returncode == 0 and "Created 0 tags; 1 already existed" in r.stdout


def test_a_tag_that_names_a_different_change_goes_red(repo: Repo) -> None:
    before = repo.head()
    repo.commit("fix", version="0.1.1", code="b")
    repo.push()
    # Someone (a backfill on another line, a hand-made tag) already used the number.
    repo.git("tag", "v0.1.1", before)
    repo.git("push", "-q", "origin", "refs/tags/v0.1.1")
    r = repo.tags(before)
    assert r.returncode == 1 and "used for a different change" in r.stderr


def test_backfill_tags_every_past_version_once(repo: Repo) -> None:
    a = repo.commit("A", version="0.1.1", code="a")
    repo.commit("A docs", docs="x")
    b = repo.commit("B", version="0.1.2", code="b")
    repo.push()
    r = repo.tags("--backfill")
    assert r.returncode == 0, r.stderr
    tags = repo.origin_tags()
    assert tags["v0.1.1"] == a and tags["v0.1.2"] == b and "v0.1.0" in tags
    assert repo.tags("--backfill").returncode == 0
    assert "Created 0 tags" in repo.tags("--backfill").stdout


def test_the_workflows_call_the_scripts_and_queue_rather_than_cancel() -> None:
    """The YAML is the one thing these tests cannot run; pin what it must say."""
    wf = ROOT / ".github" / "workflows"
    ci = (wf / "ci.yml").read_text()
    rt = (wf / "release-tags.yml").read_text()
    assert "scripts/check-version-bump.sh" in ci
    assert "scripts/release-tags.sh --push" in rt
    # The version job runs on pushes to main too, not only on PRs (B-F4).
    version_job = ci.split("\n  version:", 1)[1].split("\n  python:", 1)[0]
    assert "if: github.event_name == 'pull_request'" not in version_job
    assert "git fetch" in version_job and "origin/" in version_job
    # Main's CI runs never cancel each other's queue: one group per commit (B-F5).
    assert "github.sha" in ci.split("concurrency:", 1)[1].split("jobs:", 1)[0]
    # The tagger queues every push rather than dropping the middle one.
    assert "queue: max" in rt and "cancel-in-progress: false" in rt
