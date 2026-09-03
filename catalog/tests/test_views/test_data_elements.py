"""End-to-end tests for the data element endpoints."""

import pytest
from django.urls import reverse

from catalog.models import DataElement, Dataset, DatasetLifecycleStatus, DataType
from catalog.tests.factories import DataElementFactory, DatasetFactory

pytestmark = pytest.mark.django_db


def list_url(dataset: Dataset) -> str:
    return reverse("v2:catalog:data-elements", kwargs={"dataset_uuid": dataset.uuid})


def detail_url(element: DataElement) -> str:
    return reverse(
        "v2:catalog:data-element-detail",
        kwargs={"dataset_uuid": element.dataset.uuid, "data_element_uuid": element.uuid},
    )


def bulk_create_url(dataset: Dataset) -> str:
    return reverse("v2:catalog:data-elements-bulk-create", kwargs={"dataset_uuid": dataset.uuid})


class TestListDataElements:
    def test_returns_the_elements_of_the_dataset(self, api_client):
        dataset = DatasetFactory()
        DataElementFactory(dataset=dataset, name="email")
        DataElementFactory(dataset=DatasetFactory(), name="elsewhere")

        response = api_client.get(list_url(dataset))

        assert response.status_code == 200
        assert [e["name"] for e in response.data["results"]] == ["email"]

    def test_returns_the_expected_fields(self, api_client):
        element = DataElementFactory()

        result = api_client.get(list_url(element.dataset)).data["results"][0]

        assert set(result) == {
            "data_element_uuid",
            "dataset_uuid",
            "name",
            "description",
            "data_type",
            "max_length",
            "is_nullable",
            "is_primary_key",
            "is_pii",
            "created_at",
            "updated_at",
        }

    def test_filters_to_pii(self, api_client):
        dataset = DatasetFactory(retention_period_days=30)
        DataElementFactory(dataset=dataset, name="email", is_pii=True)
        DataElementFactory(dataset=dataset, name="created_at", is_pii=False)

        response = api_client.get(list_url(dataset), {"is_pii": "true"})

        assert [e["name"] for e in response.data["results"]] == ["email"]

    def test_orders_by_several_keys(self, api_client):
        dataset = DatasetFactory(retention_period_days=30)
        DataElementFactory(dataset=dataset, name="a_public", is_pii=False)
        DataElementFactory(dataset=dataset, name="b_personal", is_pii=True)

        response = api_client.get(list_url(dataset), {"ordering": ["-is_pii", "name"]})

        assert [e["name"] for e in response.data["results"]] == ["b_personal", "a_public"]

    def test_an_unknown_dataset_is_a_404(self, api_client):
        url = reverse(
            "v2:catalog:data-elements",
            kwargs={"dataset_uuid": "00000000-0000-0000-0000-000000000000"},
        )

        assert api_client.get(url).status_code == 404

    def test_listing_does_not_scale_its_queries_with_the_number_of_elements(
        self, api_client, django_assert_num_queries
    ):
        """`dataset_uuid` is read through a relation, so this would be an N+1 without a join."""
        dataset = DatasetFactory()
        DataElementFactory.create_batch(10, dataset=dataset)

        # 1 to resolve the dataset, 1 for the pagination COUNT, 1 for the joined page.
        with django_assert_num_queries(3):
            api_client.get(list_url(dataset))


class TestCreateDataElement:
    def test_creates_an_element(self, api_client):
        dataset = DatasetFactory()

        response = api_client.post(
            list_url(dataset),
            {
                "name": "email",
                "description": "Primary contact address.",
                "data_type": "string",
                "max_length": 254,
                "is_nullable": False,
            },
        )

        assert response.status_code == 201
        assert response.data["name"] == "email"
        assert response.data["dataset_uuid"] == str(dataset.uuid)
        assert DataElement.objects.count() == 1

    def test_derives_nullability_for_a_primary_key(self, api_client):
        response = api_client.post(
            list_url(DatasetFactory()),
            {"name": "customer_id", "data_type": "uuid", "is_primary_key": True},
        )

        assert response.status_code == 201
        assert response.data["is_nullable"] is False

    def test_a_second_primary_key_is_a_400(self, api_client):
        dataset = DatasetFactory()
        DataElementFactory(dataset=dataset, is_primary_key=True, is_nullable=False)

        response = api_client.post(
            list_url(dataset),
            {"name": "alt_id", "data_type": "uuid", "is_primary_key": True},
        )

        assert response.status_code == 400

    def test_a_duplicate_name_is_a_400(self, api_client):
        dataset = DatasetFactory()
        DataElementFactory(dataset=dataset, name="email")

        response = api_client.post(list_url(dataset), {"name": "EMAIL", "data_type": "string"})

        assert response.status_code == 400
        assert DataElement.objects.count() == 1

    def test_max_length_on_a_non_string_is_a_400(self, api_client):
        response = api_client.post(
            list_url(DatasetFactory()),
            {"name": "amount", "data_type": "decimal", "max_length": 10},
        )

        assert response.status_code == 400

    def test_an_unknown_data_type_is_a_400(self, api_client):
        response = api_client.post(
            list_url(DatasetFactory()), {"name": "blob", "data_type": "binary"}
        )

        assert response.status_code == 400
        assert "data_type" in response.data["extra"]["fields"]

    def test_pii_without_a_retention_period_is_a_400(self, api_client):
        dataset = DatasetFactory(retention_period_days=None)

        response = api_client.post(
            list_url(dataset), {"name": "email", "data_type": "string", "is_pii": True}
        )

        assert response.status_code == 400
        assert response.data["extra"]["field"] == "retention_period_days"
        assert DataElement.objects.count() == 0

    def test_pii_with_a_retention_period_is_created(self, api_client):
        dataset = DatasetFactory(retention_period_days=365)

        response = api_client.post(
            list_url(dataset), {"name": "email", "data_type": "string", "is_pii": True}
        )

        assert response.status_code == 201
        assert response.data["is_pii"] is True

    def test_adding_to_an_archived_dataset_is_a_409(self, api_client):
        dataset = DatasetFactory(lifecycle_status=DatasetLifecycleStatus.ARCHIVED)

        response = api_client.post(list_url(dataset), {"name": "email", "data_type": "string"})

        assert response.status_code == 409
        assert response.data["code"] == "conflict"


