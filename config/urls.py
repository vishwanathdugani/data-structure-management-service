"""Root URL configuration.

Everything the service exposes lives under a version prefix, so a future `/v3/` can be
introduced next to `/v2/` without touching existing clients.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("v2/", include("api.v2.urls", namespace="v2")),
]

# Routing-level failures (no matching URL, malformed UUID in the path) never reach a view,
# so DRF's exception handler cannot see them. These keep those responses in the same JSON
# envelope as every other API error. See config/api_errors.py.
handler404 = "config.api_errors.not_found"
handler500 = "config.api_errors.server_error_handler"
