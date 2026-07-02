"""Monthly usage limit bar — aggregates SessionDB usage by provider and shows
a visual progress bar against known limits.

Limits come from three sources, in priority order:
1. **Real-time provider API** — via ``fetch_account_usage()`` (OpenAI Codex,
   Anthropic, OpenRouter, Nous). These show actual account-level quotas.
2. **User-configured limits** — in ``config.yaml`` under ``usage_limits``:
   .. code-block:: yaml
       usage_limits:
         copilot:
           monthly_requests: 500
         openai:
           monthly_cost_usd: 20.0
3. **SessionDB aggregation** — when no API or configured limit is available,
   we still show monthly usage stats without a bar.

For GitHub Copilot (which doesn't expose usage via the ACP CLI), users can
configure their known monthly premium request limit in ``config.yaml`` and
Zeus will track usage against it from SessionDB data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _bar(pct: float, width: int = 20) -> str:
    """Unicode progress bar: [████████░░░░░░░░░░░░] 40%."""
    filled = int(pct / 100.0 * width)
    filled = max(0, min(width, filled))
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}]"


def _color_for_pct(pct: float) -> str:
    """ANSI color code based on usage percentage."""
    if pct >= 90:
        return "\033[31m"  # red
    if pct >= 75:
        return "\033[33m"  # yellow
    return "\033[32m"  # green


def _reset() -> str:
    return "\033[0m"


@dataclass
class ProviderUsage:
    """Usage data for a single provider in the current billing period."""

    provider: str
    model: Optional[str] = None
    sessions: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    api_calls: int = 0

    # Limit info (from API or config)
    limit_type: Optional[str] = None  # "cost_usd", "requests", "tokens", "credits"
    limit_value: Optional[float] = None
    used_value: Optional[float] = None
    used_percent: Optional[float] = None
    reset_at: Optional[datetime] = None
    limit_source: Optional[str] = None  # "api", "config", "sessiondb"

    @property
    def has_limit(self) -> bool:
        return self.limit_value is not None and self.limit_value > 0


def _month_start() -> datetime:
    """Start of the current calendar month in UTC."""
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _query_sessiondb_usage(db, since: datetime) -> list[dict[str, Any]]:
    """Query SessionDB for usage aggregated by billing_provider + model."""
    conn = db._conn
    try:
        cursor = conn.execute(
            """
            SELECT
                billing_provider,
                model,
                COUNT(*) as sessions,
                SUM(input_tokens) as input_tokens,
                SUM(output_tokens) as output_tokens,
                SUM(cache_read_tokens) as cache_read_tokens,
                SUM(cache_write_tokens) as cache_write_tokens,
                SUM(reasoning_tokens) as reasoning_tokens,
                SUM(input_tokens + output_tokens + cache_read_tokens
                    + cache_write_tokens + reasoning_tokens) as total_tokens,
                SUM(estimated_cost_usd) as estimated_cost_usd,
                SUM(actual_cost_usd) as actual_cost_usd,
                SUM(api_call_count) as api_calls
            FROM sessions
            WHERE started_at >= ? AND archived = 0
            GROUP BY billing_provider, model
            ORDER BY total_tokens DESC
            """,
            (since.timestamp(),),
        )
        return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.debug("usage_bar ▸ SessionDB query failed: %s", e)
        return []


def _normalize_provider(raw: Optional[str]) -> str:
    """Normalize billing_provider to a canonical name."""
    if not raw:
        return "unknown"
    p = raw.strip().lower()
    # Common aliases
    aliases = {
        "openai-codex": "openai",
        "copilot": "copilot",
        "copilot-acp": "copilot",
        "github": "copilot",
        "github-copilot": "copilot",
        "nous": "nous",
        "anthropic": "anthropic",
        "claude": "anthropic",
        "openrouter": "openrouter",
        "gemini": "gemini",
        "google": "gemini",
        "deepseek": "deepseek",
        "ollama": "ollama",
        "local": "local",
    }
    return aliases.get(p, p)


def _load_config_limits() -> dict[str, dict[str, Any]]:
    """Load user-configured usage limits from config.yaml.

    Expected format:
    .. code-block:: yaml
        usage_limits:
          copilot:
            monthly_requests: 500
          openai:
            monthly_cost_usd: 20.0
          anthropic:
            monthly_cost_usd: 50.0
    """
    try:
        from hermes_cli.config import get_config

        config = get_config()
        raw = config.get("usage_limits", {})
        if not isinstance(raw, dict):
            return {}
        return {k.lower(): v for k, v in raw.items() if isinstance(v, dict)}
    except Exception:
        return {}


def _apply_api_limits(
    providers: dict[str, ProviderUsage],
    active_provider: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> None:
    """Fetch real-time account limits from provider APIs and apply to providers."""
    try:
        from agent.account_usage import fetch_account_usage

        # Try the active provider first
        providers_to_check = []
        if active_provider:
            providers_to_check.append(active_provider)
        # Also check other providers that have usage data
        for p in providers:
            if p not in providers_to_check:
                providers_to_check.append(p)

        for provider_name in providers_to_check:
            normalized = _normalize_provider(provider_name)
            try:
                snapshot = fetch_account_usage(
                    normalized,
                    base_url=base_url if normalized == active_provider else None,
                    api_key=api_key if normalized == active_provider else None,
                )
            except Exception:
                snapshot = None

            if snapshot and snapshot.available and snapshot.windows:
                # Use the first window that has a used_percent
                for window in snapshot.windows:
                    if window.used_percent is not None:
                        pu = providers.get(normalized)
                        if pu:
                            pu.used_percent = float(window.used_percent)
                            pu.limit_source = "api"
                            pu.reset_at = window.reset_at
                            if window.detail:
                                pu.limit_type = "api_window"
                        break
    except Exception:
        logger.debug("usage_bar ▸ API limits fetch failed", exc_info=True)


def _apply_config_limits(
    providers: dict[str, ProviderUsage],
    config_limits: dict[str, dict[str, Any]],
) -> None:
    """Apply user-configured limits from config.yaml to providers."""
    for provider_name, pu in providers.items():
        limits = config_limits.get(provider_name)
        if not limits:
            continue

        # Only apply config limits if no API limit was set
        if pu.limit_source == "api":
            continue

        if "monthly_requests" in limits:
            pu.limit_type = "requests"
            pu.limit_value = float(limits["monthly_requests"])
            pu.used_value = float(pu.api_calls)
            pu.limit_source = "config"
        elif "monthly_cost_usd" in limits:
            pu.limit_type = "cost_usd"
            pu.limit_value = float(limits["monthly_cost_usd"])
            pu.used_value = pu.estimated_cost_usd
            pu.limit_source = "config"
        elif "monthly_tokens" in limits:
            pu.limit_type = "tokens"
            pu.limit_value = float(limits["monthly_tokens"])
            pu.used_value = float(pu.total_tokens)
            pu.limit_source = "config"

        if pu.has_limit and pu.used_value is not None:
            pu.used_percent = min(100.0, (pu.used_value / pu.limit_value) * 100.0)


def collect_usage(
    db=None,
    *,
    active_provider: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> list[ProviderUsage]:
    """Collect usage data for the current billing period.

    Args:
        db: SessionDB instance. If None, a new one is opened and closed.
        active_provider: The currently configured provider (for API limit fetch).
        base_url: Base URL for the active provider's API.
        api_key: API key for the active provider's API.

    Returns:
        List of ProviderUsage sorted by total tokens descending.
    """
    own_db = False
    if db is None:
        try:
            from hermes_state import SessionDB

            db = SessionDB()
            own_db = True
        except Exception:
            return []
    try:
        since = _month_start()
        rows = _query_sessiondb_usage(db, since)

        # Aggregate by normalized provider
        providers: dict[str, ProviderUsage] = {}
        for row in rows:
            raw_provider = row.get("billing_provider")
            normalized = _normalize_provider(raw_provider)
            model = row.get("model") or "unknown"

            pu = providers.get(normalized)
            if pu is None:
                pu = ProviderUsage(provider=normalized)
                providers[normalized] = pu

            pu.sessions += row.get("sessions") or 0
            pu.input_tokens += row.get("input_tokens") or 0
            pu.output_tokens += row.get("output_tokens") or 0
            pu.cache_read_tokens += row.get("cache_read_tokens") or 0
            pu.cache_write_tokens += row.get("cache_write_tokens") or 0
            pu.reasoning_tokens += row.get("reasoning_tokens") or 0
            pu.total_tokens += row.get("total_tokens") or 0
            pu.estimated_cost_usd += row.get("estimated_cost_usd") or 0.0
            pu.actual_cost_usd += row.get("actual_cost_usd") or 0.0
            pu.api_calls += row.get("api_calls") or 0

        # Apply limits
        config_limits = _load_config_limits()
        _apply_config_limits(providers, config_limits)
        _apply_api_limits(providers, active_provider, base_url, api_key)

        return sorted(providers.values(), key=lambda p: p.total_tokens, reverse=True)
    finally:
        if own_db:
            db.close()


def _fmt_tokens(n: int) -> str:
    """Format token count with K/M suffixes."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_cost(usd: float) -> str:
    if usd >= 1.0:
        return f"${usd:.2f}"
    if usd > 0:
        return f"${usd:.4f}"
    return "$0"


