"""
Catalog URLs.

Shapes follow the style guide: kebab-case segments, plural resource names, nested
resources under their parent, and non-CRUD operations under an `actions/` segment so they
can never be mistaken for a resource.

    /v2/catalog/datasets/
    /v2/catalog/datasets/{dataset_uuid}/
    /v2/catalog/datasets/{dataset_uuid}/data-elements/
    /v2/catalog/datasets/{dataset_uuid}/data-elements/actions/bulk-create/
    /v2/catalog/datasets/{dataset_uuid}/data-elements/{data_element_uuid}/

The `uuid` path converter is doing real work: a malformed identifier never reaches a view,
it is a 404 at routing time. It is also why the `actions/` route cannot be shadowed by the
detail route below it -- "actions" is not a UUID.
"""

from django.urls import path

from catalog.api.views import (
    DataElementBulkCreateView,
    DataElementDetailView,
    DataElementView,
    DatasetDetailView,
    DatasetView,
)

app_name = "catalog"

urlpatterns = [
    path(
        "datasets/",
        DatasetView.as_view(),
        name="datasets",
    ),
    path(
        "datasets/<uuid:dataset_uuid>/",
        DatasetDetailView.as_view(),
        name="dataset-detail",
    ),
    path(
        "datasets/<uuid:dataset_uuid>/data-elements/",
        DataElementView.as_view(),
        name="data-elements",
    ),
    path(
        "datasets/<uuid:dataset_uuid>/data-elements/actions/bulk-create/",
        DataElementBulkCreateView.as_view(),
        name="data-elements-bulk-create",
    ),
    path(
        "datasets/<uuid:dataset_uuid>/data-elements/<uuid:data_element_uuid>/",
        DataElementDetailView.as_view(),
        name="data-element-detail",
    ),
]
