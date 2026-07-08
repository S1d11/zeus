# config.py — Markets plugin configuration.
#
# Reads the ``markets`` section of config.yaml. Only data-related settings
# remain (no paper trading, no portfolio, no cron jobs).

from __future__ import annotations

from typing import Any, Dict

from hermes_cli.config import cfg_get, load_config_readonly

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS: Dict[str, Any] = {
    "enabled": False,                  # master toggle — must opt in
    "coverage": "us-only",             # us-only | us-crypto | us-international
    "data_backend": "yfinance",        # yfinance | alphavantage | finnhub
    "alphavantage_key": "",
    "finnhub_key": "",
}

# Coverage options mapped to data sources
COVERAGE_OPTIONS = {
    "us-only": "US equities (yfinance)",
    "us-crypto": "US equities + crypto (yfinance + CoinGecko)",
    "us-international": "US + international equities (yfinance)",
}


def load_markets_config() -> Dict[str, Any]:
    """Load the markets config section from config.yaml, merged with defaults."""
    cfg = load_config_readonly()
    raw = cfg_get(cfg, "markets", default={}) or {}
    result = dict(DEFAULTS)
    for key, default_val in DEFAULTS.items():
        if key in raw and raw[key] is not None:
            result[key] = raw[key]
    return result


def get_markets_setting(key: str, default: Any = None) -> Any:
    """Get a single markets setting."""
    config = load_markets_config()
    return config.get(key, default if default is not None else DEFAULTS.get(key))


def is_markets_enabled() -> bool:
    """Check if the markets plugin is enabled (master toggle)."""
    return bool(get_markets_setting("enabled", False))
