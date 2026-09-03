"""Version 2 URL root.

Each app owns its own URL module and is mounted here under its app segment, giving the
`/v2/<app>/<resource>s/` shape the style guide asks for.
"""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

app_name = "v2"

urlpatterns = [
    # Machine-readable schema and a browsable UI for it.
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="v2:schema"), name="docs"),
    path("catalog/", include("catalog.api.urls", namespace="catalog")),
]
