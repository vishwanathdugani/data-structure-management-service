"""
The filter primitives apps are expected to build their `FilterSet`s from.

Everything here is a thin pass-through over `django_filters` today. The indirection earns
its keep the first time a default has to change service-wide -- for example making every
`CharFilter` case-insensitive, or teaching every filter the same null handling. That then
happens in one file instead of in every app.
"""

from django_filters import rest_framework as filters

CharFilter = filters.CharFilter
BooleanFilter = filters.BooleanFilter
ChoiceFilter = filters.ChoiceFilter
MultipleChoiceFilter = filters.MultipleChoiceFilter
NumberFilter = filters.NumberFilter
UUIDFilter = filters.UUIDFilter
DateTimeFilter = filters.DateTimeFilter
DateFromToRangeFilter = filters.DateFromToRangeFilter
IsoDateTimeFromToRangeFilter = filters.IsoDateTimeFromToRangeFilter
OrderingFilter = filters.OrderingFilter


class BaseFilterSet(filters.FilterSet):
    """Base class for every `FilterSet` in the service."""


class CharInFilter(filters.BaseInFilter, filters.CharFilter):
    """
    Matches a column against a comma-separated list: `?data_type__in=string,integer`.

    Saves clients from issuing one request per value, which is the usual reason a list
    endpoint ends up being called in a loop.
    """


__all__ = [
    "BaseFilterSet",
    "BooleanFilter",
    "CharFilter",
    "CharInFilter",
    "ChoiceFilter",
    "DateFromToRangeFilter",
    "DateTimeFilter",
    "IsoDateTimeFromToRangeFilter",
    "MultipleChoiceFilter",
    "NumberFilter",
    "OrderingFilter",
    "UUIDFilter",
]
