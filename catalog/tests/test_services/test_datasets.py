"""Tests for the dataset services."""

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError

from catalog.models import Dataset, DatasetLifecycleStatus
from catalog.services import create_dataset, update_dataset
from catalog.tests.factories import DataElementFactory, DatasetFactory
from common.exceptions import ConflictError, ValidationError

pytestmark = pytest.mark.django_db


class TestCreateDataset:
    def test_creates_a_dataset_with_defaults(self):
        dataset = create_dataset(name="Customer")

        assert dataset.pk is not None
        assert dataset.lifecycle_status == DatasetLifecycleStatus.DRAFT
        assert dataset.retention_period_days is None
        assert dataset.description == ""

    def test_stores_every_field_it_was_given(self):
        dataset = create_dataset(
            name="Customer",
            description="Someone who buys from us.",
            owner="growth-team",
            lifecycle_status=DatasetLifecycleStatus.ACTIVE,
            retention_period_days=730,
        )

        assert dataset.description == "Someone who buys from us."
        assert dataset.owner == "growth-team"
        assert dataset.lifecycle_status == DatasetLifecycleStatus.ACTIVE
        assert dataset.retention_period_days == 730

    def test_strips_surrounding_whitespace_from_the_name(self):
        assert create_dataset(name="  Customer  ").name == "Customer"

    def test_rejects_a_name_that_already_exists_in_another_case(self):
        create_dataset(name="Customer")

        with pytest.raises(DjangoValidationError):
            create_dataset(name="customer")

        assert Dataset.objects.count() == 1

    def test_rejects_a_blank_name(self):
        with pytest.raises(DjangoValidationError):
            create_dataset(name="   ")

    def test_rejects_creating_a_dataset_that_is_already_retired(self):
        """You cannot start a dataset's life at the end of it."""
        for status in (DatasetLifecycleStatus.DEPRECATED, DatasetLifecycleStatus.ARCHIVED):
            with pytest.raises(ValidationError) as error:
                create_dataset(name=f"Dataset {status}", lifecycle_status=status)

            assert error.value.extra["lifecycle_status"]["allowed"] == ["active", "draft"]

    def test_rejects_a_non_positive_retention_period(self):
        with pytest.raises(DjangoValidationError):
            create_dataset(name="Customer", retention_period_days=0)


class TestUpdateDataset:
    def test_updates_only_the_fields_that_were_sent(self):
        dataset = DatasetFactory(name="Customer", owner="growth-team", description="Original.")

        updated = update_dataset(dataset=dataset, name="Client")

        assert updated.name == "Client"
        assert updated.owner == "growth-team"
        assert updated.description == "Original."

    def test_ignores_fields_that_are_not_updatable(self):
        """`created_at` is the service's to set. A caller cannot rewrite history."""
        dataset = DatasetFactory()
        original_created_at = dataset.created_at

        updated = update_dataset(dataset=dataset, created_at="2000-01-01T00:00:00Z")

        assert updated.created_at == original_created_at

    def test_rejects_a_duplicate_name(self):
        DatasetFactory(name="Customer")
        other = DatasetFactory(name="Order")

        with pytest.raises(DjangoValidationError):
            update_dataset(dataset=other, name="Customer")


class TestDatasetLifecycleRules:
    @pytest.mark.parametrize(
        ("current", "new"),
        [
            (DatasetLifecycleStatus.DRAFT, DatasetLifecycleStatus.ACTIVE),
            (DatasetLifecycleStatus.DRAFT, DatasetLifecycleStatus.ARCHIVED),
            (DatasetLifecycleStatus.ACTIVE, DatasetLifecycleStatus.DEPRECATED),
            (DatasetLifecycleStatus.ACTIVE, DatasetLifecycleStatus.ARCHIVED),
            (DatasetLifecycleStatus.DEPRECATED, DatasetLifecycleStatus.ACTIVE),
            (DatasetLifecycleStatus.DEPRECATED, DatasetLifecycleStatus.ARCHIVED),
        ],
    )
    def test_allows_a_valid_transition(self, current, new):
        dataset = DatasetFactory(lifecycle_status=current)

        assert update_dataset(dataset=dataset, lifecycle_status=new).lifecycle_status == new

    @pytest.mark.parametrize(
        ("current", "new"),
        [
            (DatasetLifecycleStatus.DRAFT, DatasetLifecycleStatus.DEPRECATED),
            (DatasetLifecycleStatus.ACTIVE, DatasetLifecycleStatus.DRAFT),
            (DatasetLifecycleStatus.DEPRECATED, DatasetLifecycleStatus.DRAFT),
        ],
    )
    def test_rejects_an_invalid_transition(self, current, new):
        dataset = DatasetFactory(lifecycle_status=current)

        with pytest.raises(ConflictError) as error:
            update_dataset(dataset=dataset, lifecycle_status=new)

        assert error.value.extra["lifecycle_status"]["current"] == current
        assert error.value.extra["lifecycle_status"]["requested"] == new

    def test_restating_the_current_status_is_a_no_op(self):
        dataset = DatasetFactory(lifecycle_status=DatasetLifecycleStatus.ACTIVE)

        updated = update_dataset(dataset=dataset, lifecycle_status=DatasetLifecycleStatus.ACTIVE)

        assert updated.lifecycle_status == DatasetLifecycleStatus.ACTIVE

    def test_an_archived_dataset_rejects_every_write(self):
        dataset = DatasetFactory(lifecycle_status=DatasetLifecycleStatus.ARCHIVED)

        with pytest.raises(ConflictError) as error:
            update_dataset(dataset=dataset, description="A harmless edit.")

        assert "archived" in str(error.value)

    def test_archiving_is_terminal(self):
        dataset = DatasetFactory(lifecycle_status=DatasetLifecycleStatus.ARCHIVED)

        with pytest.raises(ConflictError):
            update_dataset(dataset=dataset, lifecycle_status=DatasetLifecycleStatus.ACTIVE)


class TestRetentionAndPiiRules:
    def test_the_retention_period_cannot_be_removed_while_pii_exists(self):
        dataset = DatasetFactory(retention_period_days=365)
        DataElementFactory(dataset=dataset, name="email", is_pii=True)

        with pytest.raises(ConflictError) as error:
            update_dataset(dataset=dataset, retention_period_days=None)

        assert error.value.extra["pii_data_elements"] == ["email"]
        dataset.refresh_from_db()
        assert dataset.retention_period_days == 365

    def test_the_retention_period_can_be_removed_when_no_pii_exists(self):
        dataset = DatasetFactory(retention_period_days=365)
        DataElementFactory(dataset=dataset, is_pii=False)

        assert (
            update_dataset(dataset=dataset, retention_period_days=None).retention_period_days
            is None
        )

    def test_the_retention_period_can_be_shortened_while_pii_exists(self):
        """The rule is about removing the policy, not about changing it."""
        dataset = DatasetFactory(retention_period_days=365)
        DataElementFactory(dataset=dataset, is_pii=True)

        assert update_dataset(dataset=dataset, retention_period_days=30).retention_period_days == 30

    def test_not_mentioning_the_retention_period_is_not_removing_it(self):
        """`{"description": ...}` must not trip a rule about a field it never named."""
        dataset = DatasetFactory(retention_period_days=365)
        DataElementFactory(dataset=dataset, is_pii=True)

        updated = update_dataset(dataset=dataset, description="Updated.")

        assert updated.retention_period_days == 365
