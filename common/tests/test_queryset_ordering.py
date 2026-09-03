"""Tests for the declarative ordering service."""

import pytest

from catalog.models import Dataset, DatasetLifecycleStatus
from catalog.tests.factories import DatasetFactory
from common.exceptions import ValidationError
from common.models import queryset_ordering as ordering

pytestmark = pytest.mark.django_db


class DatasetOrdering(ordering.OrderingService):
    name = ordering.StringField()
    owner = ordering.StringField()
    retention_period_days = ordering.NumberField()
    created_at = ordering.DateTimeField()

    _defaults = ("-created_at",)


def names(queryset) -> list[str]:
    return [dataset.name for dataset in queryset]


class TestOrderQueryset:
    def test_applies_the_defaults_when_no_ordering_is_given(self):
        first = DatasetFactory(name="First")
        second = DatasetFactory(name="Second")

        result = DatasetOrdering.order_queryset(Dataset.objects.all(), [])

        assert names(result) == [second.name, first.name]

    def test_applies_the_defaults_for_none(self):
        DatasetFactory(name="Only")

        assert names(DatasetOrdering.order_queryset(Dataset.objects.all(), None)) == ["Only"]

    def test_orders_ascending_by_default(self):
        DatasetFactory(name="Beta")
        DatasetFactory(name="Alpha")

        result = DatasetOrdering.order_queryset(Dataset.objects.all(), ["name"])

        assert names(result) == ["Alpha", "Beta"]

    def test_a_leading_minus_orders_descending(self):
        DatasetFactory(name="Alpha")
        DatasetFactory(name="Beta")

        result = DatasetOrdering.order_queryset(Dataset.objects.all(), ["-name"])

        assert names(result) == ["Beta", "Alpha"]

    def test_string_ordering_is_case_insensitive(self):
        """A plain column sort would put every capital before every lowercase letter."""
        DatasetFactory(name="apple")
        DatasetFactory(name="Banana")
        DatasetFactory(name="cherry")

        result = DatasetOrdering.order_queryset(Dataset.objects.all(), ["name"])

        assert names(result) == ["apple", "Banana", "cherry"]

    def test_orders_by_several_fields_in_the_order_given(self):
        DatasetFactory(name="B", owner="alpha")
        DatasetFactory(name="C", owner="beta")
        DatasetFactory(name="A", owner="alpha")

        result = DatasetOrdering.order_queryset(Dataset.objects.all(), ["owner", "name"])

        assert [(d.owner, d.name) for d in result] == [
            ("alpha", "A"),
            ("alpha", "B"),
            ("beta", "C"),
        ]

    def test_nulls_sort_last_in_both_directions(self):
        DatasetFactory(name="With retention", retention_period_days=30)
        DatasetFactory(name="Without retention", retention_period_days=None)

        ascending = DatasetOrdering.order_queryset(Dataset.objects.all(), ["retention_period_days"])
        descending = DatasetOrdering.order_queryset(
            Dataset.objects.all(), ["-retention_period_days"]
        )

        assert names(ascending)[-1] == "Without retention"
        assert names(descending)[-1] == "Without retention"

    def test_repeating_a_field_keeps_the_first_direction(self):
        DatasetFactory(name="Alpha")
        DatasetFactory(name="Beta")

        result = DatasetOrdering.order_queryset(Dataset.objects.all(), ["-name", "name"])

        assert names(result) == ["Beta", "Alpha"]

    def test_blank_tokens_are_ignored(self):
        DatasetFactory(name="Alpha")

        result = DatasetOrdering.order_queryset(Dataset.objects.all(), ["", "  ", "name"])

        assert names(result) == ["Alpha"]

    def test_an_unknown_field_is_rejected_with_the_allowed_list(self):
        """Silently ignoring it would hand the client a plausible-looking wrong answer."""
        with pytest.raises(ValidationError) as error:
            DatasetOrdering.order_queryset(Dataset.objects.all(), ["password"])

        assert "password" in str(error.value)
        assert error.value.extra["ordering"]["allowed"] == [
            "created_at",
            "name",
            "owner",
            "retention_period_days",
        ]

    def test_a_field_of_the_model_that_was_not_declared_is_still_rejected(self):
        with pytest.raises(ValidationError):
            DatasetOrdering.order_queryset(Dataset.objects.all(), ["lifecycle_status"])

    def test_a_tiebreaker_makes_the_order_deterministic(self):
        """
        Without this, LIMIT/OFFSET paging over a non-unique sort key can repeat or skip rows
        between pages, because the database is free to break ties differently each time.
        """
        for index in range(5):
            DatasetFactory(name=f"Dataset {index}", owner="same-team")

        first_pass = list(
            DatasetOrdering.order_queryset(Dataset.objects.all(), ["owner"]).values_list(
                "pk", flat=True
            )
        )
        second_pass = list(
            DatasetOrdering.order_queryset(Dataset.objects.all(), ["owner"]).values_list(
                "pk", flat=True
            )
        )

        assert first_pass == second_pass
        assert first_pass == sorted(first_pass, reverse=True)


class TestOrderingServiceDeclaration:
    def test_allowed_fields_lists_the_declared_fields(self):
        assert DatasetOrdering.allowed_fields() == [
            "created_at",
            "name",
            "owner",
            "retention_period_days",
        ]

    def test_a_typo_in_defaults_fails_at_import_time(self):
        """Better a hard failure when the module loads than a 400 in production."""
        with pytest.raises(ValueError, match="unknown ordering field"):

            class Broken(ordering.OrderingService):
                name = ordering.StringField()

                _defaults = ("-craeted_at",)

    def test_source_maps_a_public_name_onto_another_column(self):
        class Aliased(ordering.OrderingService):
            status = ordering.StringField(source="lifecycle_status")

            _defaults = ("status",)

        DatasetFactory(name="B", lifecycle_status=DatasetLifecycleStatus.ACTIVE)
        DatasetFactory(name="A", lifecycle_status=DatasetLifecycleStatus.DRAFT)

        result = Aliased.order_queryset(Dataset.objects.all(), ["status"])

        assert names(result) == ["B", "A"]

    def test_a_subclass_inherits_and_can_override_fields(self):
        class Extended(DatasetOrdering):
            lifecycle_status = ordering.StringField()

        assert "name" in Extended.allowed_fields()
        assert "lifecycle_status" in Extended.allowed_fields()
