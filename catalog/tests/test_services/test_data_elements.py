"""Tests for the data element services."""

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError

from catalog.models import DataElement, DatasetLifecycleStatus, DataType
from catalog.services import bulk_create_data_elements, create_data_element, update_data_element
from catalog.tests.factories import DataElementFactory, DatasetFactory
from common.exceptions import ConflictError, ValidationError

pytestmark = pytest.mark.django_db


class TestCreateDataElement:
    def test_creates_an_element(self):
        dataset = DatasetFactory()

        element = create_data_element(dataset=dataset, name="email", data_type=DataType.STRING)

        assert element.dataset == dataset
        assert element.name == "email"
        assert element.data_type == DataType.STRING

    def test_strips_surrounding_whitespace_from_the_name(self):
        element = create_data_element(
            dataset=DatasetFactory(), name="  email  ", data_type=DataType.STRING
        )

        assert element.name == "email"

    def test_defaults_to_nullable_for_an_ordinary_element(self):
        element = create_data_element(
            dataset=DatasetFactory(), name="email", data_type=DataType.STRING
        )

        assert element.is_nullable is True

    def test_a_primary_key_defaults_to_not_nullable(self):
        """An unspecified nullability is derived from the element's role."""
        element = create_data_element(
            dataset=DatasetFactory(),
            name="customer_id",
            data_type=DataType.UUID,
            is_primary_key=True,
        )

        assert element.is_nullable is False

    def test_an_explicitly_nullable_primary_key_is_rejected(self):
        """A default may be inferred; a contradiction the caller stated may not."""
        with pytest.raises(DjangoValidationError):
            create_data_element(
                dataset=DatasetFactory(),
                name="customer_id",
                data_type=DataType.UUID,
                is_primary_key=True,
                is_nullable=True,
            )

    def test_rejects_a_second_primary_key(self):
        dataset = DatasetFactory()
        create_data_element(
            dataset=dataset, name="id", data_type=DataType.UUID, is_primary_key=True
        )

        with pytest.raises(DjangoValidationError):
            create_data_element(
                dataset=dataset, name="other_id", data_type=DataType.UUID, is_primary_key=True
            )

    def test_rejects_a_duplicate_name_in_the_same_dataset(self):
        dataset = DatasetFactory()
        create_data_element(dataset=dataset, name="email", data_type=DataType.STRING)

        with pytest.raises(DjangoValidationError):
            create_data_element(dataset=dataset, name="EMAIL", data_type=DataType.STRING)

    def test_allows_the_same_name_in_another_dataset(self):
        create_data_element(dataset=DatasetFactory(), name="email", data_type=DataType.STRING)
        element = create_data_element(
            dataset=DatasetFactory(), name="email", data_type=DataType.STRING
        )

        assert element.pk is not None

    def test_rejects_max_length_on_a_non_string(self):
        with pytest.raises(DjangoValidationError):
            create_data_element(
                dataset=DatasetFactory(),
                name="amount",
                data_type=DataType.DECIMAL,
                max_length=10,
            )

    def test_rejects_an_unknown_data_type(self):
        with pytest.raises(DjangoValidationError):
            create_data_element(dataset=DatasetFactory(), name="blob", data_type="binary")


class TestDataElementPiiRule:
    def test_pii_requires_the_dataset_to_declare_a_retention_period(self):
        dataset = DatasetFactory(retention_period_days=None)

        with pytest.raises(ValidationError) as error:
            create_data_element(
                dataset=dataset, name="email", data_type=DataType.STRING, is_pii=True
            )

        assert error.value.extra["field"] == "retention_period_days"
        assert DataElement.objects.count() == 0

    def test_pii_is_allowed_once_a_retention_period_exists(self):
        dataset = DatasetFactory(retention_period_days=365)

        element = create_data_element(
            dataset=dataset, name="email", data_type=DataType.STRING, is_pii=True
        )

        assert element.is_pii is True

    def test_a_non_pii_element_needs_no_retention_period(self):
        element = create_data_element(
            dataset=DatasetFactory(retention_period_days=None),
            name="created_at",
            data_type=DataType.DATETIME,
        )

        assert element.pk is not None

    def test_flagging_an_existing_element_as_pii_is_subject_to_the_same_rule(self):
        """Otherwise the rule would be bypassable by creating first and flagging after."""
        dataset = DatasetFactory(retention_period_days=None)
        element = DataElementFactory(dataset=dataset, is_pii=False)

        with pytest.raises(ValidationError):
            update_data_element(data_element=element, is_pii=True)

        element.refresh_from_db()
        assert element.is_pii is False


