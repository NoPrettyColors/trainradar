"""Short, fixed labels for upstream failures.

Feed and download errors are shown publicly (/api/sources, /api/status), so they carry a label
from a fixed set instead of the exception text, which can include URLs, paths or addresses.
The full exception goes to the log.
"""

from __future__ import annotations

import socket
import urllib.error


class TooLarge(ValueError):
    """An upstream response passed its size cap."""


def read_capped(response, limit: int) -> bytes:
    """Read a whole response, refusing one larger than limit bytes."""
    data = response.read(limit + 1)
    if len(data) > limit:
        raise TooLarge(f"response over {limit} bytes")
    return data


def label(e: BaseException) -> str:
    if isinstance(e, TooLarge):
        return "too large"
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    if isinstance(e, urllib.error.URLError):
        return "timeout" if isinstance(e.reason, (TimeoutError, socket.timeout)) else "connection failed"
    if isinstance(e, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(e, OSError):
        return "connection failed"
    if isinstance(e, (ValueError, KeyError, TypeError, IndexError)):  # includes JSONDecodeError
        return "bad data"
    return "unavailable"
