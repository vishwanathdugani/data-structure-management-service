"""
Data element endpoints.

Every route here is nested under a dataset. The dataset is resolved first, from the URL, so
a request for an element of a dataset that does not exist is a 404 about the dataset --
not a confusing empty list.
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
from api.v2.core.serializers import inline_serializer
from catalog import selectors, services
from catalog.api.serializers import (
    DataElementBulkCreateInputSerializer,
    DataElementCreateInputSerializer,
    DataElementSerializer,
    DataElementUpdateInputSerializer,
    data_elements_for_serialization,
    serialize_data_element,
    serialize_data_elements,
)
from catalog.filters import DataElementFilterSet
from catalog.selectors import DataElementOrderingService

DATASET_UUID_PARAMETER = OpenApiParameter(
    name="dataset_uuid",
    type=str,
    location=OpenApiParameter.PATH,
    description="Public UUID of the dataset the element belongs to.",
)
DATA_ELEMENT_UUID_PARAMETER = OpenApiParameter(
    name="data_element_uuid",
    type=str,
    location=OpenApiParameter.PATH,
    description="Public UUID of the data element.",
)


class DataElementView(BaseView):
    """List and create the data elements of one dataset."""

    @extend_schema(
        operation_id="dataset_data_elements_list",
        summary="List a dataset's data elements",
        description=(
            "Returns a paginated, filterable list of the data elements belonging to one "
            "dataset. `?is_pii=true` narrows it to the personal data a dataset holds."
        ),
        parameters=[
            DATASET_UUID_PARAMETER,
            *filterset_parameters(DataElementFilterSet),
            ordering_parameter(DataElementOrderingService),
            *pagination_parameters(),
        ],
        responses={
            200: paginated_response(
                name="PaginatedDataElementList",
                child=DataElementSerializer(many=True),
            ),
            400: VALIDATION_ERROR_RESPONSE,
            404: NOT_FOUND_ERROR_RESPONSE,
        },
        tags=["Data elements"],
    )
    def get(self, request: Request, dataset_uuid: str, *args, **kwargs) -> Response:
        dataset = selectors.get_dataset(dataset_uuid=dataset_uuid)

        data_elements = selectors.get_data_elements(
            dataset=dataset,
            filters=request.query_params,
            ordering=self.get_ordering(request),
        )
        # Join before paginating; see `data_elements_for_serialization`.
        page = self.paginate_queryset(data_elements_for_serialization(data_elements))

        serializer = serialize_data_elements(page)
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        operation_id="dataset_data_elements_create",
        summary="Add a data element to a dataset",
        description=(
            "Adds one data element. Names are unique within a dataset, case-insensitively, "
            "`max_length` is only accepted on `string` elements, and a dataset may have at "
            "most one primary key.\n\n"
            "`is_nullable` may be omitted, in which case it is derived from "
            "`is_primary_key`. Marking an element as PII requires the dataset to declare a "
            "retention period first, and an archived dataset accepts no new elements."
        ),
        parameters=[DATASET_UUID_PARAMETER],
        request=DataElementCreateInputSerializer,
        responses={
            201: DataElementSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            404: NOT_FOUND_ERROR_RESPONSE,
            409: CONFLICT_ERROR_RESPONSE,
        },
        tags=["Data elements"],
    )
    def post(self, request: Request, dataset_uuid: str, *args, **kwargs) -> Response:
        dataset = selectors.get_dataset(dataset_uuid=dataset_uuid)

        input_serializer = DataElementCreateInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        data_element = services.create_data_element(
            dataset=dataset,
            **input_serializer.validated_data,
        )

        output_serializer = serialize_data_element(data_element)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


class DataElementDetailView(BaseView):
    """Retrieve and update a single data element."""

    @extend_schema(
        operation_id="dataset_data_elements_retrieve",
        summary="Retrieve a data element",
        parameters=[DATASET_UUID_PARAMETER, DATA_ELEMENT_UUID_PARAMETER],
        responses={200: DataElementSerializer, 404: NOT_FOUND_ERROR_RESPONSE},
        tags=["Data elements"],
    )
    def get(
        self, request: Request, dataset_uuid: str, data_element_uuid: str, *args, **kwargs
    ) -> Response:
        dataset = selectors.get_dataset(dataset_uuid=dataset_uuid)
        data_element = selectors.get_data_element(
            dataset=dataset,
            data_element_uuid=data_element_uuid,
        )
        serializer = serialize_data_element(data_element)
        return Response(serializer.data)

    @extend_schema(
        operation_id="dataset_data_elements_partial_update",
        summary="Update a data element",
        description=(
            "Partially updates a data element. The element cannot be moved to another "
            "dataset, and the same rules as on create apply to the resulting state."
        ),
        parameters=[DATASET_UUID_PARAMETER, DATA_ELEMENT_UUID_PARAMETER],
        request=DataElementUpdateInputSerializer,
        responses={
            200: DataElementSerializer,
            400: VALIDATION_ERROR_RESPONSE,
            404: NOT_FOUND_ERROR_RESPONSE,
            409: CONFLICT_ERROR_RESPONSE,
        },
        tags=["Data elements"],
    )
    def patch(
        self, request: Request, dataset_uuid: str, data_element_uuid: str, *args, **kwargs
    ) -> Response:
        dataset = selectors.get_dataset(dataset_uuid=dataset_uuid)
        data_element = selectors.get_data_element(
            dataset=dataset,
            data_element_uuid=data_element_uuid,
        )

        input_serializer = DataElementUpdateInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        data_element = services.update_data_element(
            data_element=data_element,
            **input_serializer.validated_data,
        )

        output_serializer = serialize_data_element(data_element)
        return Response(output_serializer.data)


class DataElementBulkCreateView(BaseView):
    """Create several data elements in one atomic request."""

    @extend_schema(
        operation_id="dataset_data_elements_bulk_create",
        summary="Bulk-create data elements",
        description=(
            "Adds up to 100 data elements in a single transaction. Defining an entity's "
            "structure is naturally one action, and doing it as one request means the "
            "catalog never shows a half-described dataset: if any element is rejected, none "
            "are created and the error reports the offending `index`."
        ),
        parameters=[DATASET_UUID_PARAMETER],
        request=DataElementBulkCreateInputSerializer,
        responses={
            201: inline_serializer(
                name="DataElementBulkCreateOutputSerializer",
                fields={"data_elements": DataElementSerializer(many=True)},
            ),
            400: VALIDATION_ERROR_RESPONSE,
            404: NOT_FOUND_ERROR_RESPONSE,
            409: CONFLICT_ERROR_RESPONSE,
        },
        tags=["Data elements"],
    )
    def post(self, request: Request, dataset_uuid: str, *args, **kwargs) -> Response:
        dataset = selectors.get_dataset(dataset_uuid=dataset_uuid)

        input_serializer = DataElementBulkCreateInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        data_elements = services.bulk_create_data_elements(
            dataset=dataset,
            data_elements=input_serializer.validated_data["data_elements"],
        )

        output_serializer = inline_serializer(
            name="DataElementBulkCreateOutputSerializer",
            fields={"data_elements": DataElementSerializer(many=True)},
            instance={"data_elements": data_elements},
        )
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)
