"""
End-to-end tests for the dataset endpoints.

These go through the real URL conf, the real exception handler and the real serializers, so
they pin the HTTP contract: status codes, the response envelope and the shape of the
payload. The rules themselves are tested against the services; what is verified here is
that a rule violation reaches the client as the right status and the right body.
"""

import pytest
from django.urls import reverse

from catalog.models import Dataset, DatasetLifecycleStatus
from catalog.tests.factories import DataElementFactory, DatasetFactory

pytestmark = pytest.mark.django_db

LIST_URL = reverse("v2:catalog:datasets")


def detail_url(dataset: Dataset) -> str:
    return reverse("v2:catalog:dataset-detail", kwargs={"dataset_uuid": dataset.uuid})


class TestListDatasets:
    def test_returns_a_paginated_envelope(self, api_client):
        DatasetFactory.create_batch(3)

        response = api_client.get(LIST_URL)

        assert response.status_code == 200
        assert set(response.data) == {"count", "limit", "offset", "next", "previous", "results"}
        assert response.data["count"] == 3
        assert len(response.data["results"]) == 3

    def test_returns_the_expected_fields(self, api_client):
        DatasetFactory(name="Customer", owner="growth-team", retention_period_days=730)

        result = api_client.get(LIST_URL).data["results"][0]

        assert set(result) == {
            "dataset_uuid",
            "name",
            "description",
            "owner",
            "lifecycle_status",
            "retention_period_days",
            "data_element_count",
            "created_at",
            "updated_at",
        }

    def test_does_not_embed_data_elements(self, api_client):
        """List responses stay flat; the count is what a list view needs."""
        dataset = DatasetFactory()
        DataElementFactory.create_batch(2, dataset=dataset)

        result = api_client.get(LIST_URL).data["results"][0]

        assert "data_elements" not in result
        assert result["data_element_count"] == 2

    def test_pagination_limits_the_page(self, api_client):
        DatasetFactory.create_batch(3)

        response = api_client.get(LIST_URL, {"limit": 2})

        assert response.data["count"] == 3
        assert len(response.data["results"]) == 2
        assert response.data["next"] is not None

    def test_the_page_size_is_capped(self, api_client):
        DatasetFactory()

        assert api_client.get(LIST_URL, {"limit": 100_000}).data["limit"] == 100

    def test_filters_and_orders(self, api_client):
        DatasetFactory(name="Customer")
        DatasetFactory(name="Customer archive")
        DatasetFactory(name="Order")

        response = api_client.get(LIST_URL, {"search": "customer", "ordering": "name"})

        assert [r["name"] for r in response.data["results"]] == ["Customer", "Customer archive"]

    def test_an_unknown_ordering_field_is_a_400(self, api_client):
        response = api_client.get(LIST_URL, {"ordering": "password"})

        assert response.status_code == 400
        assert response.data["code"] == "validation_error"
        assert "allowed" in response.data["extra"]["ordering"]

    def test_an_invalid_filter_is_a_400(self, api_client):
        response = api_client.get(LIST_URL, {"lifecycle_status": "banana"})

        assert response.status_code == 400
        assert "lifecycle_status" in response.data["extra"]["fields"]

    def test_listing_does_not_scale_its_queries_with_the_number_of_rows(
        self, api_client, django_assert_num_queries
    ):
        """
        A guard against N+1. The count annotation is one aggregate over the page, so ten
        datasets with elements cost the same as one.
        """
        for _ in range(10):
            DataElementFactory.create_batch(3, dataset=DatasetFactory())

        # 1 for the pagination COUNT, 1 for the page itself.
        with django_assert_num_queries(2):
            api_client.get(LIST_URL)


class TestCreateDataset:
    def test_creates_a_dataset(self, api_client):
        response = api_client.post(
            LIST_URL,
            {
                "name": "Customer",
                "description": "Someone who buys from us.",
                "owner": "growth-team",
                "lifecycle_status": "active",
                "retention_period_days": 730,
            },
        )

        assert response.status_code == 201
        assert response.data["name"] == "Customer"
        assert response.data["lifecycle_status"] == "active"
        assert response.data["data_element_count"] == 0
        assert Dataset.objects.count() == 1

    def test_only_the_name_is_required(self, api_client):
        response = api_client.post(LIST_URL, {"name": "Customer"})

        assert response.status_code == 201
        assert response.data["lifecycle_status"] == "draft"
        assert response.data["retention_period_days"] is None

    def test_a_missing_name_is_a_400(self, api_client):
        response = api_client.post(LIST_URL, {"description": "No name."})

        assert response.status_code == 400
        assert response.data["extra"]["fields"]["name"] == ["This field is required."]

    def test_a_duplicate_name_is_a_400(self, api_client):
        DatasetFactory(name="Customer")

        response = api_client.post(LIST_URL, {"name": "customer"})

        assert response.status_code == 400
        assert Dataset.objects.count() == 1

    def test_creating_an_archived_dataset_is_a_400(self, api_client):
        response = api_client.post(LIST_URL, {"name": "Customer", "lifecycle_status": "archived"})

        assert response.status_code == 400
        assert response.data["extra"]["lifecycle_status"]["allowed"] == ["active", "draft"]

    def test_a_zero_retention_period_is_a_400(self, api_client):
        response = api_client.post(LIST_URL, {"name": "Customer", "retention_period_days": 0})

        assert response.status_code == 400
        assert "retention_period_days" in response.data["extra"]["fields"]


