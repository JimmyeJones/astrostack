"""The probe's two overflow checks must not count screen-reader-only text.

``scripts/dogfood_probe.mjs``'s ``overflowingLeaves`` and ``clippedLabels``
flag a box whose content is wider than the box drawn for it. A
``VisuallyHidden`` span (the ``sr-only`` idiom: 1 px, ``clip: rect(0 0 0 0)``)
is exactly that shape **by design** — it is spoken, never painted. Since
v0.465.3 the header's "N running" badge carries its full phrase in one, so
every pass that swept `/` while a job ran — every ``--deep`` pass, whose
1,200-sub load is still QC-ing then — printed "1px box vs 87px content" twice:
two phantom findings on the one screen the owner opens first.

This runs the probe's *own* function source in a real Chromium against a page
holding one spoken-only span and one genuinely clipped label, and asserts the
first is skipped while the second is still caught — so the exclusion cannot
quietly widen into a probe that sees nothing. It needs Node and Playwright
(pre-installed in the agent container); where either is missing it skips.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_PROBE = Path(__file__).resolve().parents[1] / "scripts" / "dogfood_probe.mjs"

# Mantine's own VisuallyHidden rule (`.m_515a97f8` in @mantine/core/styles.css),
# copied verbatim so the fixture is the shape the app really renders.
_PAGE = """<!doctype html><html><head><style>
.sr { border: 0; clip: rect(0 0 0 0); height: 1px; width: 1px; margin: -1px;
      overflow: hidden; padding: 0; position: absolute; white-space: nowrap; }
.badge { display: inline-block; overflow: hidden; width: 40px; white-space: nowrap; }
</style></head><body>
<span class="mantine-Badge-root">3<span class="sr">3 jobs running right now</span></span>
<span class="mantine-Badge-root badge" id="real">a much longer label than fits</span>
<span class="sr" id="lone">a spoken-only leaf outside any badge, long text</span>
</body></html>"""


def _function_source(name: str) -> str:
    text = _PROBE.read_text(encoding="utf-8")
    m = re.search(rf"^function {name}\(\) \{{\n.*?^\}}\n", text, re.DOTALL | re.MULTILINE)
    assert m, f"{name} not found in {_PROBE.name}"
    return m.group(0)


def _call(name: str) -> str:
    """An expression that defines the probe function and returns its answer."""
    return f"(() => {{\n{_function_source(name)}\nreturn {name}();\n}})()"


def _have_playwright() -> bool:
    if not shutil.which("node"):
        return False
    r = subprocess.run(["node", "-e", "require('playwright')"],
                       capture_output=True, timeout=60)
    return r.returncode == 0


@pytest.mark.skipif(not _have_playwright(), reason="needs node + playwright")
def test_screen_reader_only_text_is_not_an_overflow_finding(tmp_path: Path) -> None:
    script = tmp_path / "run.js"
    script.write_text(
        "const { chromium } = require('playwright');\n"
        "(async () => {\n"
        "  const browser = await chromium.launch();\n"
        "  const page = await browser.newPage();\n"
        f"  await page.setContent({json.dumps(_PAGE)});\n"
        f"  const leaves = await page.evaluate({json.dumps(_call('overflowingLeaves'))});\n"
        f"  const labels = await page.evaluate({json.dumps(_call('clippedLabels'))});\n"
        "  console.log(JSON.stringify({ leaves, labels }));\n"
        "  await browser.close();\n"
        "})().catch((e) => { console.error(e); process.exit(1); });\n",
        encoding="utf-8",
    )
    r = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    leaf_texts = [o["text"] for o in out["leaves"]]
    label_texts = [o["text"] for o in out["labels"]]

    # Spoken-only text, inside a badge or on its own, is never a finding.
    assert not any("running right now" in t for t in leaf_texts + label_texts), out
    assert not any("spoken-only" in t for t in leaf_texts), out
    # ...and the checks still see what they exist to see.
    assert any("much longer label" in t for t in label_texts), out
    assert any("much longer label" in t for t in leaf_texts), out
