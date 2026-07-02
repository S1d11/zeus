"""Handler for ``hermes monitor`` — real-time monitoring via cron jobs.

Thin wrapper around the cron system that creates jobs with the
``live-monitor`` skill. Each monitor is a cron job that:
1. Fetches live data via web_search or MCP tools
2. Checks against configured conditions/thresholds
3. Delivers alerts via the user's preferred channel (or suppresses with [SILENT])
"""

from __future__ import annotations

import sys
from typing import Any, Optional


def _build_monitor_prompt(query: str, condition: Optional[str], source: str) -> str:
    """Build the prompt that the live-monitor skill will execute."""
    parts = [f"Monitor: {query}"]
    if condition:
        parts.append(f"Alert condition: {condition}")
    else:
        parts.append("Alert on any change or notable update.")
    if source == "mcp":
        parts.append("Data source: Use MCP tools if available, fall back to web_search.")
    else:
        parts.append("Data source: Use web_search to fetch the latest data.")
    parts.append(
        "If there is nothing to report (no change, condition not met), "
        "output [SILENT] to suppress delivery."
    )
    return "\n".join(parts)


def _derive_name(query: str) -> str:
    """Derive a short monitor name from the query."""
    # Take first 3 words, lowercase, hyphenated
    words = query.strip().lower().split()[:4]
    return "-".join(words) if words else "monitor"


def _find_monitor_jobs(include_all: bool = False) -> list[dict[str, Any]]:
    """List cron jobs that are monitors (have the live-monitor skill)."""
    try:
        from cron.jobs import list_jobs

        jobs = list_jobs(include_disabled=include_all)
        return [
            j for j in jobs
            if "live-monitor" in (j.get("skills") or [])
            or j.get("skill") == "live-monitor"
        ]
    except Exception as e:
        print(f"Error listing monitors: {e}")
        return []


def _find_job_by_name(name: str) -> Optional[dict[str, Any]]:
    """Find a monitor job by name (case-insensitive) or ID.

    Handles the 'monitor:' prefix on job names — users can specify
    'aapl-stock-price' or 'monitor:aapl-stock-price' interchangeably.
    """
    monitors = _find_monitor_jobs(include_all=True)
    name_lower = name.strip().lower()
    # Also try with the monitor: prefix stripped
    name_no_prefix = name_lower.removeprefix("monitor:")
    for j in monitors:
        job_name = (j.get("name") or "").strip().lower()
        job_id = (j.get("id") or "").strip().lower()
        # Strip monitor: prefix from job name for comparison
        job_name_no_prefix = job_name.removeprefix("monitor:")
        # Match against full name, name without prefix, or job ID
        if (
            name_lower == job_name
            or name_no_prefix == job_name
            or name_lower == job_name_no_prefix
            or name_no_prefix == job_name_no_prefix
            or name_lower == job_id
        ):
            return j
    return None


def monitor_command(args) -> None:
    """Dispatch ``hermes monitor <action>``."""
    action = getattr(args, "monitor_action", None)

    if action is None:
        print("usage: hermes monitor <action> [options]\n")
        print("actions:")
        print("  add       Add a new monitor")
        print("  list      List active monitors")
        print("  remove    Remove a monitor")
        print("  pause     Pause a monitor")
        print("  resume    Resume a paused monitor")
        print("  run       Trigger a monitor immediately (test run)")
        return

    if action == "add":
        _monitor_add(args)
        return

    if action in ("list", "ls"):
        _monitor_list(args)
        return

    if action in ("remove", "rm", "delete"):
        _monitor_remove(args)
        return

    if action == "pause":
        _monitor_pause(args)
        return

    if action == "resume":
        _monitor_resume(args)
        return

    if action == "run":
        _monitor_run(args)
        return

    print(f"Unknown monitor action: {action}")


