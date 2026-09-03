"""Tests for `BaseView` and the pagination contract it exposes."""

import pytest
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from api.v2.core.base import BaseView
from api.v2.core.openapi import paginated_response
from api.v2.core.pagination import LimitOffsetPagination
from catalog.models import Dataset
from catalog.tests.factories import DatasetFactory


class PaginatedView(BaseView):
    def get(self, request, *args, **kwargs):
        page = self.paginate_queryset(Dataset.objects.order_by("pk"))
        return self.get_paginated_response([dataset.name for dataset in page])


class UnpaginatedView(BaseView):
    """A view may opt out; a fixed, small collection does not need an envelope."""

    pagination_class = None

    def get(self, request, *args, **kwargs):
        page = self.paginate_queryset(Dataset.objects.order_by("pk"))
        return Response({"page_is_none": page is None})


@pytest.mark.django_db
class TestPaginationHelpers:
    def test_paginates_a_queryset(self):
        DatasetFactory.create_batch(3)

        response = PaginatedView.as_view()(APIRequestFactory().get("/", {"limit": 2}))

        assert response.data["count"] == 3
        assert len(response.data["results"]) == 2

    def test_returns_none_when_pagination_is_disabled(self):
        DatasetFactory()

        response = UnpaginatedView.as_view()(APIRequestFactory().get("/"))

        assert response.data == {"page_is_none": True}

    def test_the_paginator_is_built_once_per_view_instance(self):
        view = PaginatedView()

        assert view.paginator is view.paginator

    def test_the_runtime_envelope_matches_the_documented_one(self):
        """
        Guards the one duplication left in the pagination code: the keys the paginator
        actually emits, and the keys `openapi.paginated_response` promises. If they ever
        drift, every generated client is wrong in a way no other test would catch.
        """
        DatasetFactory.create_batch(2)

        response = PaginatedView.as_view()(APIRequestFactory().get("/"))
        documented = paginated_response(name="Probe", child=serializers.ListField())

        assert set(response.data) == set(documented.fields)


class TestGetOrdering:
    def test_reads_repeated_parameters_in_order(self):
        request = APIRequestFactory().get("/", {"ordering": ["-is_pii", "name"]})

        assert BaseView().get_ordering(BaseView().initialize_request(request)) == [
            "-is_pii",
            "name",
        ]

    def test_returns_an_empty_list_when_absent(self):
        request = APIRequestFactory().get("/")

        assert BaseView().get_ordering(BaseView().initialize_request(request)) == []


class TestPaginationLimits:
    def test_the_default_page_size(self):
        assert LimitOffsetPagination.default_limit == 25

    def test_the_page_size_is_capped(self):
        assert LimitOffsetPagination.max_limit == 100
