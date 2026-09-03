"""
Dataset writes.

Services are the only place that creates or changes catalog data. Views validate and
serialize; services decide what is allowed to happen and make it happen. That is what lets
the same rule apply whether the caller is an HTTP request, the seed command or a future
importer -- none of them can route around the policy, because none of them touch the model
directly.

Every service takes keyword arguments only. A positional call site is one refactor away
from silently swapping two same-typed arguments.
"""

from catalog.models import Dataset, DatasetLifecycleStatus
from catalog.services import rules
from common.models.services import model_update

#: Fields a client may change after creation. `uuid`, `created_at` and `updated_at` are
#: deliberately absent: identity and audit timestamps are the service's to set, not the
#: caller's. Listing them explicitly (rather than passing `validated_data` straight to the
#: model) is what makes a newly added model field non-writable until someone decides it is.
UPDATABLE_FIELDS = [
    "name",
    "description",
    "owner",
    "lifecycle_status",
    "retention_period_days",
]


def create_dataset(
    *,
    name: str,
    description: str = "",
    owner: str = "",
    lifecycle_status: str = DatasetLifecycleStatus.DRAFT,
    retention_period_days: int | None = None,
) -> Dataset:
    """
    Create a dataset.

    `full_clean()` runs before the insert so that a constraint violation comes back as a
    readable, field-mapped validation error instead of an `IntegrityError`. The database
    constraints are still the thing that guarantees correctness -- this only guarantees a
    good error message on the way there.
    """
    rules.assert_lifecycle_status_is_creatable(lifecycle_status)

    dataset = Dataset(
        name=name.strip(),
        description=description,
        owner=owner.strip(),
        lifecycle_status=lifecycle_status,
        retention_period_days=retention_period_days,
    )
    dataset.full_clean()
    dataset.save()

    return dataset


def update_dataset(*, dataset: Dataset, **validated_data) -> Dataset:
    """
    Apply a partial update to a dataset.

    Rules are checked in order of how fundamental they are: an archived dataset is not
    writable at all, so that is settled before we look at what the caller wanted to change.
    """
    rules.assert_dataset_is_writable(dataset)

    if "lifecycle_status" in validated_data:
        rules.assert_lifecycle_transition_is_allowed(
            current=dataset.lifecycle_status,
            new=validated_data["lifecycle_status"],
        )

    # `in` rather than `.get()`: clearing the retention period and not mentioning it at all
    # are different requests, and only the first one is subject to this rule.
    if (
        "retention_period_days" in validated_data
        and validated_data["retention_period_days"] is None
    ):
        rules.assert_retention_period_can_be_cleared(dataset)

    dataset, _is_updated = model_update(
        instance=dataset,
        fields=UPDATABLE_FIELDS,
        data=validated_data,
    )
    return dataset
