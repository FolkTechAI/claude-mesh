"""Stable identifiers and timestamps for mesh events."""

from __future__ import annotations

import datetime as dt
import uuid


def utc_now() -> str:
    """Return a lexically sortable UTC timestamp with microsecond precision."""
    return dt.datetime.now(dt.UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def new_event_id() -> str:
    """Return a collision-resistant event identifier."""
    return f"evt-{uuid.uuid4()}"
