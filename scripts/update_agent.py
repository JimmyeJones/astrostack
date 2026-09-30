#!/usr/bin/env python3
"""The NAS-side half of Settings → "App updates".

    sudo python3 scripts/update_agent.py --install   # once, from your astrostack clone
    (then a TrueNAS cron job runs the installed copy every minute, as root)

**Why there is a helper at all.** The app cannot update itself: it runs inside the
container an update has to rebuild. So the page only *asks* — it writes
``$ASTRO_DATA/state/updater/request.json`` — and this script, run on the host by
cron, reads the ask, checks it against the three things it may mean, and runs the
same ``scripts/deploy.sh`` / ``scripts/rollback.sh`` the owner would run by hand
(stop the app, back up, build, wait for healthy). It reports back in
``state/updater/status.json``, which the page reads. Stdlib only: TrueNAS ships
``python3`` and nothing here may need an install.

**Trust.** Everything under ASTRO_DATA is writable by the container, and this runs
as root, so:

* the request is **data, never code** — it chooses one of ``check`` / ``update`` /
  ``rollback`` (plus a yes/no for restoring data), is validated field by field, and
  nothing in it ever reaches a command line. An update always installs
  ``origin/stable``; the page cannot name a commit;
* this script and the clone it drives must live **outside** ASTRO_DATA —
  ``--install`` refuses otherwise — because a file the container could edit, run as
  root by cron, would hand the web page root on the NAS.

**Network.** It runs ``git fetch`` only when the page asked (Check for updates,
Update). There is no scheduled outbound check — the owner's answer, 2026-09-30,
keeping to the app-stays-local rule (AGENTS.md §1).

**Liveness.** Every run stamps ``agent_seen_at``, and a long deploy keeps stamping
it from a thread, so the page can tell "the helper is set up and alive" from
"nobody installed it" (no status file) and "cron stopped" (a stale stamp).
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

AGENT_VERSION = 1
ACTIONS = ("check", "update", "rollback")
STABLE_REF = "origin/stable"
REQUEST_MAX_AGE_S = 3600      # an ask older than this is dropped, not acted on
HEARTBEAT_S = 20
LOG_TAIL_LINES = 40
_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_VERSION_RE = re.compile(r'__version__\s*=\s*"([^"]+)"')
_SCHEMA_RE = re.compile(r"^SCHEMA_VERSION = (\d+)", re.M)
_LIB_SCHEMA_RE = re.compile(r"^LIBRARY_SCHEMA_VERSION = (\d+)", re.M)
# cron's PATH is minimal; deploy.sh needs docker and (for its snapshot) zfs.
_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


class Refused(Exception):
    """A request this helper will not act on; the message is shown to the owner."""


# ---- the request: data from the web page, validated field by field ----------

def validate_request(raw: bytes, now: float) -> dict:
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Refused("The update request was not readable.") from None
    if not isinstance(obj, dict):
        raise Refused("The update request was not readable.")
    action, rid, at = obj.get("action"), obj.get("id"), obj.get("requested_at")
    if action not in ACTIONS:
        raise Refused("The update request asked for something this helper does not do.")
    if not isinstance(rid, str) or not _ID_RE.match(rid):
        raise Refused("The update request had no valid id.")
    if isinstance(at, bool) or not isinstance(at, (int, float)):
        raise Refused("The update request had no time.")
    if at < now - REQUEST_MAX_AGE_S:
        raise Refused("That request was over an hour old, so it was not acted on. Press the button again.")
    if at > now + 300:
        raise Refused("The update request was dated in the future; the NAS clock and the app disagree.")
    restore = obj.get("restore_data", False)
    if not isinstance(restore, bool) or (restore and action != "rollback"):
        raise Refused("The update request was not readable.")
    if restore and obj.get("confirm") != "RESTORE":
        raise Refused("Restoring the backup needs RESTORE typed to confirm.")
    return {"id": rid, "action": action, "restore_data": restore}


# ---- small helpers -------------------------------------------------------------

def read_astro_data(clone: Path) -> Path:
    """ASTRO_DATA from the clone's .env, read the way deploy.sh reads it."""
    env = clone / ".env"
    value = ""
    for line in env.read_text().splitlines():
        if line.startswith("ASTRO_DATA="):
            value = line[len("ASTRO_DATA="):].strip().strip("'\"")
    if not value:
        raise SystemExit(f"no ASTRO_DATA in {env}")
    return Path(value)


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _atomic_write(path: Path, text: str, like: Path | None = None) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(tmp, 0o644)
        if like is not None and os.geteuid() == 0:
            st = like.stat()
            os.chown(tmp, st.st_uid, st.st_gid)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _ver_tuple(v: str | None) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in (v or "").split("."))
    except ValueError:
        return ()


