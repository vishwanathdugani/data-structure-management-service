"""Filtering rules for the dataset list endpoint."""

from django.db.models import Exists, OuterRef, Q, QuerySet

from api.v2.core.filters.base_filters import (
    BaseFilterSet,
    BooleanFilter,
    CharFilter,
    CharInFilter,
    ChoiceFilter,
    IsoDateTimeFromToRangeFilter,
)
from catalog.models import DataElement, Dataset, DatasetLifecycleStatus


class DatasetFilterSet(BaseFilterSet):
    """
    Declares exactly which query parameters `/v2/catalog/datasets/` accepts.

    A `FilterSet` is a whitelist. Anything not named here is ignored rather than passed
    through to the ORM, so query parameters can never be used to filter or traverse
    relations we did not intend to expose.
    """

    name = CharFilter(lookup_expr="icontains", help_text="Case-insensitive substring match.")
    owner = CharFilter(lookup_expr="iexact")
    lifecycle_status = ChoiceFilter(choices=DatasetLifecycleStatus.choices)
    lifecycle_status__in = CharInFilter(
        field_name="lifecycle_status",
        lookup_expr="in",
        help_text="Comma-separated, e.g. 'draft,active'.",
    )
    # `exclude=True` inverts the `isnull` lookup, so `?has_retention_period=true` means
    # "a retention period is declared" rather than the double negative it maps to in SQL.
    has_retention_period = BooleanFilter(
        field_name="retention_period_days",
        lookup_expr="isnull",
        exclude=True,
    )
    contains_pii = BooleanFilter(
        method="filter_contains_pii",
        help_text="Whether the dataset has at least one data element marked as PII.",
    )
    created_at = IsoDateTimeFromToRangeFilter(
        help_text="Range filter: use created_at_after / created_at_before.",
    )
    search = CharFilter(
        method="filter_search",
        help_text="Free-text search across name, description and owner.",
    )

    class Meta:
        model = Dataset
        fields: list[str] = []

    def filter_contains_pii(self, queryset: QuerySet, name: str, value: bool | None) -> QuerySet:
        """
        Filter on the presence of PII, using a correlated EXISTS.

        No empty-value guard: django_filters skips a filter whose value is in EMPTY_VALUES
        before ever calling the method, so `?contains_pii=` never reaches this.

        A join plus `.distinct()` would work too, but EXISTS lets the database stop at the
        first matching data element per dataset and keeps the row count intact, which
        matters because the caller is about to paginate this queryset.
        """
        has_pii = Exists(DataElement.objects.filter(dataset=OuterRef("pk"), is_pii=True))
        return queryset.filter(has_pii) if value else queryset.filter(~has_pii)

    def filter_search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match the term against any of the human-readable columns."""
        return queryset.filter(
            Q(name__icontains=value) | Q(description__icontains=value) | Q(owner__icontains=value)
        )
