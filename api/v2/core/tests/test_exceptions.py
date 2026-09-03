"""
Tests for the single error envelope.

The envelope is a public contract: clients branch on `code` and display `detail`. These
tests pin every path into it, including the one that deliberately does *not* produce an
envelope -- an unexpected exception must stay a 500 rather than being dressed up as a
tidy 400.
"""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions as drf_exceptions

from api.v2.core.exceptions import exception_handler
from common.exceptions import ApplicationError, ConflictError, NotFoundError, ValidationError


def handle(exc: Exception):
    return exception_handler(exc, {})


class TestDomainExceptions:
    def test_application_error_becomes_a_400(self):
        response = handle(ApplicationError("Something is off."))

        assert response.status_code == 400
        assert response.data == {"code": "error", "detail": "Something is off.", "extra": {}}

    def test_validation_error_becomes_a_400(self):
        response = handle(ValidationError("Bad input.", extra={"field": "name"}))

        assert response.status_code == 400
        assert response.data["code"] == "validation_error"
        assert response.data["extra"] == {"field": "name"}

    def test_conflict_error_becomes_a_409(self):
        response = handle(ConflictError("Already archived."))

        assert response.status_code == 409
        assert response.data["code"] == "conflict"

    def test_not_found_error_becomes_a_404(self):
        response = handle(NotFoundError("Gone."))

        assert response.status_code == 404
        assert response.data["code"] == "not_found"

    def test_a_custom_code_overrides_the_default(self):
        response = handle(ValidationError("Bad input.", code="retention_required"))

        assert response.data["code"] == "retention_required"

    def test_a_subclass_inherits_its_parents_status(self):
        """New domain exceptions get sensible behaviour without touching the handler."""

        class SpecificConflict(ConflictError):
            default_code = "specific_conflict"

        response = handle(SpecificConflict("Nope."))

        assert response.status_code == 409
        assert response.data["code"] == "specific_conflict"


class TestFrameworkExceptions:
    def test_django_validation_errors_are_normalised(self):
        """Model `full_clean()` raises Django's ValidationError, not DRF's."""
        response = handle(DjangoValidationError({"name": ["This field cannot be blank."]}))

        assert response.status_code == 400
        assert response.data["code"] == "validation_error"
        assert response.data["extra"]["fields"]["name"] == ["This field cannot be blank."]

    def test_drf_validation_errors_are_nested_under_extra_fields(self):
        response = handle(drf_exceptions.ValidationError({"name": ["Required."]}))

        assert response.status_code == 400
        assert response.data["detail"] == "Invalid input."
        assert response.data["extra"]["fields"] == {"name": ["Required."]}

    def test_http404_becomes_the_not_found_envelope(self):
        response = handle(Http404())

        assert response.status_code == 404
        assert set(response.data) == {"code", "detail", "extra"}

    def test_django_permission_denied_becomes_a_403(self):
        response = handle(DjangoPermissionDenied())

        assert response.status_code == 403

    def test_method_not_allowed_keeps_its_detail(self):
        response = handle(drf_exceptions.MethodNotAllowed("DELETE"))

        assert response.status_code == 405
        assert "DELETE" in response.data["detail"]

    def test_throttling_keeps_its_retry_after_header(self):
        """The envelope must not swallow headers that carry protocol meaning."""
        response = handle(drf_exceptions.Throttled(wait=30))

        assert response.status_code == 429
        assert response.headers["Retry-After"] == "30"


class TestUnhandledExceptions:
    def test_an_unexpected_exception_is_not_converted(self):
        """
        Returning None hands the exception back to Django, so it becomes a 500 and gets
        reported. Turning a bug into a neat 400 would hide it from everyone.
        """
        assert handle(RuntimeError("boom")) is None
