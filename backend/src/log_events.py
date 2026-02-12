"""Structured log events for remaster responses (observability / frontend logs panel)."""

from datetime import datetime


def log_event(level: str, step: str, message: str, debug: str | None = None) -> dict:
    """Return a structured log event: { ts, level, step, message, debug? }."""
    ev = {
        "ts": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "level": level,
        "step": step,
        "message": message,
    }
    if debug:
        ev["debug"] = debug
    return ev
