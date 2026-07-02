"""``hermes usage`` subcommand parser.

Shows a visual usage limit bar — monthly token/cost usage by provider,
compared against known limits (from provider APIs or config.yaml).
"""

from __future__ import annotations

from typing import Callable


def build_usage_parser(subparsers, *, cmd_usage: Callable) -> None:
    """Attach the ``usage`` subcommand to ``subparsers``."""
    usage_parser = subparsers.add_parser(
        "usage",
        help="Show usage limit bar — monthly usage by provider vs. limits",
        description=(
            "Show a visual progress bar of monthly token/cost usage by "
            "provider, compared against known limits. Limits are fetched "
            "from provider APIs (where available) or from config.yaml "
            "'usage_limits' settings. For providers without configured "
            "limits, shows usage stats without a bar."
        ),
    )
    usage_parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color codes in the output",
    )
    usage_parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of a formatted bar (for scripting/TUI)",
    )
    usage_parser.set_defaults(func=cmd_usage)