# ---- the agent -------------------------------------------------------------------

class Agent:
    def __init__(self, clone: Path, home: Path, deploy_state: Path | None = None) -> None:
        self.clone = clone
        self.home = home
        self.data = read_astro_data(clone)
        self.queue = self.data / "state" / "updater"
        st = clone.stat()
        self.owner = pwd.getpwuid(st.st_uid).pw_name
        # Where deploy.sh keeps last-good / last-backup (its STATE_DIR).
        self.deploy_state = deploy_state or Path(pwd.getpwnam(self.owner).pw_dir) / ".astrostack-deploy"
        self._status_lock = threading.Lock()

    # git runs as the clone's owner, as deploy.sh does (root on a user's clone
    # trips git's "dubious ownership" check).
    def git(self, *args: str, check: bool = True) -> str:
        cmd = ["git", "-C", str(self.clone), *args]
        if os.geteuid() == 0 and self.owner != "root":
            cmd = ["sudo", "-u", self.owner, *cmd]
        r = subprocess.run(cmd, capture_output=True, text=True, env=self._env())
        if check and r.returncode != 0:
            raise Refused(f"git {args[0]} failed: {(r.stderr or r.stdout).strip()[:300]}")
        return r.stdout.strip() if r.returncode == 0 else ""

    def _env(self) -> dict:
        env = {k: v for k, v in os.environ.items() if k != "SUDO_USER"}
        env["PATH"] = _PATH + ":" + env.get("PATH", "")
        return env

    def version_at(self, ref: str) -> str | None:
        m = _VERSION_RE.search(self.git("show", f"{ref}:webapp/__init__.py", check=False))
        return m.group(1) if m else None

    def schema_at(self, ref: str) -> tuple[int, int] | None:
        p = _SCHEMA_RE.search(self.git("show", f"{ref}:seestack/io/project.py", check=False))
        lib = _LIB_SCHEMA_RE.search(self.git("show", f"{ref}:seestack/io/library.py", check=False))
        return (int(p.group(1)), int(lib.group(1))) if p and lib else None

    # ---- status.json ----
    def _status_path(self) -> Path:
        return self.queue / "status.json"

    def read_status(self) -> dict:
        try:
            st = json.loads(self._status_path().read_text())
            return st if isinstance(st, dict) else {}
        except (OSError, ValueError):
            return {}

    def update_status(self, **fields) -> dict:
        with self._status_lock:
            st = self.read_status()
            st.update(fields)
            st["schema"] = 1
            st["agent_version"] = AGENT_VERSION
            st["agent_seen_at"] = time.time()
            _atomic_write(self._status_path(), json.dumps(st, indent=1), like=self.queue)
            return st

    def ensure_queue(self) -> None:
        state = self.data / "state"
        if not state.is_dir():
            raise SystemExit(f"{state} does not exist — is ASTRO_DATA right, and has the app run once?")
        if not self.queue.is_dir():
            self.queue.mkdir()
            if os.geteuid() == 0:
                st = state.stat()
                os.chown(self.queue, st.st_uid, st.st_gid)

    # ---- facts the page shows ----
    def installed(self) -> dict:
        return {"version": self.version_at("HEAD"), "commit": self.git("rev-parse", "--short", "HEAD", check=False)}

    def rollback_info(self) -> dict | None:
        try:
            sha = (self.deploy_state / "last-good").read_text().split()[0]
        except (OSError, IndexError):
            return None
        backup = ""
        with contextlib.suppress(OSError):
            backup = (self.deploy_state / "last-backup").read_text().strip()
        then, now = self.schema_at(sha), self.schema_at("HEAD")
        needs = bool(then and now and (then[0] < now[0] or then[1] < now[1]))
        return {
            "to_version": self.version_at(sha),
            "needs_restore_data": needs,
            "backup": "snapshot" if "@" in backup else ("archive" if backup.endswith(".tar.gz") else None),
        }

    def available(self) -> dict | None:
        commit = self.git("rev-parse", "-q", "--verify", f"{STABLE_REF}^{{commit}}", check=False)
        if not commit:
            return None
        return {
            "version": self.version_at(commit),
            "commit": commit[:12],
            "committed_at": int(self.git("log", "-1", "--format=%ct", commit, check=False) or 0),
        }

    # ---- actions ----
    def do_check(self) -> tuple[bool, str, list[str]]:
        self.git("fetch", "--quiet", "--tags", "origin")
        avail = self.available()
        self.update_status(available=avail, checked_at=time.time())
        if avail is None:
            return True, "Checked — there is no tested (stable) version to install yet.", []
        return True, f"Checked — the newest tested version is v{avail['version']}.", []

    def do_update(self) -> tuple[bool, str, list[str]]:
        self.do_check()
        avail = self.available()
        if avail is None:
            raise Refused("There is no tested (stable) version to install yet.")
        ok, tail = self.run_logged([str(self.clone / "scripts" / "deploy.sh"), "-y", STABLE_REF])
        if ok:
            self.refresh_self()
            return True, f"Updated to v{avail['version']}.", tail
        return False, "The update did not finish. The app may still be on the old version — see the log below, or roll back.", tail

    def do_rollback(self, restore: bool) -> tuple[bool, str, list[str]]:
        info = self.rollback_info()
        if info is None:
            raise Refused("There is no earlier version recorded to go back to.")
        script = self.clone / "scripts" / "rollback.sh"
        if not script.exists():
            raise Refused("This version predates one-click rollback; run sudo scripts/rollback.sh over SSH.")
        cmd = [str(script), "--yes"] + (["--restore-data"] if restore else [])
        ok, tail = self.run_logged(cmd)
        if ok:
            return True, f"Rolled back to v{info['to_version']}.", tail
        return False, "The rollback did not finish — see the log below.", tail

    def run_logged(self, cmd: list[str]) -> tuple[bool, list[str]]:
        """Run *cmd* in the clone, logging to state/updater/last.log, stamping the
        heartbeat while it runs (a deploy takes minutes)."""
        log_path = self.queue / "last.log"
        done = threading.Event()

        def beat() -> None:
            while not done.wait(HEARTBEAT_S):
                with contextlib.suppress(OSError):
                    self.update_status()

        t = threading.Thread(target=beat, daemon=True)
        t.start()
        try:
            with open(log_path, "w") as log:
                r = subprocess.run(cmd, cwd=self.clone, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, env=self._env())
        finally:
            done.set()
            t.join()
        lines = log_path.read_text(errors="replace").splitlines()
        return r.returncode == 0, lines[-LOG_TAIL_LINES:]

    def refresh_self(self) -> None:
        """After an update, carry the helper forward with the code it now drives."""
        installed = self.home / "update_agent.py"
        fresh = self.clone / "scripts" / "update_agent.py"
        if not (self.home / "clone-path").exists() or not fresh.exists():
            return
        if installed.exists() and installed.read_bytes() == fresh.read_bytes():
            return
        _atomic_write(installed, fresh.read_text())
        os.chmod(installed, 0o755)

    # ---- one cron tick ----
    def tick(self) -> None:
        self.ensure_queue()
        st = self.read_status()
        self.update_status(state="idle", job=None, installed=self.installed(),
                           rollback=self.rollback_info(),
                           **({} if "available" in st else {"available": None}))
        req, claimed = self.queue / "request.json", self.queue / "request.claimed.json"
        try:
            os.replace(req, claimed)
        except FileNotFoundError:
            return
        raw = claimed.read_bytes()
        claimed.unlink(missing_ok=True)
        now = time.time()
        rid = None
        try:
            with contextlib.suppress(ValueError, AttributeError):
                rid = json.loads(raw).get("id")
            r = validate_request(raw, now)
            rid = r["id"]
            busy = {"check": "checking", "update": "updating", "rollback": "rolling_back"}[r["action"]]
            self.update_status(state=busy, job={"id": rid, "action": r["action"], "started_at": now})
            if r["action"] == "check":
                ok, msg, tail = self.do_check()
            elif r["action"] == "update":
                ok, msg, tail = self.do_update()
            else:
                ok, msg, tail = self.do_rollback(r["restore_data"])
            action = r["action"]
        except Refused as e:
            ok, msg, tail, action = False, str(e), [], None
        self.update_status(
            state="idle", job=None, installed=self.installed(), rollback=self.rollback_info(),
            last_result={"id": rid if isinstance(rid, str) and _ID_RE.match(rid) else None,
                         "action": action, "ok": ok, "message": msg,
                         "finished_at": time.time(), "log_tail": tail},
        )


