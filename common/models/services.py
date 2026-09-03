"""Generic model-writing helpers used by the service layer."""

from typing import Any

from django.db import models


def model_update(
    *,
    instance: models.Model,
    fields: list[str],
    data: dict[str, Any],
    auto_updated_at: bool = True,
) -> tuple[models.Model, bool]:
    """
    Apply a partial update to `instance` and return `(instance, is_updated)`.

    Only keys that appear in both `fields` and `data` are considered, which makes this safe
    to call with a serializer's `validated_data` straight from a PATCH: absent keys mean
    "leave alone", and a caller can never write a field the service did not explicitly
    allow.

    The update is skipped entirely when nothing actually changed, so a no-op PATCH does not
    bump `updated_at` or emit a write. When something did change we call `full_clean()`
    first: that runs field validators *and* (Django 4.1+) evaluates the model's `CHECK` and
    `UNIQUE` constraints, so a violation surfaces as a readable `ValidationError` instead of
    a raw `IntegrityError` from the database driver. It costs one query per constraint;
    `common/tests/test_model_update.py` pins that cost so it stays a visible trade-off.

    Only the changed columns are written, via `save(update_fields=...)`, so two concurrent
    updates to unrelated columns do not clobber each other.

    Many-to-many fields are not handled: no model in this service has one, and support that
    nothing exercises is support that quietly rots. Adding it is a small, obvious change
    when the first such field appears -- assign after the save, since a relation cannot be
    set on an unsaved row.
    """
    has_updated = False
    update_fields: list[str] = []

    model_fields = {field.name: field for field in instance._meta.get_fields()}

    for field in fields:
        # A field the caller did not send is not an update, it is an omission.
        if field not in data:
            continue

        if field not in model_fields:
            raise ValueError(f"{field!r} is not a field of {instance.__class__.__name__}.")

        if getattr(instance, field) != data[field]:
            has_updated = True
            update_fields.append(field)
            setattr(instance, field, data[field])

    if not has_updated:
        return instance, False

    if auto_updated_at and "updated_at" in model_fields and "updated_at" not in update_fields:
        # `auto_now` only fires for columns listed in `update_fields`.
        update_fields.append("updated_at")

    instance.full_clean()
    instance.save(update_fields=update_fields)

    return instance, True
