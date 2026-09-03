"""
Django-level error handlers.

DRF's exception handler only runs once a request has reached a view. A URL that matches no
route -- or a malformed UUID, which the `uuid` path converter rejects during routing --
never gets that far, so without this it would answer an API client with Django's HTML
error page. These handlers keep the error envelope uniform right up to the edge.

Only API paths are converted; the admin keeps its normal HTML pages.
"""

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.defaults import page_not_found, server_error

API_PATH_PREFIX = "/v2/"


def _is_api_request(request: HttpRequest) -> bool:
    return request.path.startswith(API_PATH_PREFIX)


def not_found(request: HttpRequest, exception: Exception, *args, **kwargs) -> HttpResponse:
    if not _is_api_request(request):
        return page_not_found(request, exception, *args, **kwargs)

    return JsonResponse(
        {
            "code": "not_found",
            "detail": "No resource matches this URL.",
            "extra": {"path": request.path},
        },
        status=404,
    )


def server_error_handler(request: HttpRequest, *args, **kwargs) -> HttpResponse:
    if not _is_api_request(request):
        return server_error(request, *args, **kwargs)

    # Deliberately opaque: an unhandled exception is a bug, and its details belong in the
    # logs and the error tracker, not in a response body.
    return JsonResponse(
        {"code": "server_error", "detail": "Internal server error.", "extra": {}},
        status=500,
    )
