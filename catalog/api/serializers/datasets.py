"""
Dataset serializers.

These are plain `Serializer`s, not `ModelSerializer`s. A `ModelSerializer` derives the API
contract from the model, which means adding a column to the model silently changes what
the API returns, and `__all__` eventually publishes something nobody meant to publish.
Spelling the fields out makes the contract a decision rather than a side effect, and it is
visible in review when it changes.

Identifier naming is consistent across the API: a resource's own primary key is
`<model_name>_uuid`, and a reference to another resource is `<resource>_uuid`.
"""

from django.db.models import Prefetch, QuerySet, prefetch_related_objects
from django.db.models.functions import Lower
from rest_framework import serializers

from api.v2.core.serializers import inline_serializer
from catalog.models import DataElement, Dataset, DatasetLifecycleStatus, DataType


class DatasetSerializer(serializers.Serializer):
    """
    The flat representation of a dataset, used for list responses.

    Deliberately does not embed data elements. A list of twenty datasets would otherwise
    carry a few hundred nested objects that the caller almost certainly does not render;
    `data_element_count` gives the one thing a list view actually needs, and the elements
    themselves have their own endpoint.
    """

    dataset_uuid = serializers.UUIDField(source="uuid", read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    owner = serializers.CharField(read_only=True)
    lifecycle_status = serializers.ChoiceField(
        choices=DatasetLifecycleStatus.choices,
        read_only=True,
    )
    retention_period_days = serializers.IntegerField(read_only=True, allow_null=True)
    data_element_count = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)


class DatasetDetailSerializer(DatasetSerializer):
    """
    A dataset together with its data elements -- the one nested response in this API.

    Responses are capped at one level of nesting, and this sits exactly at that cap. It
    earns the nesting because "show me this entity's structure" is the single question
    the detail endpoint exists to answer, and answering it in two round trips would make
    every consumer write the same two-request dance.

    The nested shape is a summary rather than the full data element representation: inside
    its parent, an element's `dataset_uuid` is noise, and its audit timestamps are not what
    the reader came for. Both are available from the data element endpoints.
    """

    data_elements = inline_serializer(
        # This name becomes the OpenAPI component, and therefore the generated client type.
        name="DatasetDetailDataElementSerializer",
        many=True,
        read_only=True,
        fields={
            "data_element_uuid": serializers.UUIDField(source="uuid", read_only=True),
            "name": serializers.CharField(read_only=True),
            "description": serializers.CharField(read_only=True),
            "data_type": serializers.ChoiceField(choices=DataType.choices, read_only=True),
            "max_length": serializers.IntegerField(read_only=True, allow_null=True),
            "is_nullable": serializers.BooleanField(read_only=True),
            "is_primary_key": serializers.BooleanField(read_only=True),
            "is_pii": serializers.BooleanField(read_only=True),
        },
    )


class DatasetCreateInputSerializer(serializers.Serializer):
    """Validates the body of `POST /v2/catalog/datasets/`."""

    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    owner = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    lifecycle_status = serializers.ChoiceField(
        choices=DatasetLifecycleStatus.choices,
        required=False,
        default=DatasetLifecycleStatus.DRAFT,
    )
    # `min_value=1` mirrors the `dataset_retention_period_positive` check constraint. The
    # constraint is the guarantee; this is here so the caller gets a field-level error
    # instead of a generic one.
    retention_period_days = serializers.IntegerField(
        required=False,
        allow_null=True,
        default=None,
        min_value=1,
    )


class DatasetUpdateInputSerializer(serializers.Serializer):
    """
    Validates the body of `PATCH /v2/catalog/datasets/{dataset_uuid}/`.

    No field declares a `default`. That is what makes PATCH mean PATCH: an absent key stays
    out of `validated_data`, so `model_update` leaves the column alone instead of resetting
    it to a default the caller never asked for.
    """

    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    owner = serializers.CharField(max_length=150, required=False, allow_blank=True)
    lifecycle_status = serializers.ChoiceField(
        choices=DatasetLifecycleStatus.choices,
        required=False,
    )
    retention_period_days = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    def validate(self, attrs: dict) -> dict:
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


def serialize_datasets(datasets: QuerySet[Dataset] | list[Dataset]) -> DatasetSerializer:
    """
    Serialize datasets for a list response.

    There is nothing to join for this shape -- `data_element_count` is annotated by
    `DatasetQuerySet.with_data_element_count()` in the selector, because the annotation has
    to be on the queryset before it is paginated. This function is still the single place
    every list response goes through, so the day the list grows a related field, the
    `select_related` for it goes here and every caller gets it at once.
    """
    return DatasetSerializer(datasets, many=True)


def serialize_dataset(dataset: Dataset) -> DatasetSerializer:
    """Serialize a single dataset in its flat form (used by create and update responses)."""
    return DatasetSerializer(dataset)


def serialize_dataset_detail(dataset: Dataset) -> DatasetDetailSerializer:
    """
    Serialize a dataset together with its data elements.

    `prefetch_related_objects` fills the prefetch cache on the instance we already have,
    which costs one extra query for the whole collection. Serializing without it would walk
    `dataset.data_elements.all()` lazily and cost one query per access pattern instead --
    the classic N+1 that only shows up once a dataset has real fields in it. There is a
    test asserting the query count so this cannot silently regress.

    Ordering the prefetch is not cosmetic: an unordered nested list is free to come back in
    a different order on every request, which makes the response impossible to diff.
    """
    prefetch_related_objects(
        [dataset],
        Prefetch(
            "data_elements",
            queryset=DataElement.objects.order_by(Lower("name"), "pk"),
        ),
    )
    return DatasetDetailSerializer(dataset)