class TestRetrieveAndUpdateDataElement:
    def test_returns_the_element(self, api_client):
        element = DataElementFactory(name="email")

        response = api_client.get(detail_url(element))

        assert response.status_code == 200
        assert response.data["name"] == "email"

    def test_an_element_of_another_dataset_is_a_404(self, api_client):
        element = DataElementFactory()
        other = DatasetFactory()

        url = reverse(
            "v2:catalog:data-element-detail",
            kwargs={"dataset_uuid": other.uuid, "data_element_uuid": element.uuid},
        )

        assert api_client.get(url).status_code == 404

    def test_updates_the_fields_that_were_sent(self, api_client):
        element = DataElementFactory(name="email", description="Original.")

        response = api_client.patch(detail_url(element), {"description": "Updated."})

        assert response.status_code == 200
        assert response.data["description"] == "Updated."
        assert response.data["name"] == "email"

    def test_flagging_pii_without_a_retention_period_is_a_400(self, api_client):
        element = DataElementFactory(dataset=DatasetFactory(retention_period_days=None))

        response = api_client.patch(detail_url(element), {"is_pii": True})

        assert response.status_code == 400

    def test_an_empty_body_is_a_400(self, api_client):
        response = api_client.patch(detail_url(DataElementFactory()), {})

        assert response.status_code == 400


class TestBulkCreateDataElements:
    def test_creates_every_element(self, api_client):
        dataset = DatasetFactory()

        response = api_client.post(
            bulk_create_url(dataset),
            {
                "data_elements": [
                    {"name": "id", "data_type": "uuid", "is_primary_key": True},
                    {"name": "email", "data_type": "string", "max_length": 254},
                ]
            },
        )

        assert response.status_code == 201
        assert [e["name"] for e in response.data["data_elements"]] == ["id", "email"]
        assert DataElement.objects.count() == 2

    def test_an_empty_batch_is_a_400(self, api_client):
        response = api_client.post(bulk_create_url(DatasetFactory()), {"data_elements": []})

        assert response.status_code == 400

    def test_the_batch_size_is_capped(self, api_client):
        dataset = DatasetFactory()
        payload = [{"name": f"field_{i}", "data_type": "string"} for i in range(101)]

        response = api_client.post(bulk_create_url(dataset), {"data_elements": payload})

        assert response.status_code == 400
        assert DataElement.objects.count() == 0

    def test_one_invalid_element_rejects_the_whole_batch(self, api_client):
        dataset = DatasetFactory()

        response = api_client.post(
            bulk_create_url(dataset),
            {
                "data_elements": [
                    {"name": "valid", "data_type": "string"},
                    {"name": "invalid", "data_type": "decimal", "max_length": 5},
                ]
            },
        )

        assert response.status_code == 400
        assert DataElement.objects.count() == 0

    def test_a_rule_violation_reports_which_element_caused_it(self, api_client):
        dataset = DatasetFactory(retention_period_days=None)

        response = api_client.post(
            bulk_create_url(dataset),
            {
                "data_elements": [
                    {"name": "id", "data_type": "uuid"},
                    {"name": "email", "data_type": "string", "is_pii": True},
                ]
            },
        )

        assert response.status_code == 400
        assert response.data["extra"]["index"] == 1
        assert response.data["extra"]["name"] == "email"

    def test_names_that_collide_within_the_batch_are_a_400(self, api_client):
        response = api_client.post(
            bulk_create_url(DatasetFactory()),
            {
                "data_elements": [
                    {"name": "email", "data_type": "string"},
                    {"name": "EMAIL", "data_type": "string"},
                ]
            },
        )

        assert response.status_code == 400
        assert response.data["extra"] == {"index": 1, "conflicts_with_index": 0}

    def test_bulk_creating_on_an_archived_dataset_is_a_409(self, api_client):
        dataset = DatasetFactory(lifecycle_status=DatasetLifecycleStatus.ARCHIVED)

        response = api_client.post(
            bulk_create_url(dataset),
            {"data_elements": [{"name": "email", "data_type": "string"}]},
        )

        assert response.status_code == 409


class TestUrlShapes:
    def test_the_bulk_create_action_is_not_shadowed_by_the_detail_route(self, api_client):
        """`actions` is not a UUID, so the detail converter cannot swallow the action URL."""
        dataset = DatasetFactory()

        assert bulk_create_url(dataset).endswith("/data-elements/actions/bulk-create/")

    def test_data_types_are_exposed_as_their_stored_values(self, api_client):
        element = DataElementFactory(data_type=DataType.DATETIME)

        assert api_client.get(detail_url(element)).data["data_type"] == "datetime"
