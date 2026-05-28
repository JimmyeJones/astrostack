"""
User-saved StackOptions templates.

Templates are tiny JSON files in the user's data directory (resolved via
``platformdirs.user_data_dir``). They behave just like the built-in presets
in the Stack dialog — pick a template, the dialog populates its fields.

This is the difference between "I have to remember every knob I tweaked for
NGC 7000 last week" and "I select 'NGC 7000 widefield' from the dropdown".
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, fields
from pathlib import Path

from platformdirs import user_data_dir

from seestack.stack.stacker import StackOptions

log = logging.getLogger(__name__)

APP_NAME = "Seestack"
APP_AUTHOR = "Seestack"
TEMPLATE_SUFFIX = ".seestackpreset.json"
_SAFE_NAME = re.compile(r"[^A-Za-z0-9 _.-]+")


def templates_dir() -> Path:
    """The folder where user templates live. Created on first use."""
    d = Path(user_data_dir(APP_NAME, APP_AUTHOR)) / "templates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_templates() -> list[str]:
    """Names of saved templates, sorted alphabetically (case-insensitive)."""
    names = []
    for p in templates_dir().glob(f"*{TEMPLATE_SUFFIX}"):
        names.append(p.name[: -len(TEMPLATE_SUFFIX)])
    names.sort(key=str.lower)
    return names


def save_template(name: str, options: StackOptions) -> Path:
    """Write a template file. Returns its on-disk path."""
    safe = _safe_filename(name)
    if not safe:
        raise ValueError("template name is empty after sanitisation")
    path = templates_dir() / f"{safe}{TEMPLATE_SUFFIX}"
    path.write_text(json.dumps(asdict(options), indent=2))
    log.info("Template saved: %s", path)
    return path


def load_template(name: str) -> StackOptions:
    """Load a template file by name (no extension). Raises FileNotFoundError."""
    safe = _safe_filename(name)
    path = templates_dir() / f"{safe}{TEMPLATE_SUFFIX}"
    raw = json.loads(path.read_text())
    keys = {f.name for f in fields(StackOptions)}
    filtered = {k: v for k, v in raw.items() if k in keys}
    return StackOptions(**filtered)


def delete_template(name: str) -> None:
    """Remove a template by name. Silently no-op if it doesn't exist."""
    safe = _safe_filename(name)
    path = templates_dir() / f"{safe}{TEMPLATE_SUFFIX}"
    if path.exists():
        path.unlink()
        log.info("Template deleted: %s", path)


def _safe_filename(name: str) -> str:
    """Strip filesystem-unsafe characters but keep the name readable."""
    return _SAFE_NAME.sub("_", name).strip()
