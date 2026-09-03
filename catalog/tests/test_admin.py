"""
Tests for the admin registration.

Only the parts with logic in them: the annotated changelist. The admin is a support tool,
so it gets proportionate coverage, not the same depth as the API.
"""

import pytest
from django.contrib.admin.sites import AdminSite

from catalog.admin import DatasetAdmin
from catalog.models import Dataset
from catalog.tests.factories import DataElementFactory, DatasetFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def dataset_admin() -> DatasetAdmin:
    return DatasetAdmin(Dataset, AdminSite())


class TestDatasetAdmin:
    def test_the_changelist_annotates_the_element_count(self, dataset_admin, rf):
        dataset = DatasetFactory()
        DataElementFactory.create_batch(3, dataset=dataset)

        queryset = dataset_admin.get_queryset(rf.get("/admin/"))

        assert dataset_admin.data_element_count(queryset.get(pk=dataset.pk)) == 3

    def test_the_changelist_does_not_count_per_row(
        self, dataset_admin, rf, django_assert_num_queries
    ):
        for _ in range(5):
            DataElementFactory.create_batch(2, dataset=DatasetFactory())

        queryset = dataset_admin.get_queryset(rf.get("/admin/"))

        with django_assert_num_queries(1):
            [dataset_admin.data_element_count(dataset) for dataset in queryset]
