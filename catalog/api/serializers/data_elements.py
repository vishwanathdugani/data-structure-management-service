"""Data element serializers."""

from django.db.models import QuerySet
from rest_framework import serializers

from catalog.models import DataElement, DataType

#: A batch has to be bounded. Without a ceiling, one request can ask the service to run an
#: unbounded number of inserts inside a single transaction.
MAX_BULK_CREATE_SIZE = 100


class DataElementSerializer(serializers.Serializer):
    """The full representation of a data element."""

    data_element_uuid = serializers.UUIDField(source="uuid", read_only=True)
    dataset_uuid = serializers.UUIDField(source="dataset.uuid", read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    data_type = serializers.ChoiceField(choices=DataType.choices, read_only=True)
    max_length = serializers.IntegerField(read_only=True, allow_null=True)
    is_nullable = serializers.BooleanField(read_only=True)
    is_primary_key = serializers.BooleanField(read_only=True)
    is_pii = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class DataElementCreateInputSerializer(serializers.Serializer):
    """
    Validates the body of `POST .../data-elements/`.

    `is_nullable` has no default and allows null, so the service can tell "the caller did
    not say" from "the caller said true". See `services.data_elements.create_data_element`.
    """

    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    data_type = serializers.ChoiceField(choices=DataType.choices)
    max_length = serializers.IntegerField(
        required=False, allow_null=True, default=None, min_value=1
    )
    is_nullable = serializers.BooleanField(required=False, allow_null=True, default=None)
    is_primary_key = serializers.BooleanField(required=False, default=False)
    is_pii = serializers.BooleanField(required=False, default=False)


class DataElementBulkCreateInputSerializer(serializers.Serializer):
    """Validates the body of `POST .../data-elements/actions/bulk-create/`."""

    data_elements = DataElementCreateInputSerializer(
        many=True,
        allow_empty=False,
        max_length=MAX_BULK_CREATE_SIZE,
    )


class DataElementUpdateInputSerializer(serializers.Serializer):
    """
    Validates the body of `PATCH .../data-elements/{data_element_uuid}/`.

    `dataset_uuid` is intentionally absent: a data element cannot be reassigned to a
    different dataset. As with the dataset update serializer, no field has a default.
    """

    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    data_type = serializers.ChoiceField(choices=DataType.choices, required=False)
    max_length = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    is_nullable = serializers.BooleanField(required=False)
    is_primary_key = serializers.BooleanField(required=False)
    is_pii = serializers.BooleanField(required=False)

    def validate(self, attrs: dict) -> dict:
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


def data_elements_for_serialization(queryset: QuerySet[DataElement]) -> QuerySet[DataElement]:
    """
    Apply the joins `DataElementSerializer` needs. Call this *before* paginating.

    `dataset_uuid` is read through the `dataset` relation, so without `select_related` this
    is an N+1: one extra query per element on the page. The join lives here, next to the
    serializer field that needs it, rather than in the selector -- callers that only count
    or filter elements should not pay for a join they never read.

    It is a separate function from `serialize_data_elements` because pagination slices the
    queryset into a plain list, and a `select_related` applied after that point would
    silently do nothing. The view therefore joins, then paginates, then serializes.
    """
    return queryset.select_related("dataset")


def serialize_data_elements(
    data_elements: QuerySet[DataElement] | list[DataElement],
) -> DataElementSerializer:
    """Serialize data elements for a list response."""
    return DataElementSerializer(data_elements, many=True)


def serialize_data_element(data_element: DataElement) -> DataElementSerializer:
    """
    Serialize a single data element.

    No join is needed here: every caller reaches this with an instance whose `dataset` is
    already populated -- the service was handed the dataset object to create it with, and
    the detail selector looks the element up by dataset.
    """
    return DataElementSerializer(data_element)