class TestRetrieveDataset:
    def test_returns_the_dataset_with_its_data_elements(self, api_client):
        dataset = DatasetFactory(name="Customer")
        DataElementFactory(dataset=dataset, name="email")
        DataElementFactory(dataset=dataset, name="born_on")

        response = api_client.get(detail_url(dataset))

        assert response.status_code == 200
        assert response.data["name"] == "Customer"
        assert [e["name"] for e in response.data["data_elements"]] == ["born_on", "email"]

    def test_the_nested_elements_are_a_summary(self, api_client):
        dataset = DatasetFactory()
        DataElementFactory(dataset=dataset)

        element = api_client.get(detail_url(dataset)).data["data_elements"][0]

        assert set(element) == {
            "data_element_uuid",
            "name",
            "description",
            "data_type",
            "max_length",
            "is_nullable",
            "is_primary_key",
            "is_pii",
        }

    def test_a_dataset_without_elements_returns_an_empty_list(self, api_client):
        response = api_client.get(detail_url(DatasetFactory()))

        assert response.data["data_elements"] == []

    def test_an_unknown_dataset_is_a_404(self, api_client):
        url = reverse(
            "v2:catalog:dataset-detail",
            kwargs={"dataset_uuid": "00000000-0000-0000-0000-000000000000"},
        )

        response = api_client.get(url)

        assert response.status_code == 404
        assert response.data["code"] == "not_found"

    def test_a_malformed_uuid_is_a_404_in_the_error_envelope(self, api_client):
        """Rejected during routing, so it never reaches DRF -- see config/api_errors.py."""
        response = api_client.get("/v2/catalog/datasets/not-a-uuid/")

        assert response.status_code == 404
        assert response.json()["code"] == "not_found"

    def test_the_nested_elements_cost_one_extra_query(self, api_client, django_assert_num_queries):
        """Prefetched, not lazily walked. Without this the endpoint is an N+1."""
        dataset = DatasetFactory()
        DataElementFactory.create_batch(10, dataset=dataset)

        # 1 for the dataset (with its count), 1 for all of its elements.
        with django_assert_num_queries(2):
            api_client.get(detail_url(dataset))


class TestUpdateDataset:
    def test_updates_the_fields_that_were_sent(self, api_client):
        dataset = DatasetFactory(name="Customer", owner="growth-team")

        response = api_client.patch(detail_url(dataset), {"owner": "data-team"})

        assert response.status_code == 200
        assert response.data["owner"] == "data-team"
        assert response.data["name"] == "Customer"

    def test_an_empty_body_is_a_400(self, api_client):
        response = api_client.patch(detail_url(DatasetFactory()), {})

        assert response.status_code == 400
        assert response.data["extra"]["fields"]["non_field_errors"] == [
            "Provide at least one field to update."
        ]

    def test_an_invalid_lifecycle_transition_is_a_409(self, api_client):
        dataset = DatasetFactory(lifecycle_status=DatasetLifecycleStatus.ACTIVE)

        response = api_client.patch(detail_url(dataset), {"lifecycle_status": "draft"})

        assert response.status_code == 409
        assert response.data["code"] == "conflict"
        assert response.data["extra"]["lifecycle_status"]["allowed"] == ["archived", "deprecated"]

    def test_writing_to_an_archived_dataset_is_a_409(self, api_client):
        dataset = DatasetFactory(lifecycle_status=DatasetLifecycleStatus.ARCHIVED)

        response = api_client.patch(detail_url(dataset), {"description": "Edited."})

        assert response.status_code == 409

    def test_removing_a_retention_period_that_pii_depends_on_is_a_409(self, api_client):
        dataset = DatasetFactory(retention_period_days=365)
        DataElementFactory(dataset=dataset, name="email", is_pii=True)

        response = api_client.patch(detail_url(dataset), {"retention_period_days": None})

        assert response.status_code == 409
        assert response.data["extra"]["pii_data_elements"] == ["email"]


class TestUnsupportedMethods:
    def test_delete_is_not_offered(self, api_client):
        """Retirement goes through the lifecycle; the catalog keeps its history."""
        response = api_client.delete(detail_url(DatasetFactory()))

        assert response.status_code == 405
        assert response.data["code"] == "method_not_allowed"

    def test_put_is_not_offered(self, api_client):
        """Only PATCH: a full replace would silently blank fields the client omitted."""
        response = api_client.put(detail_url(DatasetFactory()), {"name": "Customer"})

        assert response.status_code == 405
