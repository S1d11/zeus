"""``hermes monitor`` subcommand parser.

Real-time monitoring built on top of the cron system. Creates cron jobs
with the ``live-monitor`` skill that fetch live data (scores, stocks,
news, weather) and deliver alerts via the user's preferred channel.
"""

from __future__ import annotations

from typing import Callable


def build_monitor_parser(subparsers, *, cmd_monitor: Callable) -> None:
    """Attach the ``monitor`` subcommand to ``subparsers``."""
    monitor_parser = subparsers.add_parser(
        "monitor",
        help="Real-time monitoring: watch live data and get alerts",
        description=(
            "Set up real-time monitors for live data — sports scores, stock "
            "prices, crypto, news, weather, and more. Monitors run as cron "
            "jobs with the 'live-monitor' skill and deliver alerts to your "
            "preferred channel (Telegram, Discord, CLI, etc.)."
        ),
    )
    monitor_sub = monitor_parser.add_subparsers(dest="monitor_action")

    # ── monitor add ────────────────────────────────────────────────────
    monitor_add = monitor_sub.add_parser(
        "add",
        help="Add a new monitor",
        description=(
            "Create a real-time monitor. Zeus will periodically check the "
            "query and alert you when conditions are met or values change."
        ),
    )
    monitor_add.add_argument(
        "query",
        help="What to monitor (e.g., 'Lakers score', 'AAPL stock price', 'BTC price')",
    )
    monitor_add.add_argument(
        "--name",
        help="Friendly name for this monitor (default: derived from query)",
    )
    monitor_add.add_argument(
        "--interval",
        default="*/5 * * * *",
        help=(
            "Check interval as cron expression (default: '*/5 * * * *' = every 5 min). "
            "Examples: '*/30 * * * *' (every 30 min), '0 9-16 * * 1-5' (market hours), "
            "'0 * * * *' (hourly)"
        ),
    )
    monitor_add.add_argument(
        "--condition",
        default=None,
        help=(
            "Alert condition (optional). Examples: 'above 200', 'below 50', "
            "'changed', 'contains breaking'. If omitted, alerts on any change."
        ),
    )
    monitor_add.add_argument(
        "--deliver",
        default="local",
        help=(
            "Delivery target: local (CLI), telegram, discord, signal, or all. "
            "Default: local. Use 'telegram' or 'discord' for push notifications."
        ),
    )
    monitor_add.add_argument(
        "--source",
        default="web",
        choices=["web", "mcp"],
        help=(
            "Data source: 'web' (web_search, default) or 'mcp' (use configured "
            "MCP servers for structured data)"
        ),
    )
    monitor_add.add_argument(
        "--repeat",
        type=int,
        default=None,
        help="Number of checks before auto-stopping (default: run forever)",
    )

    # ── monitor list ───────────────────────────────────────────────────
    monitor_list = monitor_sub.add_parser(
        "list",
        aliases=["ls"],
        help="List active monitors",
    )
    monitor_list.add_argument(
        "--all",
        action="store_true",
        help="Include paused/disabled monitors",
    )

    # ── monitor remove ─────────────────────────────────────────────────
    monitor_remove = monitor_sub.add_parser(
        "remove",
        aliases=["rm", "delete"],
        help="Remove a monitor",
    )
    monitor_remove.add_argument("name", help="Monitor name or job ID")

    # ── monitor pause ──────────────────────────────────────────────────
    monitor_pause = monitor_sub.add_parser("pause", help="Pause a monitor")
    monitor_pause.add_argument("name", help="Monitor name or job ID")

    # ── monitor resume ─────────────────────────────────────────────────
    monitor_resume = monitor_sub.add_parser("resume", help="Resume a paused monitor")
    monitor_resume.add_argument("name", help="Monitor name or job ID")

    # ── monitor run ────────────────────────────────────────────────────
    monitor_run = monitor_sub.add_parser(
        "run",
        help="Trigger a monitor immediately (test run)",
    )
    monitor_run.add_argument("name", help="Monitor name or job ID")

    monitor_parser.set_defaults(func=cmd_monitor)
