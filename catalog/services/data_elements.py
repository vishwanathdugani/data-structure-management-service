"""Data element writes."""

from typing import Any

from django.db import transaction

from catalog.models import DataElement, Dataset
from catalog.services import rules
from common.exceptions import ApplicationError, ValidationError
from common.models.services import model_update

#: See the note on `catalog.services.datasets.UPDATABLE_FIELDS`. `dataset` is not in this
#: list on purpose: a data element is part of its dataset, and "move this field to another
#: entity" is not an edit, it is a delete and a create.
UPDATABLE_FIELDS = [
    "name",
    "description",
    "data_type",
    "max_length",
    "is_nullable",
    "is_primary_key",
    "is_pii",
]


def create_data_element(
    *,
    dataset: Dataset,
    name: str,
    data_type: str,
    description: str = "",
    max_length: int | None = None,
    is_nullable: bool | None = None,
    is_primary_key: bool = False,
    is_pii: bool = False,
) -> DataElement:
    """
    Add a data element to a dataset.

    `is_nullable` defaults to `None`, meaning "not specified", rather than to `True`. An
    unspecified nullability is then derived from the role of the element: a primary key is
    not nullable, anything else is. Passing `is_nullable=True` together with
    `is_primary_key=True` is still an error rather than being silently corrected -- a
    default may be inferred, an explicit contradiction may not.
    """
    rules.assert_dataset_is_writable(dataset)
    if is_pii:
        rules.assert_dataset_can_hold_pii(dataset)

    if is_nullable is None:
        is_nullable = not is_primary_key

    data_element = DataElement(
        dataset=dataset,
        name=name.strip(),
        description=description,
        data_type=data_type,
        max_length=max_length,
        is_nullable=is_nullable,
        is_primary_key=is_primary_key,
        is_pii=is_pii,
    )
    data_element.full_clean()
    data_element.save()

    return data_element


def update_data_element(*, data_element: DataElement, **validated_data) -> DataElement:
    """Apply a partial update to a data element."""
    rules.assert_dataset_is_writable(data_element.dataset)

    if validated_data.get("is_pii"):
        rules.assert_dataset_can_hold_pii(data_element.dataset)

    data_element, _is_updated = model_update(
        instance=data_element,
        fields=UPDATABLE_FIELDS,
        data=validated_data,
    )
    return data_element


@transaction.atomic
def bulk_create_data_elements(
    *,
    dataset: Dataset,
    data_elements: list[dict[str, Any]],
) -> list[DataElement]:
    """
    Create several data elements in one all-or-nothing request.

    Defining a dataset's structure means adding a dozen fields at once, and doing that as a
    dozen requests leaves the catalog describing a half-defined entity whenever one of them
    fails. `transaction.atomic` makes the batch a single unit: it either lands whole or not
    at all.

    Elements are created one at a time rather than with `bulk_create`, which is the slower
    but correct choice here. `bulk_create` skips `full_clean()`, so a batch would fail with
    a raw database error naming an index instead of a validation error naming a field --
    and on a batch of twenty, "which one was wrong" is the only thing the caller needs to
    know. The `index` in `extra` answers exactly that.
    """
    rules.assert_dataset_is_writable(dataset)
    _assert_names_are_unique_within_payload(data_elements)

    created: list[DataElement] = []
    for index, payload in enumerate(data_elements):
        try:
            created.append(create_data_element(dataset=dataset, **payload))
        except ApplicationError as exc:
            exc.extra = {**exc.extra, "index": index, "name": payload.get("name")}
            raise

    return created


def _assert_names_are_unique_within_payload(data_elements: list[dict[str, Any]]) -> None:
    """
    Catch names that collide inside the request itself.

    The unique index would reject these anyway, but one element at a time and with the
    message "this dataset already has a data element with this name" -- which is confusing
    when the conflict is with a sibling in the same payload rather than with something
    already stored.
    """
    seen: dict[str, int] = {}
    for index, payload in enumerate(data_elements):
        key = str(payload.get("name", "")).strip().casefold()
        if key in seen:
            raise ValidationError(
                f"Duplicate data element name {payload.get('name')!r} in request.",
                extra={"index": index, "conflicts_with_index": seen[key]},
            )
        seen[key] = index