# ---- install ----------------------------------------------------------------------

def check_install_paths(clone: Path, home: Path, data: Path) -> None:
    for label, p in (("your astrostack folder", clone), ("the helper's folder", home)):
        if _is_within(p, data):
            raise SystemExit(
                f"{label} ({p}) is inside the app's data folder ({data}). The app can write "
                "there, and this helper runs as root — so it must live somewhere the app "
                "cannot touch. Move the clone outside the data folder and run this again.")


def install(clone: Path) -> None:
    if os.geteuid() != 0:
        raise SystemExit("run with sudo: sudo python3 scripts/update_agent.py --install")
    data = read_astro_data(clone)
    if not data.is_dir():
        raise SystemExit(f"ASTRO_DATA ({data}) is not a folder.")
    if not (clone / "scripts" / "deploy.sh").exists():
        raise SystemExit("this clone has no scripts/deploy.sh — update it once by hand first.")
    owner = pwd.getpwuid(clone.stat().st_uid)
    home = Path(owner.pw_dir) / ".astrostack-deploy"
    check_install_paths(clone, home, data)
    home.mkdir(parents=True, exist_ok=True)
    os.chown(home, owner.pw_uid, owner.pw_gid)
    dest = home / "update_agent.py"
    shutil.copyfile(Path(__file__).resolve(), dest)
    os.chmod(dest, 0o755)
    (home / "clone-path").write_text(str(clone.resolve()) + "\n")
    agent = Agent(clone.resolve(), home)
    agent.ensure_queue()
    agent.update_status(state="idle", job=None, installed=agent.installed(),
                        rollback=agent.rollback_info(), available=None)
    print(f"""
Installed the update helper at {dest}.

Last step — tell TrueNAS to run it every minute:
  System → Advanced Settings → Cron Jobs → Add
    Description : AstroStack updates
    Command     : python3 {dest}
    Run As User : root
    Schedule    : Custom → minutes */1 (every minute), every hour, every day
    Tick "Hide Standard Output" and "Hide Standard Error".
  Save.

Within a minute, Settings → Maintenance → App updates in the app will say it is ready.
(Any other Linux host: add  * * * * * python3 {dest}  to root's crontab.)
""")


def main(argv: list[str]) -> int:
    here = Path(__file__).resolve().parent
    pinned = here / "clone-path"
    clone = Path(pinned.read_text().strip()) if pinned.exists() else here.parent
    if "--install" in argv:
        install(clone.resolve())
        return 0
    with open(here / ".update-agent.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0       # the previous minute's run is still deploying
        Agent(clone, here).tick()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
