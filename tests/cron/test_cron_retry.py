"""Tests for cron retry-with-backoff and failure-notification enhancements.

Covers:
  - create_job stores a retry config with the right defaults
  - mark_job_run schedules a retry (exponential backoff) on failure when
    attempts remain, WITHOUT incrementing repeat.completed
  - mark_job_run resets the retry counter on success
  - mark_job_run falls through to normal failure handling when retries are
    exhausted (incrementing repeat.completed, computing next_run_at)
  - _summarize_cron_failure_for_delivery appends retry context
"""
import pytest
from datetime import datetime, timedelta, timezone

from cron.jobs import create_job, mark_job_run, load_jobs, save_jobs
import cron.jobs as jobs_mod
import cron.scheduler as sched


@pytest.fixture()
def tmp_cron_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("cron.jobs.CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr("cron.jobs.JOBS_FILE", tmp_path / "cron" / "jobs.json")
    monkeypatch.setattr("cron.jobs.OUTPUT_DIR", tmp_path / "cron" / "output")
    (tmp_path / "cron").mkdir(parents=True, exist_ok=True)
    (tmp_path / "cron" / "output").mkdir(parents=True, exist_ok=True)
    return tmp_path


# =========================================================================
# create_job retry config
# =========================================================================

class TestCreateJobRetryConfig:
    def test_default_no_retry(self, tmp_cron_dir):
        job = create_job(prompt="test", schedule="every 1h")
        assert job["retry"]["max_attempts"] == 1
        assert job["retry"]["attempt"] == 0
        assert job["retry"]["backoff_base_seconds"] == 60
        assert job["retry"]["next_retry_at"] is None

    def test_custom_retry_config(self, tmp_cron_dir):
        job = create_job(
            prompt="test", schedule="every 1h",
            retry_max_attempts=3, retry_backoff_seconds=120,
        )
        assert job["retry"]["max_attempts"] == 3
        assert job["retry"]["backoff_base_seconds"] == 120

    def test_zero_max_attempts_means_no_retry(self, tmp_cron_dir):
        job = create_job(prompt="test", schedule="every 1h", retry_max_attempts=0)
        assert job["retry"]["max_attempts"] == 1

    def test_negative_backoff_clamped_to_1(self, tmp_cron_dir):
        job = create_job(prompt="test", schedule="every 1h", retry_backoff_seconds=-5)
        assert job["retry"]["backoff_base_seconds"] == 1


# =========================================================================
# mark_job_run retry scheduling
# =========================================================================

class TestMarkJobRunRetry:
    def test_failure_schedules_retry_when_attempts_remain(self, tmp_cron_dir, monkeypatch):
        """A failing job with max_attempts=3 should schedule a retry instead
        of advancing to the next scheduled run."""
        now = datetime(2026, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        job = create_job(
            prompt="test", schedule="every 1h",
            retry_max_attempts=3, retry_backoff_seconds=60,
        )
        save_jobs([job])

        mark_job_run(job["id"], success=False, error="provider timeout")

        updated = load_jobs()[0]
        assert updated["last_status"] == "error"
        assert updated["last_error"] == "provider timeout"
        assert updated["retry"]["attempt"] == 1
        assert updated["retry"]["next_retry_at"] is not None
        # next_run_at should point at the retry time, not the next scheduled run
        assert updated["next_run_at"] == updated["retry"]["next_retry_at"]
        # repeat.completed should NOT be incremented (retry != new occurrence)
        assert updated["repeat"]["completed"] == 0

    def test_retry_backoff_is_exponential(self, tmp_cron_dir, monkeypatch):
        """Second retry should have 2x the backoff of the first."""
        now = datetime(2026, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        job = create_job(
            prompt="test", schedule="every 1h",
            retry_max_attempts=3, retry_backoff_seconds=60,
        )
        save_jobs([job])

        # First failure → retry in 60s (60 * 2^0)
        mark_job_run(job["id"], success=False, error="err")
        updated = load_jobs()[0]
        first_retry = datetime.fromisoformat(updated["retry"]["next_retry_at"])
        expected_first = now + timedelta(seconds=60)
        assert abs((first_retry - expected_first).total_seconds()) < 1

        # Second failure → retry in 120s (60 * 2^1) from the new now
        now2 = first_retry
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now2)
        mark_job_run(job["id"], success=False, error="err")
        updated = load_jobs()[0]
        second_retry = datetime.fromisoformat(updated["retry"]["next_retry_at"])
        expected_second = now2 + timedelta(seconds=120)
        assert abs((second_retry - expected_second).total_seconds()) < 1

    def test_success_resets_retry_counter(self, tmp_cron_dir, monkeypatch):
        """A successful run after a failure should reset attempt to 0."""
        now = datetime(2026, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        job = create_job(
            prompt="test", schedule="every 1h",
            retry_max_attempts=3, retry_backoff_seconds=60,
        )
        # Simulate a prior failure: set attempt=1
        job["retry"]["attempt"] = 1
        save_jobs([job])

        mark_job_run(job["id"], success=True)

        updated = load_jobs()[0]
        assert updated["retry"]["attempt"] == 0
        assert updated["retry"]["next_retry_at"] is None
        assert updated["last_status"] == "ok"

    def test_exhausted_retries_fall_through_to_normal_failure(self, tmp_cron_dir, monkeypatch):
        """When all retry attempts are used, mark_job_run should fall through
        to normal failure handling: increment repeat.completed, compute
        next_run_at from the schedule, reset attempt counter."""
        now = datetime(2026, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        job = create_job(
            prompt="test", schedule="every 1h",
            retry_max_attempts=2, retry_backoff_seconds=60,
        )
        # Simulate first retry already consumed
        job["retry"]["attempt"] = 1
        save_jobs([job])

        mark_job_run(job["id"], success=False, error="final error")

        updated = load_jobs()[0]
        # Retry counter reset
        assert updated["retry"]["attempt"] == 0
        assert updated["retry"]["next_retry_at"] is None
        # Normal failure handling kicked in
        assert updated["repeat"]["completed"] == 1
        assert updated["last_status"] == "error"
        assert updated["last_error"] == "final error"
        # next_run_at should be the next scheduled run, not a retry time
        assert updated["next_run_at"] != updated["retry"]["next_retry_at"]

    def test_no_retry_config_behaves_like_before(self, tmp_cron_dir, monkeypatch):
        """A job with max_attempts=1 (default, no retry) should go straight to
        normal failure handling on failure — no retry scheduling."""
        now = datetime(2026, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
        monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)

        job = create_job(prompt="test", schedule="every 1h")
        save_jobs([job])

        mark_job_run(job["id"], success=False, error="err")

        updated = load_jobs()[0]
        assert updated["retry"]["attempt"] == 0
        assert updated["retry"]["next_retry_at"] is None
        assert updated["repeat"]["completed"] == 1
        assert updated["last_status"] == "error"


# =========================================================================
# Failure delivery summary with retry context
# =========================================================================

class TestFailureDeliveryRetryContext:
    def test_no_retry_no_suffix(self):
        """A job with max_attempts=1 should not get a retry suffix."""
        job = {"name": "test", "retry": {"max_attempts": 1, "attempt": 0}}
        msg = sched._summarize_cron_failure_for_delivery(job, "timeout")
        assert "attempt" not in msg
        assert "retrying" not in msg

    def test_retry_pending_suffix(self):
        """A failing job with retries remaining should mention the retry."""
        job = {"name": "test", "retry": {"max_attempts": 3, "attempt": 0}}
        msg = sched._summarize_cron_failure_for_delivery(job, "timeout")
        assert "attempt 1/3" in msg
        assert "retrying" in msg

    def test_retry_exhausted_suffix(self):
        """A job that used all attempts should say all attempts failed."""
        job = {"name": "test", "retry": {"max_attempts": 3, "attempt": 2}}
        msg = sched._summarize_cron_failure_for_delivery(job, "timeout")
        assert "all 3 attempts failed" in msg

    def test_legacy_job_without_retry_field(self):
        """A job dict without a retry field should not crash."""
        job = {"name": "test"}
        msg = sched._summarize_cron_failure_for_delivery(job, "timeout")
        assert "Cron 'test' failed" in msg
        assert "attempt" not in msg
