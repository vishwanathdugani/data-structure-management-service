"""Tests for the data element selectors."""

import pytest

from catalog.models import DataType
from catalog.selectors import get_data_element, get_data_elements
from catalog.tests.factories import DataElementFactory, DatasetFactory
from common.exceptions import NotFoundError, ValidationError

pytestmark = pytest.mark.django_db


def names(queryset) -> list[str]:
    return [element.name for element in queryset]


class TestGetDataElements:
    def test_is_scoped_to_the_given_dataset(self):
        dataset = DatasetFactory()
        DataElementFactory(dataset=dataset, name="email")
        DataElementFactory(dataset=DatasetFactory(), name="other")

        assert names(get_data_elements(dataset=dataset)) == ["email"]

    def test_defaults_to_alphabetical_order(self):
        dataset = DatasetFactory()
        DataElementFactory(dataset=dataset, name="zip_code")
        DataElementFactory(dataset=dataset, name="Address")

        assert names(get_data_elements(dataset=dataset)) == ["Address", "zip_code"]

    def test_orders_by_the_requested_fields(self):
        dataset = DatasetFactory(retention_period_days=30)
        DataElementFactory(dataset=dataset, name="a_public", is_pii=False)
        DataElementFactory(dataset=dataset, name="b_personal", is_pii=True)

        result = get_data_elements(dataset=dataset, ordering=["-is_pii", "name"])

        assert names(result) == ["b_personal", "a_public"]

    def test_filters_by_pii(self):
        dataset = DatasetFactory(retention_period_days=30)
        DataElementFactory(dataset=dataset, name="email", is_pii=True)
        DataElementFactory(dataset=dataset, name="created_at", is_pii=False)

        assert names(get_data_elements(dataset=dataset, filters={"is_pii": "true"})) == ["email"]

    def test_filters_by_data_type(self):
        dataset = DatasetFactory()
        DataElementFactory(dataset=dataset, name="email", data_type=DataType.STRING)
        DataElementFactory(dataset=dataset, name="born_on", data_type=DataType.DATE)

        result = get_data_elements(dataset=dataset, filters={"data_type": DataType.DATE})

        assert names(result) == ["born_on"]

    def test_filters_by_several_data_types(self):
        dataset = DatasetFactory()
        DataElementFactory(dataset=dataset, name="email", data_type=DataType.STRING)
        DataElementFactory(dataset=dataset, name="born_on", data_type=DataType.DATE)
        DataElementFactory(dataset=dataset, name="active", data_type=DataType.BOOLEAN)

        result = get_data_elements(dataset=dataset, filters={"data_type__in": "string,date"})

        assert sorted(names(result)) == ["born_on", "email"]

    def test_filters_by_primary_key(self):
        dataset = DatasetFactory()
        DataElementFactory(dataset=dataset, name="id", is_primary_key=True, is_nullable=False)
        DataElementFactory(dataset=dataset, name="email")

        result = get_data_elements(dataset=dataset, filters={"is_primary_key": "true"})

        assert names(result) == ["id"]

    def test_searches_name_and_description(self):
        dataset = DatasetFactory()
        DataElementFactory(dataset=dataset, name="email", description="")
        DataElementFactory(dataset=dataset, name="contact", description="An email address.")
        DataElementFactory(dataset=dataset, name="created_at", description="")

        assert sorted(names(get_data_elements(dataset=dataset, filters={"search": "email"}))) == [
            "contact",
            "email",
        ]

    def test_rejects_an_invalid_filter_value(self):
        with pytest.raises(ValidationError):
            get_data_elements(dataset=DatasetFactory(), filters={"data_type": "binary"})

    def test_rejects_an_unknown_ordering_field(self):
        with pytest.raises(ValidationError):
            get_data_elements(dataset=DatasetFactory(), ordering=["dataset"])


class TestGetDataElement:
    def test_returns_the_element(self):
        element = DataElementFactory()

        result = get_data_element(dataset=element.dataset, data_element_uuid=element.uuid)

        assert result == element

    def test_an_element_of_another_dataset_is_not_found(self):
        """
        The dataset is part of the lookup, not a check afterwards. Addressing a real element
        under the wrong parent must not confirm that it exists.
        """
        element = DataElementFactory()

        with pytest.raises(NotFoundError):
            get_data_element(dataset=DatasetFactory(), data_element_uuid=element.uuid)

    def test_raises_for_an_unknown_uuid(self):
        with pytest.raises(NotFoundError):
            get_data_element(
                dataset=DatasetFactory(),
                data_element_uuid="00000000-0000-0000-0000-000000000000",
            )
