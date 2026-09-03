"""
Dataset endpoints.

Each handler reads as three steps: validate the input, hand off to a selector or a service,
serialize the result. No business rule is decided here -- if a handler ever needs to answer
"is this allowed?", that answer belongs in `catalog/services/rules.py`.
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from api.v2.core.base import BaseView
from api.v2.core.openapi import (
    CONFLICT_ERROR_RESPONSE,
    NOT_FOUND_ERROR_RESPONSE,
    VALIDATION_ERROR_RESPONSE,
    filterset_parameters,
    ordering_parameter,
    paginated_response,
    pagination_parameters,
)
from catalog import selectors, services
from catalog.api.serializers import (
    DatasetCreateInputSerializer,
    DatasetDetailSerializer,
    DatasetSerializer,
    DatasetUpdateInputSerializer,
    serialize_dataset,
    serialize_dataset_detail,
    serialize_datasets,
)
from catalog.filters import DatasetFilterSet
from catalog.selectors import DatasetOrderingService

DATASET_UUID_PARAMETER = OpenApiParameter(
    name="dataset_uuid",
    type=str,
    location=OpenApiParameter.PATH,
    description="Public UUID of the dataset.",
)


class DatasetView(BaseView):
    """List and create datasets."""

    @extend_schema(
        operation_id="datasets_list",
        summary="List datasets",
        description=(
            "Returns a paginated, filterable list of datasets. Data elements are not "
            "embedded; `data_element_count` reports how many each dataset has, and the "
            "elements themselves are available from the dataset's data element endpoint."
        ),
        parameters=[
            *filterset_parameters(DatasetFilterSet),
            ordering_parameter(DatasetOrderingService),
            *pagination_parameters(),
        ],
        responses={
            200: paginated_response(
                name="PaginatedDatasetList",
                child=DatasetSerializer(many=True),
            ),
            400: VALIDATION_ERROR_RESPONSE,
        },
        tags=["Datasets"],
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        datasets = selectors.get_datasets(
            filters=request.query_params,
            ordering=self.get_ordering(request),
        )
        page = self.paginate_queryset(datasets)
        serializer = serialize_datasets(page)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        operation_id="datasets_create",
        summary="Create a dataset",
        description=(
            "Creates a dataset. A dataset starts in `draft` unless `active` is requested; "
            "later lifecycle changes go through PATCH and follow the lifecycle rules. "
            "Names are unique case-insensitively."
        ),
        request=DatasetCreateInputSerializer,
        responses={
            201: DatasetSerializer,
            400: VALIDATION_ERROR_RESPONSE,
        },
        tags=["Datasets"],
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        input_serializer = DatasetCreateInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        dataset = services.create_dataset(**input_serializer.validated_data)

        # A freshly created dataset has no elements, so the annotation the read path
        # supplies is not there. Setting it keeps the create response the same shape as
        # every other dataset response, which is what stops clients special-casing it.
        dataset.data_element_count = 0

        output_serializer = serialize_dataset(dataset)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


class DatasetDetailView(BaseView):
    """Retrieve and update a single dataset."""

    @extend_schema(
        operation_id="datasets_retrieve",
        summary="Retrieve a dataset with its data elements",
        description=(
            "Returns one dataset together with its data elements, ordered by name. This is "
            "the only nested response in the API; everywhere else resources are flat."
        ),
        parameters=[DATASET_UUID_PARAMETER],
        responses={
            200: DatasetDetailSerializer,
            404: NOT_FOUND_ERROR_RESPONSE,
        },
        tags=["Datasets"],
    )
    def get(self, request: Request, dataset_uuid: str, *args, **kwargs) -> Response:
        dataset = selectors.get_dataset(dataset_uuid=dataset_uuid)
        serializer = serialize_dataset_detail(dataset)
        return Response(serializer.data)

    @extend_schema(
        operation_id="datasets_partial_update",
        summary="Update a dataset",
        description=(
            "Partially updates a dataset. Only the fields present in the body are changed.\n\n"
            "Two rules apply. Lifecycle changes must follow `draft -> active -> deprecated`, "
            "with `archived` reachable from anywhere and terminal; an archived dataset "
            "rejects all further writes with 409. And the retention period cannot be removed "
            "while the dataset still has data elements marked as PII."
        ),
        parameters=[DATASET_UUID_PARAMETER],
        request=DatasetUpdateInputSerializer,
        responses={
            200: DatasetSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            404: NOT_FOUND_ERROR_RESPONSE,
            409: CONFLICT_ERROR_RESPONSE,
        },
        tags=["Datasets"],
    )
    def patch(self, request: Request, dataset_uuid: str, *args, **kwargs) -> Response:
        dataset = selectors.get_dataset(dataset_uuid=dataset_uuid)

        input_serializer = DatasetUpdateInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        dataset = services.update_dataset(dataset=dataset, **input_serializer.validated_data)

        output_serializer = serialize_dataset(dataset)
        return Response(output_serializer.data)
