"""
Tests for the generated OpenAPI document.

The schema is a deliverable, not a by-product: it is what a consumer reads and what a
generated client is built from. These tests make sure it keeps generating, and that the
parts derived from the filter sets and ordering services really are derived -- so a filter
added tomorrow appears in the docs without anyone remembering to write it down twice.
"""

import pytest
from django.urls import reverse
from drf_spectacular.generators import SchemaGenerator

from api.v2.core.openapi import filterset_parameters, ordering_parameter
from catalog.filters import DatasetFilterSet
from catalog.selectors import DatasetOrderingService


@pytest.fixture(scope="module")
def schema() -> dict:
    return SchemaGenerator().get_schema(request=None, public=True)


class TestSchemaGeneration:
    def test_every_endpoint_is_documented(self, schema):
        assert set(schema["paths"]) == {
            "/v2/catalog/datasets/",
            "/v2/catalog/datasets/{dataset_uuid}/",
            "/v2/catalog/datasets/{dataset_uuid}/data-elements/",
            "/v2/catalog/datasets/{dataset_uuid}/data-elements/actions/bulk-create/",
            "/v2/catalog/datasets/{dataset_uuid}/data-elements/{data_element_uuid}/",
        }

    def test_operations_have_stable_identifiers(self, schema):
        """`operationId` becomes the method name in a generated client, so it must be set."""
        operation = schema["paths"]["/v2/catalog/datasets/"]["get"]

        assert operation["operationId"] == "datasets_list"

    def test_list_responses_document_the_pagination_envelope(self, schema):
        response = schema["paths"]["/v2/catalog/datasets/"]["get"]["responses"]["200"]
        component = response["content"]["application/json"]["schema"]["$ref"].split("/")[-1]

        assert set(schema["components"]["schemas"][component]["properties"]) == {
            "count",
            "limit",
            "offset",
            "next",
            "previous",
            "results",
        }

    def test_error_responses_are_documented(self, schema):
        responses = schema["paths"]["/v2/catalog/datasets/{dataset_uuid}/"]["patch"]["responses"]

        assert {"200", "400", "404", "409"} <= set(responses)

    def test_the_nested_data_element_component_is_named(self, schema):
        """`inline_serializer(name=...)` is what gives generated clients a usable type name."""
        assert "DatasetDetailDataElement" in str(schema["components"]["schemas"].keys())


class TestDerivedParameters:
    def test_filter_parameters_come_from_the_filter_set(self):
        names = {parameter.name for parameter in filterset_parameters(DatasetFilterSet)}

        assert {"name", "owner", "lifecycle_status", "contains_pii", "search"} <= names

    def test_range_filters_expand_into_the_pair_that_is_actually_read(self):
        names = {parameter.name for parameter in filterset_parameters(DatasetFilterSet)}

        assert "created_at_after" in names
        assert "created_at_before" in names
        assert "created_at" not in names

    def test_boolean_filters_are_typed_as_booleans(self):
        parameters = {p.name: p for p in filterset_parameters(DatasetFilterSet)}

        assert parameters["contains_pii"].type is bool

    def test_choice_filters_carry_their_options(self):
        parameters = {p.name: p for p in filterset_parameters(DatasetFilterSet)}

        assert parameters["lifecycle_status"].enum == ["draft", "active", "deprecated", "archived"]

    def test_the_ordering_parameter_comes_from_the_ordering_service(self):
        parameter = ordering_parameter(DatasetOrderingService)

        assert "name" in parameter.enum
        assert "-name" in parameter.enum
        assert "lifecycle_status" in parameter.enum


@pytest.mark.django_db
class TestSchemaEndpoints:
    def test_the_schema_is_served(self, api_client):
        response = api_client.get(reverse("v2:schema"))

        assert response.status_code == 200

    def test_the_documentation_ui_is_served(self, api_client):
        response = api_client.get(reverse("v2:docs"))

        assert response.status_code == 200
