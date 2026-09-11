"""The deployed artifact's contract, pinned from the tree CI can read.

AGENTS.md §8: *"Green means the checkout passed, not that the owner's install
works."* The suite and both original CI jobs run against the whole repository;
the image the owner installs is built from ``docker/Dockerfile``'s own, much
smaller file set and runs from ``/app`` off a **non-editable** install. The
2026-09-09 deploy failure lived in exactly that gap, and nothing in the repo
looked at it.

The real check is the ``image`` job in ``.github/workflows/ci.yml``, which builds
the frontend stage and imports the Python half out of a non-editable install of
only what the Dockerfile copies. These tests are the cheap half: they pin the
handful of facts that job depends on, so a change that quietly re-breaks one
fails here in seconds instead of surfacing on the owner's box. They are drift
guards in the same idiom as ``tests/test_project_schema_drift.py`` and the
``pack_unit`` tree sweep — they read files, not pixels.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_DOCKERFILE = _ROOT / "docker" / "Dockerfile"
_COMPOSE = _ROOT / "docker" / "docker-compose.yml"
_CI = _ROOT / ".github" / "workflows" / "ci.yml"
_PYPROJECT = _ROOT / "pyproject.toml"


@pytest.fixture(scope="module")
def dockerfile() -> str:
    return _DOCKERFILE.read_text()


@pytest.fixture(scope="module")
def pyproject() -> dict:
    with _PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


# --------------------------------------------------------------------------
# Qt stays out of the image
# --------------------------------------------------------------------------


def test_pyside6_is_not_a_base_dependency(pyproject: dict) -> None:
    """The image runs ``pip install .[web]``; PySide6 must not ride along.

    Qt is ~650 MB installed and nothing the web app imports needs it —
    ``seestack/core/jobs.py`` defers its single PySide6 import into a function
    and ``seestack/render/`` is deliberately GUI-free. It sat in the base
    ``dependencies`` until v0.418.0, so every deploy carried all of Qt.
    """
    base = " ".join(pyproject["project"]["dependencies"]).lower()
    assert "pyside6" not in base, (
        "PySide6 is back in [project] dependencies, so the image's own "
        "`pip install .[web]` installs ~650 MB of Qt it never imports. "
        "Keep it in the `gui` extra."
    )


def test_the_gui_extra_is_where_qt_lives(pyproject: dict) -> None:
    """Moving it out is only safe if something still asks for it.

    ``scripts/agent-setup.sh`` and AGENTS.md §7 install ``.[dev,web,gui]`` so the
    three pytest-qt tests still have a binding; if the extra vanished, that line
    would resolve to an error rather than quietly skipping them.
    """
    extras = pyproject["project"]["optional-dependencies"]
    assert "gui" in extras, "the `gui` extra is what `.[dev,web,gui]` installs"
    assert any("pyside6" in req.lower() for req in extras["gui"])


def test_the_agent_setup_script_asks_for_the_gui_extra() -> None:
    """Without it a fresh container cannot run the full suite at all.

    ``pytest-qt``'s ``pytest_configure`` hook imports a Qt binding, and with no
    binding installed that is a collection-time INTERNALERROR which aborts the
    whole run — the failure AGENTS.md §7 describes for a missing ``libEGL``,
    reached a second way. The script is how every run installs.
    """
    setup = (_ROOT / "scripts" / "agent-setup.sh").read_text()
    assert "[dev,web,gui]" in setup
    assert '-e ".[dev,web]"' not in setup, (
        "agent-setup.sh installs without the gui extra, so pytest-qt has no "
        "binding and the documented full-suite command cannot run"
    )


# --------------------------------------------------------------------------
# The frontend stage builds what CI tested
# --------------------------------------------------------------------------


def test_the_frontend_stage_installs_from_the_lockfile(dockerfile: str) -> None:
    """``npm ci`` + an unconditional lockfile copy, not ``npm install``.

    ``npm install`` is free to resolve a newer transitive dependency than the
    lockfile names, so the image could be built from a dependency tree the
    frontend job never tested; and the old ``package-lock.json*`` glob meant a
    missing lockfile silently degraded to an unpinned install instead of failing
    the build. CI's own frontend job uses ``npm ci``.
    """
    assert re.search(r"^RUN npm ci\b", dockerfile, re.M), "the frontend stage must use `npm ci`"
    assert not re.search(r"^RUN npm install\b", dockerfile, re.M)
    assert "frontend/package-lock.json " in dockerfile, (
        "copy package-lock.json unconditionally — a `package-lock.json*` glob "
        "makes a missing lockfile a silent unpinned install"
    )
    assert "frontend/package-lock.json*" not in dockerfile


# --------------------------------------------------------------------------
# Every ENV in the image means something
# --------------------------------------------------------------------------

# Read by the interpreter itself rather than by our code, so a tree grep can
# never find them. Anything else must be read somewhere in seestack/ or webapp/.
_ENV_READ_BY_PYTHON = {"PYTHONPATH"}


def test_the_container_port_is_stated_in_exactly_one_place(dockerfile: str) -> None:
    """``ENV ASTROSTACK_PORT`` advertised a knob the image does not have.

    This is the one the v0.418.0 change actually removed, and it is *not* caught
    by the sweep below: ``ASTROSTACK_PORT`` **is** read by our code — in
    ``webapp.main:run``, the ``astrostack-web`` console script — so a tree grep
    finds it and calls it live. What makes it dead *here* is the path this image
    boots: ``CMD`` runs uvicorn directly with ``--port 8000``, and ``EXPOSE`` and
    ``HEALTHCHECK`` hardcode 8000 too. So the rule is consistency rather than
    reachability: either the port is configurable everywhere, or it is stated
    once and not shadowed by an ENV that changes nothing.
    """
    cmd = re.search(r"^CMD (.+)$", dockerfile, re.M)
    assert cmd, "expected a CMD"
    if "ASTROSTACK_PORT" in cmd.group(1):
        return  # the port really is taken from the environment; nothing to pin.
    assert not re.search(r"^ENV\s+ASTROSTACK_PORT=", dockerfile, re.M), (
        "ENV ASTROSTACK_PORT is set, but CMD/EXPOSE/HEALTHCHECK all hardcode "
        "8000 — so changing it does nothing and reads as a supported knob. "
        "Either thread it through all three or drop the ENV."
    )


def test_no_env_in_the_dockerfile_names_something_unread(dockerfile: str) -> None:
    """A weaker, forward-looking companion to the test above.

    It catches an ENV whose name appears **nowhere** in our Python at all. That
    is strictly less than "dead on the path the image boots" — which is why the
    port case needs its own test and cannot lean on this one.
    """
    declared = set(re.findall(r"^ENV\s+([A-Z_][A-Z0-9_]*)=", dockerfile, re.M))
    assert declared, "expected the runtime stage to declare some ENV"

    sources = [
        path.read_text()
        for pkg in ("seestack", "webapp")
        for path in (_ROOT / pkg).rglob("*.py")
    ]
    haystack = "\n".join(sources)

    dead = sorted(
        name
        for name in declared - _ENV_READ_BY_PYTHON
        if name not in haystack
    )
    assert not dead, (
        f"ENV set in docker/Dockerfile but read nowhere in seestack/ or webapp/: {dead}. "
        "Either use it or drop it — a knob that changes nothing is worse than no knob."
    )


# --------------------------------------------------------------------------
# A mistyped data path must fail loudly, not boot empty
# --------------------------------------------------------------------------


def test_the_data_bind_refuses_to_create_a_missing_host_path() -> None:
    """Docker creates a missing short-syntax bind source; that hides a typo.

    Reproduced in the fourth external audit: with ``ASTRO_DATA`` pointing
    somewhere that does not exist, Docker makes the directory and the app comes
    up on a brand-new empty library — which reads to the owner as having lost
    every target. ``create_host_path: false`` turns it into a startup failure
    naming the path.
    """
    compose = _COMPOSE.read_text()
    assert "create_host_path: false" in compose
    assert "ASTRO_DATA" in compose
    assert not re.search(r"^\s*-\s*\$\{ASTRO_DATA[^}]*\}:/data\s*$", compose, re.M), (
        "the /data bind is back to the short syntax, which lets Docker create a "
        "mistyped host path and boot on an empty library"
    )


# --------------------------------------------------------------------------
# CI actually looks at the image
# --------------------------------------------------------------------------


def test_ci_builds_the_frontend_stage_and_smokes_the_python_half() -> None:
    """The job this whole file exists to protect must still be there.

    Two jobs against the checkout is the state that let the 2026-09-09 deploy
    failure through. This asserts the third one's two halves by the commands
    that make them meaningful, not by its name.
    """
    ci = _CI.read_text()
    assert "docker build --target frontend -f docker/Dockerfile ." in ci, (
        "CI no longer builds the Dockerfile's frontend stage"
    )
    # Non-editable, from the Dockerfile's file set, imported from `/` — each of
    # the three properties `pip install -e .` at the repo root cannot test.
    assert 'pip install "/tmp/imgsrc[web]"' in ci
    assert "cp -r seestack webapp /tmp/imgsrc/" in ci
    assert "working-directory: /" in ci


def test_the_ci_smoke_copies_every_directory_the_dockerfile_does(dockerfile: str) -> None:
    """The two file sets must not drift apart.

    If a future change adds ``COPY data/ ./data/`` to the runtime stage, the
    smoke must learn about it or it stops testing the thing it claims to.
    """
    # Runtime-stage COPYs of our own tree: skip --from= (the built SPA) and the
    # install-astap.sh helper, which is deleted again in the same layer.
    copied = {
        part.rstrip("/")
        for line in re.findall(r"^COPY (?!--from=)(.+)$", dockerfile, re.M)
        for part in line.split()[:-1]
        if "/" in part or part.endswith((".toml", ".md"))
    }
    dirs = {
        name
        for name in copied
        if (_ROOT / name).is_dir() and not name.startswith(("docker", "frontend"))
    }
    assert dirs == {"seestack", "webapp"}, (
        f"the Dockerfile's runtime stage now copies {sorted(dirs)}; teach the "
        "`image` CI job's copy step about the change too"
    )


# --------------------------------------------------------------------------
# Bundled data reaches the wheel
# --------------------------------------------------------------------------


def test_every_bundled_data_file_is_declared_as_package_data(pyproject: dict) -> None:
    """``seestack/data/`` holds files the *running app* reads, not fixtures.

    A non-editable install (which is what the image does) copies only what
    ``[tool.setuptools.package-data]`` names, so a new extension dropped in here
    is silently absent from the owner's install while every test and CI job —
    all of which run from the tree — keep passing. That is exactly the gap the
    glossary sat in for its whole life, from the other direction: it was in
    ``docs/``, which the Dockerfile does not copy at all.
    """
    patterns = pyproject["tool"]["setuptools"]["package-data"]["seestack"]
    declared = {p.rsplit(".", 1)[-1] for p in patterns if p.startswith("data/")}
    present = {p.suffix.lstrip(".") for p in (_ROOT / "seestack" / "data").iterdir()
               if p.is_file()}
    missing = present - declared
    assert not missing, (
        f"seestack/data holds {sorted(missing)} files that package-data does not "
        f"declare ({patterns}) — they will not reach a non-editable install"
    )


def test_the_glossary_the_app_serves_ships_inside_the_package() -> None:
    """The named instance of the rule above, pinned where a reader will find it.

    ``GET /api/glossary`` reads ``seestack/data/glossary.md``. Moving it back to
    ``docs/`` — or forgetting the ``data/*.md`` pattern — makes the page empty in
    the image and full in every checkout.
    """
    from seestack.glossary import glossary_path

    assert glossary_path().is_file()
    assert glossary_path().is_relative_to(_ROOT / "seestack")
