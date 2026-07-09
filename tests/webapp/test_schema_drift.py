"""Guard: the form schema must stay in lockstep with the StackOptions dataclass."""

from __future__ import annotations

import dataclasses

from seestack.stack.stacker import StackOptions
from webapp.schemas import (
    NON_FORM_KEYS,
    coerce_stack_options,
    describable_keys,
    stack_option_fields,
)


def test_every_stackoption_is_described():
    dataclass_keys = {f.name for f in dataclasses.fields(StackOptions)}
    # Server-resolved fields (calibration paths) intentionally have no form
    # control and are excluded from the lockstep guard.
    described = describable_keys() | NON_FORM_KEYS
    missing = dataclass_keys - described
    assert not missing, f"StackOptions fields not in the form schema: {missing}"


def test_no_phantom_described_keys():
    dataclass_keys = {f.name for f in dataclasses.fields(StackOptions)}
    extra = describable_keys() - dataclass_keys
    assert not extra, f"Form schema describes unknown StackOptions fields: {extra}"


def test_schema_defaults_match_dataclass():
    defaults = {f.name: getattr(StackOptions(), f.name) for f in dataclasses.fields(StackOptions)}
    for fld in stack_option_fields():
        assert fld.default == defaults[fld.key], f"default mismatch for {fld.key}"


def test_coerce_ignores_unknown_keys():
    opts = coerce_stack_options({"sigma_kappa": 2.5, "bogus": 99, "output_name": "x"})
    assert opts.sigma_kappa == 2.5
    assert opts.output_name == "x"


def test_every_form_field_has_plain_language_help():
    # Friendliness bar (AGENTS.md §1 priority 3): every knob a beginner can see in
    # the Stack form must carry a plain-language "what/why" tooltip — no bare jargon
    # label with an empty hint. Guards against a new field shipping without help.
    without_help = [f.key for f in stack_option_fields() if not (f.help or "").strip()]
    assert not without_help, f"Stack-form fields missing help text: {without_help}"
