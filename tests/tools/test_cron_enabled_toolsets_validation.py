"""Regression tests for enabled_toolsets validation on the cron runtime (bead .25).

The hard gate reads ``enabled_toolsets`` on agent-tier cron jobs. Previously
``cronjob(action='create'|'update')`` stored whatever toolset string was passed
verbatim — a typo or prompt-injected toolset name silently produced a job that
runs with none of the requested tools, and made the gate's read untrustworthy.

Fix: validate ``enabled_toolsets`` against the canonical registry
(``toolsets.validate_toolset``) at create AND update, and fail closed (reject)
on agent-tier jobs. On ``no_agent`` script-tier jobs the field is meaningless,
so it is accepted-and-ignored.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


@pytest.fixture
def hermes_env(tmp_path, monkeypatch):
    """Isolate HERMES_HOME so no real ~/.hermes/cron/jobs.json is touched."""
    home = tmp_path / ".hermes"
    home.mkdir()
    (home / "scripts").mkdir()
    (home / "cron").mkdir()

    monkeypatch.setenv("HERMES_HOME", str(home))

    # Reload modules that cache get_hermes_home() at import time.
    import importlib
    import hermes_constants
    importlib.reload(hermes_constants)
    import cron.jobs
    importlib.reload(cron.jobs)

    return home


def _raw_cronjob(**kwargs) -> dict:
    from tools.cronjob_tools import cronjob

    return json.loads(cronjob(**kwargs))


class TestCreateValidatesEnabledToolsets:
    def test_create_rejects_unknown_toolset_and_does_not_persist(self, hermes_env):
        result = _raw_cronjob(
            action="create",
            prompt="check disk usage",
            schedule="every 5m",
            deliver="local",
            enabled_toolsets=["not_a_real_toolset_xyz"],
        )
        assert result.get("success") is False
        assert "not_a_real_toolset_xyz" in result.get("error", "")

        # Fail closed and did not persist.
        from cron.jobs import load_jobs

        assert load_jobs() == []

    def test_create_rejects_single_unknown_name_among_valid_ones(self, hermes_env):
        result = _raw_cronjob(
            action="create",
            prompt="check disk usage",
            schedule="every 5m",
            deliver="local",
            enabled_toolsets=["web", "bogus_toolset"],
        )
        assert result.get("success") is False
        assert "bogus_toolset" in result.get("error", "")

    def test_create_accepts_valid_toolset_and_persists(self, hermes_env):
        result = _raw_cronjob(
            action="create",
            prompt="check disk usage",
            schedule="every 5m",
            deliver="local",
            enabled_toolsets=["web", "terminal"],
        )
        assert result.get("success") is True, result.get("error")
        job_id = result["job_id"]

        from cron.jobs import get_job

        job = get_job(job_id)
        assert job is not None
        assert job.get("enabled_toolsets") == ["web", "terminal"]

    def test_create_no_agent_script_tier_accepts_unknown_toolset(self, hermes_env):
        """Script-tier jobs have no agent to scope → toolsets are ignored, not
        rejected (the field is meaningless there)."""
        (hermes_env / "scripts" / "warn.sh").write_text("echo hi\n")
        result = _raw_cronjob(
            action="create",
            schedule="every 5m",
            script="warn.sh",
            no_agent=True,
            deliver="local",
            enabled_toolsets=["not_a_real_toolset_xyz"],
        )
        assert result.get("success") is True, result.get("error")


class TestUpdateValidatesEnabledToolsets:
    def _create_agent_job(self):
        result = _raw_cronjob(
            action="create",
            prompt="check disk usage",
            schedule="every 5m",
            deliver="local",
        )
        assert result.get("success") is True
        return result["job_id"]

    def test_update_rejects_unknown_toolset(self, hermes_env):
        job_id = self._create_agent_job()
        result = _raw_cronjob(
            action="update",
            job_id=job_id,
            enabled_toolsets=["not_a_real_toolset_xyz"],
        )
        assert result.get("success") is False
        assert "not_a_real_toolset_xyz" in result.get("error", "")

        # The bad value was not applied to the stored job.
        from cron.jobs import get_job

        job = get_job(job_id)
        assert job is not None
        assert job.get("enabled_toolsets") is None

    def test_update_accepts_valid_toolset(self, hermes_env):
        job_id = self._create_agent_job()
        result = _raw_cronjob(
            action="update",
            job_id=job_id,
            enabled_toolsets=["memory"],
        )
        assert result.get("success") is True, result.get("error")

        from cron.jobs import get_job

        job = get_job(job_id)
        assert job is not None
        assert job.get("enabled_toolsets") == ["memory"]

    def test_update_toggling_no_agent_on_ignores_unknown_toolset(self, hermes_env):
        """Flipping an agent job to no_agent in the same update makes toolsets
        meaningless → accepted-and-ignored, not rejected."""
        (hermes_env / "scripts" / "warn.sh").write_text("echo hi\n")
        job_id = self._create_agent_job()
        result = _raw_cronjob(
            action="update",
            job_id=job_id,
            script="warn.sh",
            no_agent=True,
            enabled_toolsets=["not_a_real_toolset_xyz"],
        )
        assert result.get("success") is True, result.get("error")

        from cron.jobs import get_job

        job = get_job(job_id)
        assert job is not None
        assert job.get("no_agent") is True