class TestArchivedDatasetIsReadOnly:
    def test_no_element_can_be_added(self):
        dataset = DatasetFactory(lifecycle_status=DatasetLifecycleStatus.ARCHIVED)

        with pytest.raises(ConflictError):
            create_data_element(dataset=dataset, name="email", data_type=DataType.STRING)

    def test_no_element_can_be_updated(self):
        dataset = DatasetFactory(lifecycle_status=DatasetLifecycleStatus.ARCHIVED)
        element = DataElementFactory(dataset=dataset)

        with pytest.raises(ConflictError):
            update_data_element(data_element=element, description="A harmless edit.")

    def test_no_batch_can_be_created(self):
        dataset = DatasetFactory(lifecycle_status=DatasetLifecycleStatus.ARCHIVED)

        with pytest.raises(ConflictError):
            bulk_create_data_elements(
                dataset=dataset,
                data_elements=[{"name": "email", "data_type": DataType.STRING}],
            )


class TestUpdateDataElement:
    def test_updates_only_the_fields_that_were_sent(self):
        element = DataElementFactory(name="email", description="Original.")

        updated = update_data_element(data_element=element, description="Updated.")

        assert updated.name == "email"
        assert updated.description == "Updated."

    def test_an_element_cannot_be_moved_to_another_dataset(self):
        """`dataset` is not an updatable field, so the attempt is ignored, not honoured."""
        element = DataElementFactory()
        other_dataset = DatasetFactory()

        updated = update_data_element(data_element=element, dataset=other_dataset)

        assert updated.dataset != other_dataset

    def test_rejects_an_update_that_would_break_a_constraint(self):
        dataset = DatasetFactory()
        DataElementFactory(dataset=dataset, name="email")
        other = DataElementFactory(dataset=dataset, name="phone")

        with pytest.raises(DjangoValidationError):
            update_data_element(data_element=other, name="email")


class TestBulkCreateDataElements:
    def test_creates_every_element(self):
        dataset = DatasetFactory()

        created = bulk_create_data_elements(
            dataset=dataset,
            data_elements=[
                {"name": "id", "data_type": DataType.UUID, "is_primary_key": True},
                {"name": "email", "data_type": DataType.STRING, "max_length": 254},
                {"name": "created_at", "data_type": DataType.DATETIME},
            ],
        )

        assert len(created) == 3
        assert DataElement.objects.for_dataset(dataset).count() == 3

    def test_rolls_the_whole_batch_back_when_one_element_is_invalid(self):
        """A half-defined dataset is worse than a rejected request."""
        dataset = DatasetFactory()

        with pytest.raises(DjangoValidationError):
            bulk_create_data_elements(
                dataset=dataset,
                data_elements=[
                    {"name": "valid", "data_type": DataType.STRING},
                    {"name": "invalid", "data_type": DataType.DECIMAL, "max_length": 5},
                ],
            )

        assert DataElement.objects.for_dataset(dataset).count() == 0

    def test_reports_which_element_broke_a_business_rule(self):
        dataset = DatasetFactory(retention_period_days=None)

        with pytest.raises(ValidationError) as error:
            bulk_create_data_elements(
                dataset=dataset,
                data_elements=[
                    {"name": "id", "data_type": DataType.UUID},
                    {"name": "email", "data_type": DataType.STRING, "is_pii": True},
                ],
            )

        assert error.value.extra["index"] == 1
        assert error.value.extra["name"] == "email"

    def test_rejects_names_that_collide_within_the_request(self):
        dataset = DatasetFactory()

        with pytest.raises(ValidationError) as error:
            bulk_create_data_elements(
                dataset=dataset,
                data_elements=[
                    {"name": "email", "data_type": DataType.STRING},
                    {"name": "EMAIL", "data_type": DataType.STRING},
                ],
            )

        assert error.value.extra == {"index": 1, "conflicts_with_index": 0}
        assert DataElement.objects.for_dataset(dataset).count() == 0

    def test_rejects_a_second_primary_key_within_the_request(self):
        dataset = DatasetFactory()

        with pytest.raises(DjangoValidationError):
            bulk_create_data_elements(
                dataset=dataset,
                data_elements=[
                    {"name": "id", "data_type": DataType.UUID, "is_primary_key": True},
                    {"name": "alt_id", "data_type": DataType.UUID, "is_primary_key": True},
                ],
            )

        assert DataElement.objects.for_dataset(dataset).count() == 0
