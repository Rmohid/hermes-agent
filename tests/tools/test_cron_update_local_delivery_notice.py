"""Regression tests for update-path local-delivery notice (bead .26).

The create path calls ``_local_delivery_notice()`` so a user creating a
CLI/headless-session job is told its output is local-only and never delivered.
The update path never re-surfaced it: an agent that changes a job's ``deliver``
to ``origin`` from a headless session (or edits schedule/prompt on an existing
undeliverable job) got no warning, so the job silently stayed undeliverable.

Fix: call ``_local_delivery_notice()`` in the update branch too, keyed on the
effective deliver (this update's value merged over the stored job).
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def hermes_env(tmp_path, monkeypatch):
    """Isolate HERMES_HOME and clear the session env so cronjob() sees a
    headless/CLI context (no live origin, no HERMES_SESSION_PLATFORM)."""
    from tests.conftest import _HERMES_BEHAVIORAL_VARS

    home = tmp_path / ".hermes"
    home.mkdir()
    (home / "scripts").mkdir()
    (home / "cron").mkdir()

    monkeypatch.setenv("HERMES_HOME", str(home))
    for var in _HERMES_BEHAVIORAL_VARS:
        monkeypatch.delenv(var, raising=False)

    import importlib
    import hermes_constants
    importlib.reload(hermes_constants)
    import cron.jobs
    importlib.reload(cron.jobs)

    return home


def _raw_cronjob(**kwargs) -> dict:
    from tools.cronjob_tools import cronjob

    return json.loads(cronjob(**kwargs))


class TestUpdateSurfacesLocalDeliveryNotice:
    def test_update_setting_deliver_origin_surfaces_notice(self, hermes_env):
        # Create an isolated local job (headless env → no origin).
        created = _raw_cronjob(
            action="create",
            prompt="daily digest",
            schedule="every 2h",
            deliver="local",
        )
        assert created.get("success") is True, created.get("error")
        job_id = created["job_id"]

        # Flipping an undeliverable job to 'origin' in a headless session must warn.
        result = _raw_cronjob(action="update", job_id=job_id, deliver="origin")
        assert result.get("success") is True, result.get("error")
        assert "message" in result
        assert "local-only" in result["message"]
        assert "NOT be delivered" in result["message"]

    def test_update_editing_prompt_on_undeliverable_job_warns(self, hermes_env):
        """Editing any field on an existing undeliverable job re-warns."""
        created = _raw_cronjob(
            action="create",
            prompt="daily digest",
            schedule="every 2h",
            deliver="origin",
        )
        assert created.get("success") is True, created.get("error")
        job_id = created["job_id"]

        result = _raw_cronjob(action="update", job_id=job_id, prompt="new prompt")
        assert result.get("success") is True, result.get("error")
        assert "message" in result
        assert "local-only" in result["message"]

    def test_update_to_wired_channel_stays_silent(self, hermes_env):
        """A normal update pointing deliver at an explicit (wired) channel must
        not surface the local-only notice."""
        created = _raw_cronjob(
            action="create",
            prompt="daily digest",
            schedule="every 2h",
            deliver="local",
        )
        assert created.get("success") is True, created.get("error")
        job_id = created["job_id"]

        result = _raw_cronjob(
            action="update",
            job_id=job_id,
            deliver="telegram:-1001234567890:17585",
        )
        assert result.get("success") is True, result.get("error")
        assert "message" not in result

    def test_update_to_explicit_local_stays_silent(self, hermes_env):
        """Explicitly choosing 'local' is exactly what the user asked for — no
        surprise notice."""
        created = _raw_cronjob(
            action="create",
            prompt="daily digest",
            schedule="every 2h",
            deliver="local",
        )
        assert created.get("success") is True, created.get("error")
        job_id = created["job_id"]

        result = _raw_cronjob(action="update", job_id=job_id, deliver="local")
        assert result.get("success") is True, result.get("error")
        assert "message" not in result
