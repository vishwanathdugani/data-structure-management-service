"""
Seed the catalog with a small, realistic example.

Useful for exercising the API by hand and for demoing the PII and lifecycle rules without
having to type a dozen requests first. It goes through the service layer rather than
through the ORM, which means the seed data is guaranteed to satisfy the same rules real
data does -- if a rule changes and the fixture no longer complies, this command fails
instead of quietly inserting data the API would have rejected.
"""

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import Dataset, DatasetLifecycleStatus, DataType
from catalog.services import bulk_create_data_elements, create_dataset

SEED: list[dict[str, Any]] = [
    {
        "dataset": {
            "name": "Customer",
            "description": "A person or organisation that buys from us.",
            "owner": "growth-team",
            "lifecycle_status": DatasetLifecycleStatus.ACTIVE,
            # Required before any of the PII elements below may be added.
            "retention_period_days": 730,
        },
        "data_elements": [
            {
                "name": "customer_id",
                "description": "Internal identifier.",
                "data_type": DataType.UUID,
                "is_primary_key": True,
            },
            {
                "name": "email",
                "description": "Primary contact address.",
                "data_type": DataType.STRING,
                "max_length": 254,
                "is_nullable": False,
                "is_pii": True,
            },
            {
                "name": "full_name",
                "data_type": DataType.STRING,
                "max_length": 200,
                "is_pii": True,
            },
            {
                "name": "date_of_birth",
                "data_type": DataType.DATE,
                "is_pii": True,
            },
            {
                "name": "marketing_opt_in",
                "data_type": DataType.BOOLEAN,
                "is_nullable": False,
            },
        ],
    },
    {
        "dataset": {
            "name": "Order",
            "description": "A confirmed purchase made by a customer.",
            "owner": "commerce-team",
            "lifecycle_status": DatasetLifecycleStatus.ACTIVE,
            "retention_period_days": 2555,
        },
        "data_elements": [
            {
                "name": "order_id",
                "data_type": DataType.UUID,
                "is_primary_key": True,
            },
            {
                "name": "placed_at",
                "data_type": DataType.DATETIME,
                "is_nullable": False,
            },
            {
                "name": "total_amount_eur",
                "description": "Order total in euro, including VAT.",
                "data_type": DataType.DECIMAL,
                "is_nullable": False,
            },
            {
                "name": "shipping_address",
                "description": "Free-form delivery address.",
                "data_type": DataType.STRING,
                "max_length": 500,
                "is_pii": True,
            },
        ],
    },
]


class Command(BaseCommand):
    help = "Create an example catalog. Skips datasets that already exist."

    @transaction.atomic
    def handle(self, *args, **options) -> None:
        for entry in SEED:
            name = entry["dataset"]["name"]

            if Dataset.objects.filter(name__iexact=name).exists():
                self.stdout.write(self.style.WARNING(f"Skipping '{name}': already exists."))
                continue

            dataset = create_dataset(**entry["dataset"])
            created = bulk_create_data_elements(
                dataset=dataset,
                data_elements=entry["data_elements"],
            )
            self.stdout.write(
                self.style.SUCCESS(f"Created '{dataset.name}' with {len(created)} data elements.")
            )
