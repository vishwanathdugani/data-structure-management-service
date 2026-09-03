"""
Tests for `common.models.services.model_update`.

`Dataset` stands in as the model under test rather than a purpose-built one, which would
need its own migration and its own table in every test run. The trade-off is a dependency
from a `common` test onto `catalog`; the alternative costs more than it is worth here.
"""

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from catalog.models import Dataset
from catalog.tests.factories import DatasetFactory
from common.models.services import model_update

pytestmark = pytest.mark.django_db


class TestModelUpdate:
    def test_updates_the_fields_that_were_sent(self):
        dataset = DatasetFactory(name="Customer", owner="growth-team")

        updated, is_updated = model_update(
            instance=dataset,
            fields=["name", "owner"],
            data={"name": "Client"},
        )

        assert is_updated is True
        assert updated.name == "Client"
        # Not in `data`, so untouched -- this is what makes PATCH mean PATCH.
        assert updated.owner == "growth-team"

    def test_ignores_data_keys_that_are_not_in_fields(self):
        """`fields` is the allow-list. A key outside it is not an update, it is an attack."""
        dataset = DatasetFactory(name="Customer", owner="growth-team")

        updated, is_updated = model_update(
            instance=dataset,
            fields=["name"],
            data={"name": "Customer", "owner": "attacker"},
        )

        assert is_updated is False
        assert updated.owner == "growth-team"

    def test_reports_no_update_when_nothing_changed(self):
        dataset = DatasetFactory(name="Customer")
        original_updated_at = dataset.updated_at

        updated, is_updated = model_update(
            instance=dataset,
            fields=["name"],
            data={"name": "Customer"},
        )

        assert is_updated is False
        assert updated.updated_at == original_updated_at

    def test_bumps_updated_at_when_something_changed(self):
        dataset = DatasetFactory(name="Customer")
        original_updated_at = dataset.updated_at

        model_update(instance=dataset, fields=["name"], data={"name": "Client"})

        dataset.refresh_from_db()
        assert dataset.updated_at > original_updated_at

    def test_leaves_updated_at_alone_when_asked_to(self):
        dataset = DatasetFactory(name="Customer")
        original_updated_at = dataset.updated_at

        model_update(
            instance=dataset,
            fields=["name"],
            data={"name": "Client"},
            auto_updated_at=False,
        )

        dataset.refresh_from_db()
        assert dataset.updated_at == original_updated_at

    def test_persists_the_change(self):
        dataset = DatasetFactory(name="Customer")

        model_update(instance=dataset, fields=["name"], data={"name": "Client"})

        assert Dataset.objects.get(pk=dataset.pk).name == "Client"

    def test_raises_for_a_field_the_model_does_not_have(self):
        dataset = DatasetFactory()

        with pytest.raises(ValueError, match="not a field of Dataset"):
            model_update(instance=dataset, fields=["nonexistent"], data={"nonexistent": 1})

    def test_validates_before_saving(self):
        """`full_clean()` turns a would-be IntegrityError into a readable ValidationError."""
        DatasetFactory(name="Customer")
        other = DatasetFactory(name="Order")

        with pytest.raises(DjangoValidationError):
            model_update(instance=other, fields=["name"], data={"name": "customer"})

        other.refresh_from_db()
        assert other.name == "Order"

    def test_writes_only_the_changed_columns(self):
        """
        A partial update must not rewrite the whole row.

        Saving every column would silently overwrite work done concurrently on fields the
        caller never mentioned -- the classic lost update. This asserts on the emitted SQL
        rather than on a query count, because the count is dominated by validation queries
        (see `test_validation_costs_queries`) and would break on every constraint added.
        """
        dataset = DatasetFactory(name="Customer")

        with CaptureQueriesContext(connection) as queries:
            model_update(instance=dataset, fields=["owner"], data={"owner": "data-team"})

        updates = [q["sql"] for q in queries.captured_queries if q["sql"].startswith("UPDATE")]
        assert len(updates) == 1

        statement = updates[0]
        assert '"owner"' in statement
        assert '"updated_at"' in statement
        assert '"name"' not in statement
        assert '"description"' not in statement

    def test_validation_costs_queries(self):
        """
        Documents the price of `full_clean()`: one query per unique constraint plus one per
        check constraint, on top of the write itself.

        This is a deliberate trade-off. It buys field-mapped, human-readable errors on every
        write path, which is worth several cheap indexed lookups for a metadata catalog
        written by humans at human speed. It would not be worth it in a hot ingest loop --
        that path would skip `full_clean()` and handle `IntegrityError` instead. The test
        exists so the cost stays visible rather than becoming folklore.
        """
        dataset = DatasetFactory(name="Customer")

        with CaptureQueriesContext(connection) as queries:
            model_update(instance=dataset, fields=["owner"], data={"owner": "data-team"})

        statements = [q["sql"] for q in queries.captured_queries]
        selects = [sql for sql in statements if sql.startswith("SELECT")]

        # 2 uniqueness probes (uuid, name) + 3 evaluable check constraints.
        assert len(selects) == 5
