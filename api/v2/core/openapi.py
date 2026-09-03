"""
Helpers that keep the generated OpenAPI document honest.

The views in this service are plain `APIView`s that call selectors and services directly,
which is what makes a request readable -- but it also means drf-spectacular cannot infer
the query parameters or the pagination envelope the way it can for a `ModelViewSet`.

Rather than hand-writing that per endpoint (which drifts the moment a filter is added),
these helpers derive the documentation from the same objects the runtime uses: the
`FilterSet` that does the filtering and the `OrderingService` that does the ordering. Add a
filter, and it shows up in the schema with no second edit.
"""

from django_filters import rest_framework as django_filters
from drf_spectacular.utils import OpenApiParameter
from rest_framework import serializers

from api.v2.core.pagination import LimitOffsetPagination
from api.v2.core.serializers import inline_serializer
from common.models.queryset_ordering import OrderingService


def error_response(*, name: str, description: str) -> serializers.Serializer:
    """Document the error envelope produced by `api.v2.core.exceptions.exception_handler`."""
    return inline_serializer(
        name=name,
        fields={
            "code": serializers.CharField(help_text="Machine-readable error category."),
            "detail": serializers.CharField(help_text=description),
            "extra": serializers.DictField(help_text="Error-specific context. May be empty."),
        },
    )


VALIDATION_ERROR_RESPONSE = error_response(
    name="ValidationErrorResponse",
    description="What was wrong with the request.",
)
CONFLICT_ERROR_RESPONSE = error_response(
    name="ConflictErrorResponse",
    description="Why the request conflicts with the current state of the resource.",
)
NOT_FOUND_ERROR_RESPONSE = error_response(
    name="NotFoundErrorResponse",
    description="Which resource could not be found.",
)


def paginated_response(*, name: str, child: serializers.Serializer) -> serializers.Serializer:
    """Wrap a serializer in the pagination envelope, matching `LimitOffsetPagination`."""
    return inline_serializer(
        name=name,
        fields={
            "count": serializers.IntegerField(help_text="Total matching records."),
            "limit": serializers.IntegerField(),
            "offset": serializers.IntegerField(),
            "next": serializers.CharField(allow_null=True),
            "previous": serializers.CharField(allow_null=True),
            "results": child,
        },
    )


def pagination_parameters() -> list[OpenApiParameter]:
    """The `?limit=` / `?offset=` parameters every list endpoint accepts."""
    return [
        OpenApiParameter(
            name=LimitOffsetPagination.limit_query_param,
            type=int,
            location=OpenApiParameter.QUERY,
            description=(
                f"Page size. Defaults to {LimitOffsetPagination.default_limit}, "
                f"capped at {LimitOffsetPagination.max_limit}."
            ),
        ),
        OpenApiParameter(
            name=LimitOffsetPagination.offset_query_param,
            type=int,
            location=OpenApiParameter.QUERY,
            description="Number of records to skip.",
        ),
    ]


def ordering_parameter(ordering_service: type[OrderingService]) -> OpenApiParameter:
    """Derive the `?ordering=` parameter from the endpoint's `OrderingService`."""
    allowed = ordering_service.allowed_fields()
    return OpenApiParameter(
        name="ordering",
        type=str,
        location=OpenApiParameter.QUERY,
        many=True,
        enum=sorted(allowed + [f"-{field}" for field in allowed]),
        description=(
            "Sort field, prefix with `-` for descending. Repeat the parameter to sort by "
            f"more than one field, in priority order. Defaults to "
            f"`{', '.join(ordering_service._defaults) or 'unordered'}`."
        ),
    )


#: django_filters field classes whose values are not plain strings.
_PARAMETER_TYPES: dict[type, type] = {
    django_filters.BooleanFilter: bool,
    django_filters.NumberFilter: int,
}


def filterset_parameters(filterset_class: type[django_filters.FilterSet]) -> list[OpenApiParameter]:
    """
    Derive `OpenApiParameter`s from a `FilterSet`, so the docs cannot drift from the code.

    Range filters (`created_at`) expand into the `_after` / `_before` pair that
    django_filters actually reads, because documenting the bare name would tell a client to
    send a parameter that does nothing.
    """
    parameters: list[OpenApiParameter] = []

    for name, filter_ in filterset_class.base_filters.items():
        description = filter_.extra.get("help_text", "")
        enum = None
        choices = filter_.extra.get("choices")
        if choices:
            enum = [value for value, _label in choices]

        parameter_type = next(
            (
                mapped
                for filter_class, mapped in _PARAMETER_TYPES.items()
                if isinstance(filter_, filter_class)
            ),
            str,
        )

        if isinstance(filter_, django_filters.RangeFilter | django_filters.DateFromToRangeFilter):
            for suffix in ("after", "before"):
                parameters.append(
                    OpenApiParameter(
                        name=f"{name}_{suffix}",
                        type=str,
                        location=OpenApiParameter.QUERY,
                        description=description,
                    )
                )
            continue

        parameters.append(
            OpenApiParameter(
                name=name,
                type=parameter_type,
                location=OpenApiParameter.QUERY,
                enum=enum,
                description=description,
            )
        )

    return parameters
