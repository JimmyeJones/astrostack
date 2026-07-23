"""Pure, testable helpers for the storage "how much longer can I keep imaging?"
estimate.

A Seestar drips fixed-size subs onto the box night after night, so a real
library grows steadily and *will* eventually fill the disk — at which point
ingest silently fails and a night's frames are lost with no warning. The
storage page already shows raw GB free; this turns that into the one thing a
beginner actually asks — *"am I about to run out?"* — by projecting the recent
capture cadence forward.

The estimate is deliberately simple and honest:

* **frames/night** — the median frame count over the most recent capture nights
  (median, so a half-finished current night or one cloudy dud doesn't skew it).
* **bytes/frame** — the whole library's on-disk size divided by its total frame
  count. This amortises *everything* a sub costs on disk (the stage-1 raw copy,
  the stage-2 aligned cache, thumbnails and the eventual stacked output), so it
  is a truthful "cost per sub captured" rather than just the raw file size.
* **bytes/night** = frames/night × bytes/frame — the growth rate the caller
  divides ``free`` by to get "nights left".

It returns ``None`` (rather than a wild guess) when there isn't enough history
to be meaningful, so the caller can just show the free figure instead.
"""

from __future__ import annotations

from statistics import median


def estimate_nightly_bytes(
    night_counts: dict[str, int],
    total_library_bytes: int,
    total_frames: int,
    recent_nights: int = 7,
) -> float | None:
    """Estimate the library's recent growth rate in **bytes per night**.

    ``night_counts`` maps a capture date (``YYYY-MM-DD``) to how many frames
    were captured that night (summed across every target — see
    :meth:`seestack.io.project.Project.frame_night_counts`). Returns ``None``
    when the estimate would be meaningless:

    * no frames or no bytes on disk yet, or
    * fewer than two distinct capture nights (a single night gives no rate).

    Otherwise it takes the **median** frames/night over the most recent
    ``recent_nights`` capture nights and multiplies by the amortised
    bytes-per-frame (``total_library_bytes / total_frames``).
    """
    if total_frames <= 0 or total_library_bytes <= 0:
        return None
    # Capture nights (those with ≥1 frame), most recent first — ISO dates sort
    # lexically, so a plain reverse sort is newest-first.
    dated = sorted((d for d, n in night_counts.items() if d and n > 0), reverse=True)
    if len(dated) < 2:
        return None
    recent_dates = set(dated[:recent_nights])
    recent_counts = [n for d, n in night_counts.items() if d in recent_dates and n > 0]
    frames_per_night = float(median(recent_counts))
    if frames_per_night <= 0:
        return None
    bytes_per_frame = total_library_bytes / total_frames
    return frames_per_night * bytes_per_frame
