"""The abstract base model every domain model in this service inherits from."""

import uuid as uuid_lib

from django.db import models


class BaseModel(models.Model):
    """
    Adds a public UUID identifier and audit timestamps to a model.

    Identifier strategy: the table keeps an auto-incrementing integer primary key for
    internal use (foreign keys, index locality, join performance) and exposes a separate
    indexed `uuid` as the *only* identifier that ever leaves the service. External callers
    therefore cannot enumerate or infer row counts, and we stay free to change the internal
    key without breaking API consumers. All URLs and payloads use `<resource>_uuid`.
    """

    uuid = models.UUIDField(
        default=uuid_lib.uuid4,
        editable=False,
        unique=True,
        help_text="Public identifier. Stable for the lifetime of the record.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
