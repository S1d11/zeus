# plugins/markets/__init__.py — Markets data plugin registration.
#
# Provides yfinance-backed market data tools (quotes, history, news, overview)
# so the agent can answer stock/market questions in chat. No paper trading,
# no portfolio, no GUI — just data lookup.

from __future__ import annotations

import logging

from .config import is_markets_enabled
from .tools import get_tool_definitions

logger = logging.getLogger(__name__)


def register(ctx) -> None:
    """Register market data tools. Called once by the plugin loader."""
    if not is_markets_enabled():
        logger.info("markets plugin: disabled in config (markets.enabled = false)")
        return

    for name, schema, handler, emoji in get_tool_definitions():
        ctx.register_tool(
            name=name,
            toolset="markets",
            schema=schema,
            handler=handler,
            check_fn=_check_markets_available,
            emoji=emoji,
        )

    logger.info("markets plugin: registered %d data tools", len(get_tool_definitions()))


def _check_markets_available() -> bool:
    """Runtime check: only expose tools when the plugin is enabled."""
    return is_markets_enabled()
