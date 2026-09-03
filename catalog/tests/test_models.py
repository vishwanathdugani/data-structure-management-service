"""
Tests for the database constraints.

Every test here writes through `objects.create()` or `queryset.update()`, which skip
`full_clean()` entirely. That is deliberate. The services already give friendly validation
errors, and testing them through the services would only prove that the Python checks work.
These tests prove the guarantee underneath: that the *database* rejects bad data, so the
catalog stays correct even when something writes to it that never touched our service layer
-- a migration, a shell session, a bulk import, a future second application.
"""

import pytest
from django.db import IntegrityError, transaction

from catalog.models import DataElement, Dataset, DatasetLifecycleStatus, DataType
from catalog.tests.factories import DataElementFactory, DatasetFactory

pytestmark = pytest.mark.django_db


class TestDatasetConstraints:
    def test_name_is_unique_case_insensitively(self):
        DatasetFactory(name="Customer")

        with pytest.raises(IntegrityError), transaction.atomic():
            Dataset.objects.create(name="cUsToMeR")

    def test_name_cannot_be_blank(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            Dataset.objects.create(name="")

    def test_lifecycle_status_is_restricted_to_known_values(self):
        dataset = DatasetFactory()

        # `choices` is only enforced by validation, which `.update()` bypasses entirely.
        # The check constraint is what actually protects the column.
        with pytest.raises(IntegrityError), transaction.atomic():
            Dataset.objects.filter(pk=dataset.pk).update(lifecycle_status="banana")

    def test_retention_period_cannot_be_zero(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            Dataset.objects.create(name="Zero retention", retention_period_days=0)

    def test_retention_period_may_be_null(self):
        dataset = Dataset.objects.create(name="No retention", retention_period_days=None)

        assert dataset.retention_period_days is None

    def test_uuid_is_generated_and_unique(self):
        first, second = DatasetFactory(), DatasetFactory()

        assert first.uuid != second.uuid


class TestDataElementConstraints:
    def test_name_is_unique_within_a_dataset_case_insensitively(self):
        dataset = DatasetFactory()
        DataElementFactory(dataset=dataset, name="email")

        with pytest.raises(IntegrityError), transaction.atomic():
            DataElement.objects.create(dataset=dataset, name="EMAIL", data_type=DataType.STRING)

    def test_the_same_name_is_allowed_in_a_different_dataset(self):
        DataElementFactory(dataset=DatasetFactory(), name="email")
        other = DataElementFactory(dataset=DatasetFactory(), name="email")

        assert other.pk is not None

    def test_a_dataset_can_have_at_most_one_primary_key(self):
        dataset = DatasetFactory()
        DataElementFactory(dataset=dataset, is_primary_key=True, is_nullable=False)

        with pytest.raises(IntegrityError), transaction.atomic():
            DataElement.objects.create(
                dataset=dataset,
                name="other_id",
                data_type=DataType.UUID,
                is_primary_key=True,
                is_nullable=False,
            )

    def test_two_datasets_can_each_have_their_own_primary_key(self):
        """The uniqueness is partial *and* scoped -- it must not become a global one."""
        DataElementFactory(dataset=DatasetFactory(), is_primary_key=True, is_nullable=False)
        second = DataElementFactory(
            dataset=DatasetFactory(), is_primary_key=True, is_nullable=False
        )

        assert second.pk is not None

    def test_a_primary_key_cannot_be_nullable(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            DataElement.objects.create(
                dataset=DatasetFactory(),
                name="id",
                data_type=DataType.UUID,
                is_primary_key=True,
                is_nullable=True,
            )

    def test_max_length_is_rejected_on_a_non_string_element(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            DataElement.objects.create(
                dataset=DatasetFactory(),
                name="amount",
                data_type=DataType.DECIMAL,
                max_length=10,
            )

    def test_max_length_must_be_positive_on_a_string_element(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            DataElement.objects.create(
                dataset=DatasetFactory(),
                name="code",
                data_type=DataType.STRING,
                max_length=0,
            )

    def test_data_type_is_restricted_to_known_values(self):
        element = DataElementFactory()

        with pytest.raises(IntegrityError), transaction.atomic():
            DataElement.objects.filter(pk=element.pk).update(data_type="blob")

    def test_name_cannot_be_blank(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            DataElement.objects.create(dataset=DatasetFactory(), name="", data_type=DataType.STRING)

    def test_elements_are_deleted_with_their_dataset(self):
        """A data element has no meaning without its dataset, hence CASCADE."""
        dataset = DatasetFactory()
        DataElementFactory.create_batch(3, dataset=dataset)

        dataset.delete()

        assert DataElement.objects.count() == 0


class TestDatasetQuerySet:
    def test_with_data_element_count_annotates_each_dataset(self):
        empty = DatasetFactory()
        populated = DatasetFactory()
        DataElementFactory.create_batch(2, dataset=populated)

        counts = {
            dataset.uuid: dataset.data_element_count
            for dataset in Dataset.objects.with_data_element_count()
        }

        assert counts[empty.uuid] == 0
        assert counts[populated.uuid] == 2

    def test_editable_excludes_archived_datasets(self):
        DatasetFactory(lifecycle_status=DatasetLifecycleStatus.ARCHIVED)
        active = DatasetFactory(lifecycle_status=DatasetLifecycleStatus.ACTIVE)

        assert list(Dataset.objects.editable()) == [active]

    def test_active_returns_only_active_datasets(self):
        active = DatasetFactory(lifecycle_status=DatasetLifecycleStatus.ACTIVE)
        DatasetFactory(lifecycle_status=DatasetLifecycleStatus.DRAFT)

        assert list(Dataset.objects.active()) == [active]

    def test_containing_pii_returns_each_dataset_once(self):
        dataset = DatasetFactory(retention_period_days=30)
        DataElementFactory.create_batch(2, dataset=dataset, is_pii=True)
        DatasetFactory()

        assert list(Dataset.objects.containing_pii()) == [dataset]


class TestDataElementQuerySet:
    def test_for_dataset_scopes_to_one_dataset(self):
        dataset = DatasetFactory()
        element = DataElementFactory(dataset=dataset)
        DataElementFactory()

        assert list(DataElement.objects.for_dataset(dataset)) == [element]

    def test_pii_filters_to_personal_data(self):
        pii = DataElementFactory(is_pii=True)
        DataElementFactory(is_pii=False)

        assert list(DataElement.objects.pii()) == [pii]

    def test_of_type_filters_by_data_type(self):
        date_element = DataElementFactory(data_type=DataType.DATE)
        DataElementFactory(data_type=DataType.STRING)

        assert list(DataElement.objects.of_type(DataType.DATE)) == [date_element]


class TestModelRepresentations:
    def test_dataset_str_is_its_name(self):
        assert str(DatasetFactory(name="Customer")) == "Customer"

    def test_data_element_str_is_qualified_by_its_dataset(self):
        dataset = DatasetFactory(name="Customer")

        assert str(DataElementFactory(dataset=dataset, name="email")) == "Customer.email"

    def test_is_archived_reflects_lifecycle_status(self):
        assert DatasetFactory(lifecycle_status=DatasetLifecycleStatus.ARCHIVED).is_archived
        assert not DatasetFactory(lifecycle_status=DatasetLifecycleStatus.ACTIVE).is_archived
