"""Tests for hermes_cli.monitor_cmd — real-time monitoring CLI."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hermes_cli.monitor_cmd import (
    _build_monitor_prompt,
    _derive_name,
    _find_job_by_name,
    _find_monitor_jobs,
    monitor_command,
)


class TestBuildMonitorPrompt:
    def test_basic_query(self):
        prompt = _build_monitor_prompt("Lakers score", None, "web")
        assert "Lakers score" in prompt
        assert "[SILENT]" in prompt
        assert "web_search" in prompt

    def test_with_condition(self):
        prompt = _build_monitor_prompt("AAPL stock", "above 200", "web")
        assert "AAPL stock" in prompt
        assert "above 200" in prompt

    def test_mcp_source(self):
        prompt = _build_monitor_prompt("BTC price", None, "mcp")
        assert "MCP tools" in prompt

    def test_web_source(self):
        prompt = _build_monitor_prompt("BTC price", None, "web")
        assert "web_search" in prompt


class TestDeriveName:
    def test_simple(self):
        assert _derive_name("Lakers score") == "lakers-score"

    def test_long_query(self):
        assert _derive_name("What is the weather in New York today") == "what-is-the-weather"

    def test_empty(self):
        assert _derive_name("") == "monitor"


class TestFindMonitorJobs:
    def test_filters_non_monitors(self):
        with patch("cron.jobs.list_jobs") as mock_list:
            mock_list.return_value = [
                {"id": "1", "name": "regular-job", "skills": ["other-skill"]},
                {"id": "2", "name": "monitor:stocks", "skills": ["live-monitor"]},
                {"id": "3", "name": "monitor:scores", "skill": "live-monitor"},
            ]
            result = _find_monitor_jobs()
            assert len(result) == 2
            assert result[0]["id"] == "2"
            assert result[1]["id"] == "3"

    def test_empty_list(self):
        with patch("cron.jobs.list_jobs") as mock_list:
            mock_list.return_value = []
            result = _find_monitor_jobs()
            assert result == []

    def test_handles_error(self):
        with patch("cron.jobs.list_jobs", side_effect=Exception("fail")):
            result = _find_monitor_jobs()
            assert result == []


class TestFindJobByName:
    def test_by_name_with_prefix(self):
        with patch("hermes_cli.monitor_cmd._find_monitor_jobs") as mock_find:
            mock_find.return_value = [
                {"id": "abc", "name": "monitor:stocks", "skills": ["live-monitor"]},
            ]
            result = _find_job_by_name("stocks")
            assert result is not None
            assert result["id"] == "abc"

    def test_by_full_name(self):
        with patch("hermes_cli.monitor_cmd._find_monitor_jobs") as mock_find:
            mock_find.return_value = [
                {"id": "abc", "name": "monitor:stocks", "skills": ["live-monitor"]},
            ]
            result = _find_job_by_name("monitor:stocks")
            assert result is not None

    def test_by_job_id(self):
        with patch("hermes_cli.monitor_cmd._find_monitor_jobs") as mock_find:
            mock_find.return_value = [
                {"id": "abc123", "name": "monitor:stocks", "skills": ["live-monitor"]},
            ]
            result = _find_job_by_name("abc123")
            assert result is not None

    def test_not_found(self):
        with patch("hermes_cli.monitor_cmd._find_monitor_jobs") as mock_find:
            mock_find.return_value = [
                {"id": "abc", "name": "monitor:stocks", "skills": ["live-monitor"]},
            ]
            result = _find_job_by_name("nonexistent")
            assert result is None

    def test_case_insensitive(self):
        with patch("hermes_cli.monitor_cmd._find_monitor_jobs") as mock_find:
            mock_find.return_value = [
                {"id": "abc", "name": "monitor:Stocks", "skills": ["live-monitor"]},
            ]
            result = _find_job_by_name("STOCKS")
            assert result is not None


class TestMonitorCommand:
    def test_no_action_prints_usage(self, capsys):
        args = MagicMock()
        args.monitor_action = None
        monitor_command(args)
        captured = capsys.readouterr()
        assert "usage:" in captured.out
        assert "add" in captured.out
        assert "list" in captured.out

    def test_unknown_action(self, capsys):
        args = MagicMock()
        args.monitor_action = "unknown"
        monitor_command(args)
        captured = capsys.readouterr()
        assert "Unknown monitor action" in captured.out
