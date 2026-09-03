"""Data element queries. Always scoped to a dataset."""

from django.db.models import QuerySet

from api.v2.core.filters import apply_filters
from catalog.filters import DataElementFilterSet
from catalog.models import DataElement, Dataset
from common.exceptions import NotFoundError
from common.models import queryset_ordering as ordering


class DataElementOrderingService(ordering.OrderingService):
    """Sortable fields for the data element list endpoint."""

    name = ordering.StringField()
    data_type = ordering.StringField()
    is_pii = ordering.BooleanField()
    is_nullable = ordering.BooleanField()
    is_primary_key = ordering.BooleanField()
    created_at = ordering.DateTimeField()

    # Alphabetical by default. A dataset's fields are looked up by name, so this is the
    # order that makes an element findable by eye; `-created_at` would not.
    _defaults = ("name",)


def get_data_elements(
    *,
    dataset: Dataset,
    filters: dict | None = None,
    ordering: list[str] | None = None,
) -> QuerySet[DataElement]:
    """Return the data elements of `dataset`, filtered and ordered."""
    queryset = DataElement.objects.for_dataset(dataset)
    queryset = apply_filters(
        filterset_class=DataElementFilterSet,
        filters=filters,
        queryset=queryset,
    )
    return DataElementOrderingService.order_queryset(queryset, ordering)


def get_data_element(*, dataset: Dataset, data_element_uuid) -> DataElement:
    """
    Return one data element belonging to `dataset`.

    The dataset is part of the lookup, not checked afterwards. An element addressed under
    the wrong dataset is a 404, which is both correct (that URL names nothing) and the
    behaviour that does not leak the existence of another dataset's fields.
    """
    try:
        return DataElement.objects.get(dataset=dataset, uuid=data_element_uuid)
    except DataElement.DoesNotExist as exc:
        raise NotFoundError(
            f"Data element {data_element_uuid} does not exist in dataset {dataset.uuid}."
        ) from exc
