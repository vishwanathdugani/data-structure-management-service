"""Tests for the dataset selectors: scoping, filtering and ordering."""

import pytest

from catalog.models import DatasetLifecycleStatus
from catalog.selectors import get_dataset, get_datasets
from catalog.tests.factories import DataElementFactory, DatasetFactory
from common.exceptions import NotFoundError, ValidationError

pytestmark = pytest.mark.django_db


def names(queryset) -> list[str]:
    return [dataset.name for dataset in queryset]


class TestGetDatasets:
    def test_returns_every_dataset_by_default(self):
        DatasetFactory.create_batch(3)

        assert get_datasets().count() == 3

    def test_annotates_the_data_element_count(self):
        dataset = DatasetFactory()
        DataElementFactory.create_batch(2, dataset=dataset)

        assert get_datasets().first().data_element_count == 2

    def test_defaults_to_newest_first(self):
        older = DatasetFactory(name="Older")
        newer = DatasetFactory(name="Newer")

        assert names(get_datasets()) == [newer.name, older.name]

    def test_orders_by_the_requested_field(self):
        DatasetFactory(name="Beta")
        DatasetFactory(name="Alpha")

        assert names(get_datasets(ordering=["name"])) == ["Alpha", "Beta"]

    def test_rejects_an_unknown_ordering_field(self):
        with pytest.raises(ValidationError):
            get_datasets(ordering=["not_a_field"])


class TestGetDatasetsFiltering:
    def test_filters_by_partial_name_case_insensitively(self):
        DatasetFactory(name="Customer")
        DatasetFactory(name="Order")

        assert names(get_datasets(filters={"name": "cust"})) == ["Customer"]

    def test_filters_by_owner_exactly(self):
        DatasetFactory(name="Customer", owner="growth-team")
        DatasetFactory(name="Order", owner="commerce-team")

        assert names(get_datasets(filters={"owner": "GROWTH-TEAM"})) == ["Customer"]

    def test_filters_by_lifecycle_status(self):
        DatasetFactory(name="Active", lifecycle_status=DatasetLifecycleStatus.ACTIVE)
        DatasetFactory(name="Draft", lifecycle_status=DatasetLifecycleStatus.DRAFT)

        result = get_datasets(filters={"lifecycle_status": DatasetLifecycleStatus.ACTIVE})

        assert names(result) == ["Active"]

    def test_filters_by_several_lifecycle_statuses(self):
        DatasetFactory(name="Active", lifecycle_status=DatasetLifecycleStatus.ACTIVE)
        DatasetFactory(name="Draft", lifecycle_status=DatasetLifecycleStatus.DRAFT)
        DatasetFactory(name="Archived", lifecycle_status=DatasetLifecycleStatus.ARCHIVED)

        result = get_datasets(filters={"lifecycle_status__in": "active,draft"})

        assert sorted(names(result)) == ["Active", "Draft"]

    def test_filters_on_the_presence_of_a_retention_period(self):
        DatasetFactory(name="With", retention_period_days=30)
        DatasetFactory(name="Without", retention_period_days=None)

        assert names(get_datasets(filters={"has_retention_period": "true"})) == ["With"]
        assert names(get_datasets(filters={"has_retention_period": "false"})) == ["Without"]

    def test_filters_on_the_presence_of_pii(self):
        with_pii = DatasetFactory(name="With PII", retention_period_days=30)
        DataElementFactory(dataset=with_pii, is_pii=True)
        without_pii = DatasetFactory(name="Without PII")
        DataElementFactory(dataset=without_pii, is_pii=False)

        assert names(get_datasets(filters={"contains_pii": "true"})) == ["With PII"]
        assert names(get_datasets(filters={"contains_pii": "false"})) == ["Without PII"]

    def test_the_pii_filter_does_not_duplicate_rows(self):
        """A join-based implementation would return this dataset three times."""
        dataset = DatasetFactory(retention_period_days=30)
        DataElementFactory.create_batch(3, dataset=dataset, is_pii=True)

        assert get_datasets(filters={"contains_pii": "true"}).count() == 1

    def test_searches_across_name_description_and_owner(self):
        DatasetFactory(name="Customer", description="", owner="")
        DatasetFactory(name="Order", description="Placed by a customer.", owner="")
        DatasetFactory(name="Invoice", description="", owner="customer-team")
        DatasetFactory(name="Product", description="", owner="")

        assert sorted(names(get_datasets(filters={"search": "customer"}))) == [
            "Customer",
            "Invoice",
            "Order",
        ]

    def test_combines_filters(self):
        DatasetFactory(
            name="Customer",
            owner="growth-team",
            lifecycle_status=DatasetLifecycleStatus.ACTIVE,
        )
        DatasetFactory(
            name="Customer archive",
            owner="growth-team",
            lifecycle_status=DatasetLifecycleStatus.ARCHIVED,
        )

        result = get_datasets(
            filters={"search": "customer", "lifecycle_status": DatasetLifecycleStatus.ACTIVE}
        )

        assert names(result) == ["Customer"]

    def test_rejects_an_invalid_filter_value(self):
        with pytest.raises(ValidationError) as error:
            get_datasets(filters={"lifecycle_status": "banana"})

        assert "lifecycle_status" in error.value.extra["fields"]

    def test_ignores_query_parameters_it_does_not_declare(self):
        """`limit`, `offset` and `ordering` ride along in the same dict."""
        DatasetFactory.create_batch(2)

        assert get_datasets(filters={"limit": "10", "ordering": "name"}).count() == 2


class TestGetDataset:
    def test_returns_the_dataset(self):
        dataset = DatasetFactory()

        assert get_dataset(dataset_uuid=dataset.uuid) == dataset

    def test_annotates_the_data_element_count(self):
        dataset = DatasetFactory()
        DataElementFactory.create_batch(2, dataset=dataset)

        assert get_dataset(dataset_uuid=dataset.uuid).data_element_count == 2

    def test_raises_for_an_unknown_uuid(self):
        with pytest.raises(NotFoundError):
            get_dataset(dataset_uuid="00000000-0000-0000-0000-000000000000")
