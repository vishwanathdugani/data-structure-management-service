"""
One error envelope for the whole API.

Every failure -- a serializer rejecting input, a service raising a domain error, a missing
object, an unhandled `IntegrityError` -- leaves this service in the same shape:

    {
      "code": "validation_error",
      "detail": "Invalid input.",
      "extra": {"fields": {"name": ["This field is required."]}}
    }

Clients can therefore branch on `code` and render `detail`, without special-casing the
half-dozen different bodies DRF produces out of the box.
"""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.serializers import as_serializer_error
from rest_framework.views import exception_handler as drf_exception_handler

from common.exceptions import ApplicationError, ConflictError, NotFoundError, ValidationError

# Mapping from domain exception to HTTP status. Keeping it here, rather than as an
# attribute on the exceptions themselves, is what allows `common` to stay HTTP-agnostic.
_STATUS_BY_EXCEPTION: dict[type[ApplicationError], int] = {
    ValidationError: 400,
    ConflictError: 409,
    NotFoundError: 404,
    ApplicationError: 400,
}


def _status_for(exc: ApplicationError) -> int:
    """Resolve the status code for a domain exception, honouring subclassing."""
    for klass in type(exc).__mro__:
        if klass in _STATUS_BY_EXCEPTION:
            return _STATUS_BY_EXCEPTION[klass]
    return 400  # pragma: no cover - unreachable while ApplicationError is the root


def exception_handler(exc: Exception, ctx: dict) -> Response | None:
    """
    DRF exception handler, wired up in `REST_FRAMEWORK["EXCEPTION_HANDLER"]`.

    Returning `None` hands the exception back to Django, which turns it into a 500 and
    reports it. That is deliberate: an exception we did not anticipate is a bug, and
    quietly converting it into a tidy 400 would hide it.
    """
    # Model-level validation (`full_clean`) raises Django's ValidationError, not DRF's.
    # `as_serializer_error` normalises both the field-mapped and the message-list forms.
    if isinstance(exc, DjangoValidationError):
        exc = drf_exceptions.ValidationError(as_serializer_error(exc))

    if isinstance(exc, Http404):
        exc = drf_exceptions.NotFound()

    if isinstance(exc, DjangoPermissionDenied):
        exc = drf_exceptions.PermissionDenied()

    if isinstance(exc, ApplicationError):
        return Response(
            {"code": exc.code, "detail": exc.message, "extra": exc.extra},
            status=_status_for(exc),
        )

    response = drf_exception_handler(exc, ctx)
    if response is None:
        return None

    if isinstance(exc, drf_exceptions.ValidationError):
        # DRF puts field errors at the top level; we nest them under `extra.fields` so the
        # envelope keys never collide with a field literally called "detail" or "code".
        return Response(
            {
                "code": "validation_error",
                "detail": "Invalid input.",
                "extra": {"fields": response.data},
            },
            status=response.status_code,
        )

    detail = response.data.get("detail") if isinstance(response.data, dict) else None
    return Response(
        {
            "code": getattr(exc, "default_code", "error"),
            "detail": str(detail) if detail is not None else str(exc),
            "extra": {},
        },
        status=response.status_code,
        headers=dict(response.headers or {}),
    )
