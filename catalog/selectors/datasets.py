"""
Dataset queries.

Selectors own *which rows* a caller gets: scoping, filtering and ordering. They return
querysets, unevaluated, so a view can paginate them and a service can compose them
further. What they deliberately do not do is `select_related` / `prefetch_related` -- those
belong next to the serializer that needs them (see `catalog/api/serializers/`), because a
prefetch baked into a selector is paid for by every caller, including the ones that only
wanted a count.
"""

from django.db.models import QuerySet

from api.v2.core.filters import apply_filters
from catalog.filters import DatasetFilterSet
from catalog.models import Dataset
from common.exceptions import NotFoundError
from common.models import queryset_ordering as ordering


class DatasetOrderingService(ordering.OrderingService):
    """Sortable fields for the dataset list endpoint."""

    name = ordering.StringField()
    owner = ordering.StringField()
    lifecycle_status = ordering.StringField()
    retention_period_days = ordering.NumberField()
    created_at = ordering.DateTimeField()
    updated_at = ordering.DateTimeField()

    # Newest first: a catalog is browsed far more often than it is searched, and the thing
    # someone just added is the thing they most likely came back to look at.
    _defaults = ("-created_at",)


def get_datasets(
    *,
    filters: dict | None = None,
    ordering: list[str] | None = None,
) -> QuerySet[Dataset]:
    """
    Return datasets for the list endpoint, filtered and ordered.

    `data_element_count` is annotated here rather than computed per row during
    serialization: one aggregate over the page instead of one query per dataset.
    """
    queryset = Dataset.objects.with_data_element_count()
    queryset = apply_filters(
        filterset_class=DatasetFilterSet,
        filters=filters,
        queryset=queryset,
    )
    return DatasetOrderingService.order_queryset(queryset, ordering)


def get_dataset(*, dataset_uuid) -> Dataset:
    """
    Return a single dataset by its public UUID.

    Raises `NotFoundError` rather than returning `None`, so that every caller -- view,
    service or task -- fails the same way and no caller can accidentally carry a `None`
    into the next line.
    """
    try:
        return Dataset.objects.with_data_element_count().get(uuid=dataset_uuid)
    except Dataset.DoesNotExist as exc:
        raise NotFoundError(f"Dataset {dataset_uuid} does not exist.") from exc
