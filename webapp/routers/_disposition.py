"""One ``Content-Disposition: attachment`` header for every hand-built download.

Several download routes name their file after ``run.output_basename``, and an
editor export stores whatever the user typed in *Output name* there ("Orion –
final", ``M42 ✨``, ``my "best" M42``) — only the files on disk are sanitised.
Formatting that straight into ``f'attachment; filename="{name}"'`` broke three
ways: a character outside Latin-1 made Starlette's header encoding raise (a 500
on the Full-res PNG, the wallpaper and the share JPEG), a Latin-1 accent went out
as a raw byte no client decodes reliably, and a ``"`` closed the quoted string
early. ``FileResponse(filename=...)`` already does this right; this is the same
RFC 6266 / RFC 5987 shape for the ``Response(...)`` routes: an ASCII
``filename="..."`` fallback plus ``filename*=UTF-8''...`` when the name is not
plain ASCII. The frontend's ``DownloadMenuItem`` prefers ``filename*``.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

#: Anything a quoted-string fallback must not carry: quotes, backslashes,
#: control characters and every non-ASCII character.
_UNSAFE_FALLBACK = re.compile(r'[^\x20-\x7e]|["\\]')


def attachment(filename: str) -> str:
    """The header value that offers ``filename`` as a download, on any name."""
    folded = unicodedata.normalize("NFKD", filename)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    fallback = _UNSAFE_FALLBACK.sub("_", folded).strip() or "download"
    if fallback == filename:
        return f'attachment; filename="{filename}"'
    return (f'attachment; filename="{fallback}"; '
            f"filename*=UTF-8''{quote(filename, safe='')}")
