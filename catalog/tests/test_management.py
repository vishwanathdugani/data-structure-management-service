"""
Tests for the seed command.

Worth testing because the seed goes through the service layer: if a business rule changes
in a way the example data no longer satisfies, this test fails and tells us the example is
stale -- instead of the command inserting data the API itself would have rejected.
"""

import pytest
from django.core.management import call_command

from catalog.models import DataElement, Dataset
from catalog.tests.factories import DatasetFactory

pytestmark = pytest.mark.django_db


class TestSeedCatalog:
    def test_creates_the_example_catalog(self):
        call_command("seed_catalog", verbosity=0)

        assert set(Dataset.objects.values_list("name", flat=True)) == {"Customer", "Order"}
        assert DataElement.objects.count() == 9

    def test_the_seeded_data_satisfies_the_pii_retention_rule(self):
        call_command("seed_catalog", verbosity=0)

        for dataset in Dataset.objects.containing_pii():
            assert dataset.retention_period_days is not None

    def test_is_safe_to_run_twice(self):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_catalog", verbosity=0)

        assert Dataset.objects.count() == 2

    def test_skips_a_dataset_that_already_exists_under_another_case(self):
        DatasetFactory(name="customer")

        call_command("seed_catalog", verbosity=0)

        assert Dataset.objects.filter(name__iexact="customer").count() == 1
