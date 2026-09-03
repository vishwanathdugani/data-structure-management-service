"""
Domain-level exceptions.

These live in `common` (not in the API layer) on purpose: services and selectors raise
them without knowing that HTTP exists, and the API layer is the only place that decides
which status code each one maps to. That keeps the dependency direction one-way,
`api -> common`, and lets the same services be reused from a management command, a
Celery task or a test without dragging DRF along.

The translation to HTTP responses happens in `api/v2/core/exceptions.py`.
"""

from typing import Any


class ApplicationError(Exception):
    """
    Base class for every error that is caused by the caller rather than by a bug.

    `extra` carries machine-readable context (for example the offending field values) that
    the API layer passes through to the client untouched.
    """

    default_code = "error"

    def __init__(self, message: str, *, code: str | None = None, extra: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.extra: dict[str, Any] = extra or {}

    def __str__(self) -> str:
        return self.message


class ValidationError(ApplicationError):
    """The request was understood but its content is not acceptable. Maps to 400."""

    default_code = "validation_error"


class ConflictError(ApplicationError):
    """
    The request is valid but conflicts with the current state of the resource. Maps to 409.

    Used for lifecycle rules, for example writing to an archived dataset: retrying the
    exact same request will keep failing until the resource's state changes.
    """

    default_code = "conflict"


class NotFoundError(ApplicationError):
    """The addressed resource does not exist. Maps to 404."""

    default_code = "not_found"
