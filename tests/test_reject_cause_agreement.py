"""Two surfaces explain the *same* rejection, and they must name the same cause.

A beginner who loses half a night sees that night described twice, minutes
apart and often on one screen:

* the run's **"why were some frames left out?"** panel, whose buckets come from
  ``webapp.rejection_summary`` — "Cloud, haze or moonlight" vs "Soft or
  elongated stars", each with its own advice ("a clearer, darker night will keep
  more of them" vs "it's worth checking focus (and dew on the lens)");
* the **Nights** card and the session recap, whose buckets come from
  ``seestack.session_recap.bucket_reject_reason`` — ``cloudy`` vs ``soft``,
  where the ``cloudy`` tally is also what decides the night's one-word **hazy**
  verdict.

Both start from the *same* ``reject_reason`` string. Until v0.428.0 they kept
two private lists of which metric means what, and the lists disagreed about
``star_count``: the panel called it cloud (correctly — auto-grade's own reason
text is "far fewer stars than typical — likely cloud") while the recap called it
soft. A solid-cloud night therefore came back as "your stars were soft" next to
a one-click "Set aside", and could never reach the hazy verdict.

The fix was to make :func:`seestack.qc.grading.metric_cause` the one place that
answers it — grading is the module that both writes the reason and explains it
in words. This file is the enforcement: it drives **both** mappings from
``grading``'s own metric list, so a metric added there with no cause, or a
bucket table that drifts back to a private copy, fails here rather than in front
of the owner.
"""

from __future__ import annotations

import pytest

from seestack.qc.grading import METRIC_LABELS, metric_cause
from seestack.session_recap import bucket_reject_reason
from webapp.rejection_summary import _bucket_for

# Every graded metric, in both the spellings a ``reject_reason`` carries: the
# attr auto-grade writes (``auto:grade:sky_adu_median``) and the short label a
# ``qc:``/``bulk:`` reason uses (``bulk:sky``).
SHORT_FORMS = {
    "fwhm_px": "fwhm",
    "eccentricity_median": "eccentricity",
    "sky_adu_median": "sky",
    "star_count": "star_count",
    "transparency_score": "transparency",
}

# The two vocabularies. The bucket *names* are each module's own — only the
# cause underneath them has to agree.
RECAP_BUCKET = {"cloud": "cloudy", "seeing": "soft"}
SUMMARY_BUCKET = {"cloud": "clouds", "seeing": "soft"}


@pytest.mark.parametrize("metric", sorted(METRIC_LABELS))
def test_every_graded_metric_names_a_physical_cause(metric):
    """A metric with no cause would fall through to "other"/"soft" silently."""
    assert metric_cause(metric) in ("cloud", "seeing"), (
        f"{metric} has no physical cause — add it to CLOUD_METRIC_NAMES or "
        f"SEEING_METRIC_NAMES in seestack/qc/grading.py"
    )
    assert metric in SHORT_FORMS, (
        f"{metric} is graded but this test doesn't know its short label form; "
        f"add it to SHORT_FORMS so both spellings stay covered"
    )


@pytest.mark.parametrize("metric", sorted(METRIC_LABELS))
@pytest.mark.parametrize("namespace", ["auto:grade:", "bulk:", "qc:"])
def test_both_surfaces_agree_on_the_cause_of_one_rejection(metric, namespace):
    cause = metric_cause(metric)
    for name in (metric, SHORT_FORMS[metric]):
        reason = f"{namespace}{name}"
        assert bucket_reject_reason(reason) == RECAP_BUCKET[cause], reason
        assert _bucket_for(reason) == SUMMARY_BUCKET[cause], reason


def test_star_count_is_cloud_on_both_surfaces():
    """The instance that was wrong, pinned by name so the regression is legible."""
    assert bucket_reject_reason("auto:grade:star_count") == "cloudy"
    assert _bucket_for("auto:grade:star_count") == "clouds"


def test_a_metric_grading_does_not_know_is_not_guessed_at():
    """``metric_cause`` says ``None`` rather than defaulting to a cause, so a
    future metric can't be quietly filed under the wrong physical explanation."""
    assert metric_cause("moon_separation_deg") is None
    assert _bucket_for("auto:grade:moon_separation_deg") == "other"
