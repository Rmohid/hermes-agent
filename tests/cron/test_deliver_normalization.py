"""Regression test: deliver normalization must not serialize a list to its
Python repr literal, nor leave a legacy string-encoded list undeliverable.

Two boundaries normalize ``deliver``:

  - ``tools.cronjob_tools._normalize_deliver_param`` (the cronjob tool's API
    boundary, called with the raw user value on create/update).
  - ``cron.scheduler._normalize_deliver_value`` (the scheduler's boundary,
    called on every fire with the STORED value).

The contract is that ``deliver`` is a string ("telegram", "telegram:-100:17",
or a comma-separated combination).  Some callers — MCP clients, scripts, or a
legacy/corrupt store — supply a *list* (``["telegram"]``) or a *string that is
literally the repr of a list* (``"['telegram']"``, e.g. produced by an older
``str([...])`` serialization).  Both MUST be flattened to the canonical
comma-separated string; otherwise ``deliver.split(",")`` yields
``["'telegram'"]`` which is not a known platform and the job silently never
delivers.
"""
import pytest

from cron.scheduler import _normalize_deliver_value

from tools.cronjob_tools import _normalize_deliver_param


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Real lists — should flatten to comma-separated string.
        (["telegram"], "telegram"),
        (["telegram", "sms"], "telegram,sms"),
        (["telegram:-100:17"], "telegram:-100:17"),
        # The scheduler also reads lists directly from a stored job.
        # Strings that are ALREADY canonical pass through unchanged.
        ("telegram", "telegram"),
        ("telegram,sms", "telegram,sms"),
        ("origin,all", "origin,all"),
        ("telegram:-100:17", "telegram:-100:17"),
        ("local", "local"),
        # Falsy -> "local" at the scheduler boundary (no delivery).
        (None, "local"),
        ("", "local"),
        ([], "local"),
        # The regression: a string that is the repr of a list must be
        # detected and flattened, not treated as one opaque unknown platform.
        ("['telegram']", "telegram"),
        ("['telegram', 'sms']", "telegram,sms"),
    ],
)
def test_normalize_deliver_value_never_serializes_list_literal(raw, expected):
    assert _normalize_deliver_value(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        (["telegram"], "telegram"),
        (["telegram", "sms"], "telegram,sms"),
        ("telegram", "telegram"),
        ("telegram,sms", "telegram,sms"),
        ("['telegram']", "telegram"),
        (None, None),
        ("", None),
    ],
)
def test_normalize_deliver_param_never_serializes_list_literal(raw, expected):
    assert _normalize_deliver_param(raw) == expected
