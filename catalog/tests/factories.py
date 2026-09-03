"""
Test factories.

Factories build model instances *directly*, bypassing the service layer. That is the point:
a test for a rule must be able to construct the state the rule is about, including states
the services would refuse to create -- an archived dataset that already has PII in it, for
instance. Tests that want the rules applied call the services.
"""

import factory

from catalog.models import DataElement, Dataset, DatasetLifecycleStatus, DataType


class DatasetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Dataset

    # A sequence, not a random word: names are unique case-insensitively, and a flaky
    # collision in a test suite is a bug hunt nobody enjoys.
    name = factory.Sequence(lambda n: f"Dataset {n}")
    description = ""
    owner = "test-team"
    lifecycle_status = DatasetLifecycleStatus.DRAFT
    retention_period_days = None


class DataElementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DataElement

    dataset = factory.SubFactory(DatasetFactory)
    name = factory.Sequence(lambda n: f"field_{n}")
    description = ""
    data_type = DataType.STRING
    max_length = None
    is_nullable = True
    is_primary_key = False
    is_pii = False
