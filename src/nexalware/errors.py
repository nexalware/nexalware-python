from __future__ import annotations

from typing import Any, List, Optional


class NexalwareApiError(Exception):
    """Raised for any non-2xx response from the Nexalware API. Mirrors the
    platform's own error envelope (``{ error, message?, details? }``) so
    callers get the same reason a dashboard user or curl call would see,
    not a generic HTTP failure.
    """

    def __init__(
        self,
        status: int,
        error: str,
        message: Optional[str] = None,
        details: Optional[List[Any]] = None,
    ) -> None:
        self.status = status
        self.error = error
        self.message = message
        self.details = details
        super().__init__(message or error or f"Nexalware API request failed with status {status}")