def _monitor_add(args) -> None:
    """Create a new monitor as a cron job with the live-monitor skill."""
    from cron.jobs import create_job

    query = args.query
    name = args.name or _derive_name(query)
    condition = getattr(args, "condition", None)
    source = getattr(args, "source", "web")
    interval = args.interval
    deliver = args.deliver
    repeat = getattr(args, "repeat", None)

    # Check for duplicate name
    existing = _find_job_by_name(name)
    if existing:
        print(f"Monitor '{name}' already exists (ID: {existing['id']}).")
        print("Use a different --name, or remove the existing monitor first.")
        return

    prompt = _build_monitor_prompt(query, condition, source)

    try:
        job = create_job(
            prompt=prompt,
            schedule=interval,
            name=f"monitor:{name}",
            skills=["live-monitor"],
            deliver=deliver,
            repeat=repeat,
        )
    except Exception as e:
        print(f"Error creating monitor: {e}")
        return

    print(f"✓ Monitor '{name}' created")
    print(f"  Query: {query}")
    if condition:
        print(f"  Condition: {condition}")
    print(f"  Interval: {interval}")
    print(f"  Delivery: {deliver}")
    print(f"  Job ID: {job.get('id', 'unknown')}")
    print(f"  Next run: {job.get('next_run_at', 'pending scheduler tick')}")
    print()
    print("The monitor will check periodically and alert you when conditions are met.")
    print("Use 'hermes monitor list' to see all active monitors.")


def _monitor_list(args) -> None:
    """List all active monitors."""
    include_all = getattr(args, "all", False)
    monitors = _find_monitor_jobs(include_all=include_all)

    if not monitors:
        print("No active monitors.")
        print("Add one with: hermes monitor add 'Lakers score' --deliver telegram")
        return

    print(f"{'Name':<25} {'Interval':<20} {'Deliver':<12} {'Status':<10} {'ID'}")
    print("-" * 90)
    for j in monitors:
        name = (j.get("name") or "").removeprefix("monitor:")
        schedule = j.get("schedule_display") or j.get("schedule") or ""
        deliver = j.get("deliver") or "local"
        status = "paused" if not j.get("enabled", True) else "active"
        if j.get("last_status"):
            status += f" ({j['last_status']})"
        job_id = j.get("id", "")
        print(f"{name:<25} {schedule:<20} {deliver:<12} {status:<10} {job_id}")

    print(f"\n{len(monitors)} monitor(s) total.")


def _monitor_remove(args) -> None:
    """Remove a monitor by name or ID."""
    from cron.jobs import remove_job

    name = args.name
    job = _find_job_by_name(name)
    if not job:
        print(f"Monitor '{name}' not found.")
        print("Use 'hermes monitor list' to see available monitors.")
        return

    try:
        remove_job(job["id"])
        print(f"✓ Monitor '{job.get('name', name)}' removed.")
    except Exception as e:
        print(f"Error removing monitor: {e}")


def _monitor_pause(args) -> None:
    """Pause a monitor."""
    from cron.jobs import pause_job

    name = args.name
    job = _find_job_by_name(name)
    if not job:
        print(f"Monitor '{name}' not found.")
        return

    try:
        pause_job(job["id"])
        print(f"✓ Monitor '{job.get('name', name)}' paused.")
        print("Use 'hermes monitor resume <name>' to resume.")
    except Exception as e:
        print(f"Error pausing monitor: {e}")


def _monitor_resume(args) -> None:
    """Resume a paused monitor."""
    from cron.jobs import resume_job

    name = args.name
    job = _find_job_by_name(name)
    if not job:
        print(f"Monitor '{name}' not found.")
        return

    try:
        resume_job(job["id"])
        print(f"✓ Monitor '{job.get('name', name)}' resumed.")
    except Exception as e:
        print(f"Error resuming monitor: {e}")


def _monitor_run(args) -> None:
    """Trigger a monitor to run on the next tick."""
    from cron.jobs import trigger_job

    name = args.name
    job = _find_job_by_name(name)
    if not job:
        print(f"Monitor '{name}' not found.")
        return

    try:
        trigger_job(job["id"])
        print(f"✓ Monitor '{job.get('name', name)}' triggered — will run on next scheduler tick.")
        print("(Make sure the cron scheduler is running: hermes cron status)")
    except Exception as e:
        print(f"Error triggering monitor: {e}")