def render_usage_bar(providers: list[ProviderUsage], *, use_color: bool = True) -> str:
    """Render the usage limit bar display.

    Args:
        providers: List of ProviderUsage from collect_usage().
        use_color: Whether to include ANSI color codes.

    Returns:
        Multi-line string with usage bars.
    """
    if not providers:
        return "No usage data found for the current month."

    lines: list[str] = []
    now = datetime.now(timezone.utc)
    month_name = now.strftime("%B %Y")
    lines.append(f"📊 Usage Limit Bar — {month_name}")
    lines.append("")

    for pu in providers:
        provider_label = pu.provider.title()

        if pu.has_limit and pu.used_percent is not None:
            pct = pu.used_percent
            bar = _bar(pct)
            color = _color_for_pct(pct) if use_color else ""
            reset = _reset() if use_color else ""

            # Format the used/limit values
            if pu.limit_type == "cost_usd":
                used_str = _fmt_cost(pu.used_value or 0)
                limit_str = _fmt_cost(pu.limit_value or 0)
                unit = ""
            elif pu.limit_type == "requests":
                used_str = f"{int(pu.used_value or 0)}"
                limit_str = f"{int(pu.limit_value or 0)}"
                unit = " reqs"
            elif pu.limit_type == "tokens":
                used_str = _fmt_tokens(int(pu.used_value or 0))
                limit_str = _fmt_tokens(int(pu.limit_value or 0))
                unit = " tok"
            else:
                # API-sourced limit (generic)
                used_str = f"{pct:.0f}%"
                limit_str = "100%"
                unit = ""

            source_tag = ""
            if pu.limit_source == "config":
                source_tag = " (configured)"
            elif pu.limit_source == "api":
                source_tag = " (live API)"

            lines.append(
                f"  {provider_label:<16} {color}{bar} {pct:5.1f}%{reset}  "
                f"{used_str} / {limit_str}{unit}{source_tag}"
            )

            if pu.reset_at:
                reset_str = pu.reset_at.astimezone().strftime("%Y-%m-%d %H:%M")
                lines.append(f"  {'':>16} resets: {reset_str}")
        else:
            # No limit configured — show usage stats only
            lines.append(f"  {provider_label:<16} (no limit configured)")
            lines.append(
                f"  {'':>16} {_fmt_tokens(pu.total_tokens)} tokens, "
                f"{pu.sessions} sessions, {_fmt_cost(pu.estimated_cost_usd)} est."
            )
            if pu.api_calls:
                lines.append(f"  {'':>16} {pu.api_calls} API calls")

        lines.append("")

    # Summary line
    total_tokens = sum(p.total_tokens for p in providers)
    total_cost = sum(p.estimated_cost_usd for p in providers)
    total_sessions = sum(p.sessions for p in providers)
    lines.append(
        f"  Total: {_fmt_tokens(total_tokens)} tokens, "
        f"{total_sessions} sessions, {_fmt_cost(total_cost)} estimated"
    )

    # Hint for configuring limits
    unconfigured = [p.provider for p in providers if not p.has_limit]
    if unconfigured:
        lines.append("")
        lines.append(
            "  💡 Configure limits in config.yaml under 'usage_limits:' to see bars:"
        )
        lines.append("  usage_limits:")
        for p in unconfigured[:3]:
            lines.append(f"    {p}:")
            lines.append(f"      monthly_cost_usd: 20.0  # or monthly_requests: 500")

    return "\n".join(lines)


def show_usage_bar(
    *,
    active_provider: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """Convenience: collect usage and render the bar in one call."""
    providers = collect_usage(
        active_provider=active_provider,
        base_url=base_url,
        api_key=api_key,
    )
    return render_usage_bar(providers)
