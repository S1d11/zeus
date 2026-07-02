"""Tests for agent.usage_bar — monthly usage limit bar."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.usage_bar import (
    ProviderUsage,
    _bar,
    _color_for_pct,
    _fmt_tokens,
    _fmt_cost,
    _normalize_provider,
    _month_start,
    collect_usage,
    render_usage_bar,
    show_usage_bar,
)


class TestBar:
    def test_zero_pct(self):
        assert _bar(0) == "[░░░░░░░░░░░░░░░░░░░░]"

    def test_full_pct(self):
        assert _bar(100) == "[████████████████████]"

    def test_half_pct(self):
        assert _bar(50) == "[██████████░░░░░░░░░░]"

    def test_clamps_above_100(self):
        assert _bar(150) == "[████████████████████]"

    def test_clamps_below_0(self):
        assert _bar(-10) == "[░░░░░░░░░░░░░░░░░░░░]"

    def test_custom_width(self):
        assert _bar(50, width=10) == "[█████░░░░░]"


class TestColorForPct:
    def test_green_under_75(self):
        assert _color_for_pct(50) == "\033[32m"

    def test_yellow_75_to_90(self):
        assert _color_for_pct(80) == "\033[33m"

    def test_red_above_90(self):
        assert _color_for_pct(95) == "\033[31m"

    def test_boundary_75(self):
        assert _color_for_pct(75) == "\033[33m"

    def test_boundary_90(self):
        assert _color_for_pct(90) == "\033[31m"


class TestFmtTokens:
    def test_millions(self):
        assert _fmt_tokens(1_500_000) == "1.5M"

    def test_thousands(self):
        assert _fmt_tokens(15_000) == "15.0K"

    def test_small(self):
        assert _fmt_tokens(500) == "500"

    def test_zero(self):
        assert _fmt_tokens(0) == "0"


class TestFmtCost:
    def test_dollar_amount(self):
        assert _fmt_cost(5.50) == "$5.50"

    def test_small_amount(self):
        assert _fmt_cost(0.001) == "$0.0010"

    def test_zero(self):
        assert _fmt_cost(0) == "$0"


class TestNormalizeProvider:
    def test_openai_codex(self):
        assert _normalize_provider("openai-codex") == "openai"

    def test_copilot_aliases(self):
        assert _normalize_provider("copilot") == "copilot"
        assert _normalize_provider("copilot-acp") == "copilot"
        assert _normalize_provider("github") == "copilot"
        assert _normalize_provider("github-copilot") == "copilot"

    def test_anthropic_alias(self):
        assert _normalize_provider("claude") == "anthropic"
        assert _normalize_provider("anthropic") == "anthropic"

    def test_unknown(self):
        assert _normalize_provider("custom-provider") == "custom-provider"

    def test_none(self):
        assert _normalize_provider(None) == "unknown"

    def test_empty(self):
        assert _normalize_provider("") == "unknown"


class TestMonthStart:
    def test_returns_first_of_month(self):
        start = _month_start()
        assert start.day == 1
        assert start.hour == 0
        assert start.minute == 0
        assert start.second == 0

    def test_is_utc(self):
        start = _month_start()
        assert start.tzinfo == timezone.utc


class TestProviderUsage:
    def test_has_limit_false_by_default(self):
        pu = ProviderUsage(provider="test")
        assert not pu.has_limit

    def test_has_limit_true_when_set(self):
        pu = ProviderUsage(provider="test", limit_value=100.0)
        assert pu.has_limit

    def test_has_limit_false_when_zero(self):
        pu = ProviderUsage(provider="test", limit_value=0)
        assert not pu.has_limit


class TestRenderUsageBar:
    def test_empty_providers(self):
        result = render_usage_bar([])
        assert "No usage data" in result

    def test_with_limit(self):
        pu = ProviderUsage(
            provider="openai",
            total_tokens=500_000,
            sessions=10,
            estimated_cost_usd=5.0,
            limit_type="cost_usd",
            limit_value=20.0,
            used_value=5.0,
            used_percent=25.0,
            limit_source="config",
        )
        result = render_usage_bar([pu], use_color=False)
        assert "Openai" in result
        assert "25.0%" in result
        assert "$5.00" in result
        assert "$20.00" in result
        assert "(configured)" in result

    def test_without_limit(self):
        pu = ProviderUsage(
            provider="copilot",
            total_tokens=100_000,
            sessions=5,
            estimated_cost_usd=1.0,
            api_calls=50,
        )
        result = render_usage_bar([pu], use_color=False)
        assert "Copilot" in result
        assert "no limit configured" in result
        assert "100.0K tokens" in result

    def test_color_output(self):
        pu = ProviderUsage(
            provider="test",
            total_tokens=100,
            limit_type="cost_usd",
            limit_value=100.0,
            used_value=95.0,
            used_percent=95.0,
            limit_source="config",
        )
        result = render_usage_bar([pu], use_color=True)
        assert "\033[31m" in result  # red for 95%

    def test_no_color_output(self):
        pu = ProviderUsage(
            provider="test",
            total_tokens=100,
            limit_type="cost_usd",
            limit_value=100.0,
            used_value=95.0,
            used_percent=95.0,
            limit_source="config",
        )
        result = render_usage_bar([pu], use_color=False)
        assert "\033[31m" not in result

    def test_requests_limit(self):
        pu = ProviderUsage(
            provider="copilot",
            total_tokens=100_000,
            sessions=5,
            api_calls=300,
            limit_type="requests",
            limit_value=500,
            used_value=300,
            used_percent=60.0,
            limit_source="config",
        )
        result = render_usage_bar([pu], use_color=False)
        assert "300 / 500" in result
        assert "reqs" in result

    def test_summary_line(self):
        pu1 = ProviderUsage(provider="a", total_tokens=100, sessions=1, estimated_cost_usd=1.0)
        pu2 = ProviderUsage(provider="b", total_tokens=200, sessions=2, estimated_cost_usd=2.0)
        result = render_usage_bar([pu1, pu2], use_color=False)
        assert "Total:" in result
        assert "300 tokens" in result

    def test_config_hint_for_unconfigured(self):
        pu = ProviderUsage(provider="copilot", total_tokens=100)
        result = render_usage_bar([pu], use_color=False)
        assert "usage_limits:" in result
        assert "copilot:" in result

    def test_reset_at_displayed(self):
        pu = ProviderUsage(
            provider="test",
            total_tokens=100,
            limit_type="cost_usd",
            limit_value=100.0,
            used_value=50.0,
            used_percent=50.0,
            limit_source="api",
            reset_at=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
        )
        result = render_usage_bar([pu], use_color=False)
        assert "resets:" in result


class TestCollectUsage:
    def _make_fake_db(self, rows):
        """Create a fake SessionDB-like object with a mock connection."""
        db = MagicMock()
        db._conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = rows
        db._conn.execute.return_value = cursor
        db.close = MagicMock()
        return db

    def test_empty_db(self):
        db = self._make_fake_db([])
        providers = collect_usage(db)
        assert providers == []

    def test_single_provider(self):
        rows = [
            {
                "billing_provider": "nous",
                "model": "hermes-nova",
                "sessions": 5,
                "input_tokens": 1000,
                "output_tokens": 500,
                "cache_read_tokens": 200,
                "cache_write_tokens": 100,
                "reasoning_tokens": 50,
                "total_tokens": 1850,
                "estimated_cost_usd": 0.05,
                "actual_cost_usd": 0.04,
                "api_calls": 20,
            }
        ]
        db = self._make_fake_db(rows)
        providers = collect_usage(db)
        assert len(providers) == 1
        assert providers[0].provider == "nous"
        assert providers[0].sessions == 5
        assert providers[0].total_tokens == 1850
        assert providers[0].api_calls == 20

    def test_multiple_providers_aggregated(self):
        rows = [
            {
                "billing_provider": "openai",
                "model": "gpt-4",
                "sessions": 3,
                "input_tokens": 500,
                "output_tokens": 200,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 700,
                "estimated_cost_usd": 0.02,
                "actual_cost_usd": 0,
                "api_calls": 10,
            },
            {
                "billing_provider": "anthropic",
                "model": "claude-3",
                "sessions": 2,
                "input_tokens": 800,
                "output_tokens": 400,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 1200,
                "estimated_cost_usd": 0.03,
                "actual_cost_usd": 0,
                "api_calls": 8,
            },
        ]
        db = self._make_fake_db(rows)
        providers = collect_usage(db)
        assert len(providers) == 2
        # Sorted by total_tokens descending
        assert providers[0].provider == "anthropic"
        assert providers[0].total_tokens == 1200
        assert providers[1].provider == "openai"
        assert providers[1].total_tokens == 700

    def test_provider_normalization_in_aggregation(self):
        """Two rows with 'copilot' and 'github-copilot' should aggregate into one 'copilot'."""
        rows = [
            {
                "billing_provider": "copilot",
                "model": "gpt-4",
                "sessions": 1,
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 150,
                "estimated_cost_usd": 0,
                "actual_cost_usd": 0,
                "api_calls": 5,
            },
            {
                "billing_provider": "github-copilot",
                "model": "gpt-4",
                "sessions": 2,
                "input_tokens": 200,
                "output_tokens": 100,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 300,
                "estimated_cost_usd": 0,
                "actual_cost_usd": 0,
                "api_calls": 10,
            },
        ]
        db = self._make_fake_db(rows)
        providers = collect_usage(db)
        assert len(providers) == 1
        assert providers[0].provider == "copilot"
        assert providers[0].sessions == 3
        assert providers[0].total_tokens == 450

    def test_config_limits_applied(self):
        rows = [
            {
                "billing_provider": "copilot",
                "model": "gpt-4",
                "sessions": 5,
                "input_tokens": 1000,
                "output_tokens": 500,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 1500,
                "estimated_cost_usd": 2.0,
                "actual_cost_usd": 0,
                "api_calls": 100,
            }
        ]
        db = self._make_fake_db(rows)
        with patch("agent.usage_bar._load_config_limits") as mock_limits:
            mock_limits.return_value = {
                "copilot": {"monthly_requests": 500}
            }
            providers = collect_usage(db)
        assert len(providers) == 1
        assert providers[0].limit_type == "requests"
        assert providers[0].limit_value == 500
        assert providers[0].used_value == 100
        assert providers[0].used_percent == 20.0
        assert providers[0].limit_source == "config"

    def test_config_cost_limit(self):
        rows = [
            {
                "billing_provider": "openai",
                "model": "gpt-4",
                "sessions": 10,
                "input_tokens": 50000,
                "output_tokens": 10000,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "reasoning_tokens": 0,
                "total_tokens": 60000,
                "estimated_cost_usd": 5.0,
                "actual_cost_usd": 0,
                "api_calls": 50,
            }
        ]
        db = self._make_fake_db(rows)
        with patch("agent.usage_bar._load_config_limits") as mock_limits:
            mock_limits.return_value = {
                "openai": {"monthly_cost_usd": 20.0}
            }
            providers = collect_usage(db)
        assert providers[0].limit_type == "cost_usd"
        assert providers[0].limit_value == 20.0
        assert providers[0].used_value == 5.0
        assert providers[0].used_percent == 25.0


class TestShowUsageBar:
    def test_returns_string(self):
        with patch("agent.usage_bar.collect_usage") as mock_collect:
            mock_collect.return_value = []
            result = show_usage_bar()
            assert isinstance(result, str)
            assert "No usage data" in result
