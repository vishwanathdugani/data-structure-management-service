"""Helpers for applying a `FilterSet` from inside a selector."""

from django.db.models import QuerySet
from django_filters.rest_framework import FilterSet

from common.exceptions import ValidationError


def apply_filters(
    *,
    filterset_class: type[FilterSet],
    filters: dict | None,
    queryset: QuerySet,
) -> QuerySet:
    """
    Validate `filters` against `filterset_class` and return the filtered queryset.

    Selectors call this instead of touching `FilterSet` directly, so that a bad filter
    value produces the same 400 everywhere rather than each selector inventing its own
    handling -- or, worse, `filterset.qs` silently ignoring the broken filter and returning
    an unfiltered list that looks like a successful query.

    Query parameters the `FilterSet` does not declare are ignored, which is what lets a
    view hand over `request.query_params` wholesale while `ordering`, `limit` and `offset`
    ride along in the same dict.
    """
    if not filters:
        return queryset

    filterset = filterset_class(data=filters, queryset=queryset)
    if not filterset.is_valid():
        raise ValidationError("Invalid filter parameters.", extra={"fields": filterset.errors})

    return filterset.qs
