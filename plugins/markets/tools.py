# tools.py — Model tool definitions for the markets data plugin.
#
# Plugin-scoped tools (footprint ladder rung 4). Only appear when the plugin
# is enabled. Provides yfinance-backed market data lookup so the agent can
# answer stock questions in chat.

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from . import data
from .config import is_markets_enabled, load_markets_config

logger = logging.getLogger(__name__)


def _check_enabled() -> bool:
    return is_markets_enabled()


# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-call format)
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "name": "markets_quote",
        "schema": {
            "type": "function",
            "description": "Get a real-time stock or crypto quote (price, change, volume, market cap).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker (e.g. AAPL) or crypto symbol (e.g. BTC)."},
                },
                "required": ["ticker"],
            },
        },
        "handler": "_handle_quote",
        "emoji": "📈",
    },
    {
        "name": "markets_history",
        "schema": {
            "type": "function",
            "description": "Get historical OHLCV price data for a ticker. Returns bars for charting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock or crypto ticker."},
                    "period": {"type": "string", "description": "Time period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 5y. Default: 1mo.", "default": "1mo"},
                    "interval": {"type": "string", "description": "Bar interval: 1m, 5m, 15m, 1h, 1d, 1wk, 1mo. Default: 1d.", "default": "1d"},
                },
                "required": ["ticker"],
            },
        },
        "handler": "_handle_history",
        "emoji": "📊",
    },
    {
        "name": "markets_news",
        "schema": {
            "type": "function",
            "description": "Get recent news headlines and summaries for a stock ticker.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock ticker (e.g. AAPL)."},
                    "limit": {"type": "integer", "description": "Max headlines to return. Default: 10.", "default": 10},
                },
                "required": ["ticker"],
            },
        },
        "handler": "_handle_news",
        "emoji": "📰",
    },
    {
        "name": "markets_overview",
        "schema": {
            "type": "function",
            "description": "Get a market overview snapshot (SPY, QQQ, DIA indices).",
            "parameters": {"type": "object", "properties": {}},
        },
        "handler": "_handle_overview",
        "emoji": "🌐",
    },
]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _handle_quote(args: Dict[str, Any]) -> str:
    cfg = load_markets_config()
    result = data.get_quote(args["ticker"], cfg.get("coverage", "us-only"))
    return json.dumps(result)


def _handle_history(args: Dict[str, Any]) -> str:
    cfg = load_markets_config()
    result = data.get_history(
        args["ticker"],
        args.get("period", "1mo"),
        args.get("interval", "1d"),
        cfg.get("coverage", "us-only"),
    )
    return json.dumps(result)


def _handle_news(args: Dict[str, Any]) -> str:
    cfg = load_markets_config()
    result = data.get_news(args["ticker"], args.get("limit", 10), cfg.get("coverage", "us-only"))
    return json.dumps(result)


def _handle_overview(args: Dict[str, Any]) -> str:
    cfg = load_markets_config()
    result = data.get_market_overview(cfg.get("coverage", "us-only"))
    return json.dumps(result)


def get_tool_definitions():
    """Return (name, schema, handler_name, emoji) tuples for registration."""
    return [(t["name"], t["schema"], t["handler"], t["emoji"]) for t in _TOOLS]
