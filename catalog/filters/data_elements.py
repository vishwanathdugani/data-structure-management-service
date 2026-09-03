"""Filtering rules for the data element list endpoint."""

from django.db.models import Q, QuerySet

from api.v2.core.filters.base_filters import (
    BaseFilterSet,
    BooleanFilter,
    CharFilter,
    CharInFilter,
    ChoiceFilter,
)
from catalog.models import DataElement, DataType


class DataElementFilterSet(BaseFilterSet):
    """
    Query parameters accepted by `/v2/catalog/datasets/{dataset_uuid}/data-elements/`.

    Note that there is no `dataset` filter: the dataset is part of the URL, and the
    selector scopes the queryset before the filter set ever sees it. A filter that could
    widen the scope set by the route would be a way to read another dataset's elements.
    """

    name = CharFilter(lookup_expr="icontains", help_text="Case-insensitive substring match.")
    data_type = ChoiceFilter(choices=DataType.choices)
    data_type__in = CharInFilter(
        field_name="data_type",
        lookup_expr="in",
        help_text="Comma-separated, e.g. 'string,integer'.",
    )
    is_pii = BooleanFilter()
    is_nullable = BooleanFilter()
    is_primary_key = BooleanFilter()
    search = CharFilter(
        method="filter_search",
        help_text="Free-text search across name and description.",
    )

    class Meta:
        model = DataElement
        fields: list[str] = []

    def filter_search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """django_filters skips empty values, so `value` is always a real search term."""
        return queryset.filter(Q(name__icontains=value) | Q(description__icontains=value))
