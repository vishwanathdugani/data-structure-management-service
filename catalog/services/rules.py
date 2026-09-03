"""
The catalog's business rules, in one place.

These are the rules that a database constraint cannot express, because they depend on
other rows (does this dataset hold PII?) or on a transition (may this status become that
status?) rather than on the contents of the row being written.

They live apart from `datasets.py` and `data_elements.py` for two reasons. Each rule is
needed by more than one service -- "a data element may not be written to an archived
dataset" applies to create, update and bulk-create alike -- so a shared module is what
keeps there being exactly one definition of each rule. And gathering them makes the
service's policy readable in a single file, instead of having to be reconstructed from the
`if` statements scattered through the write paths.

Each function is named `assert_*`, returns `None`, and raises a domain exception when the
rule is broken.
"""

from catalog.models import Dataset, DatasetLifecycleStatus
from common.exceptions import ConflictError, ValidationError

#: The lifecycle state machine. A status may always stay where it is; anything not listed
#: here is rejected. `ARCHIVED` maps to the empty set because archiving is deliberately
#: terminal: a catalog is an audit surface, and being able to quietly resurrect a retired
#: dataset would make its history unreliable. Recreating it is an explicit, visible act.
ALLOWED_LIFECYCLE_TRANSITIONS: dict[str, set[str]] = {
    DatasetLifecycleStatus.DRAFT: {
        DatasetLifecycleStatus.ACTIVE,
        DatasetLifecycleStatus.ARCHIVED,
    },
    DatasetLifecycleStatus.ACTIVE: {
        DatasetLifecycleStatus.DEPRECATED,
        DatasetLifecycleStatus.ARCHIVED,
    },
    DatasetLifecycleStatus.DEPRECATED: {
        DatasetLifecycleStatus.ACTIVE,
        DatasetLifecycleStatus.ARCHIVED,
    },
    DatasetLifecycleStatus.ARCHIVED: set(),
}

#: Statuses a dataset may be created in. You cannot create something that is already
#: retired, and you cannot skip straight past the states that give the value meaning.
CREATABLE_LIFECYCLE_STATUSES: set[str] = {
    DatasetLifecycleStatus.DRAFT,
    DatasetLifecycleStatus.ACTIVE,
}


def assert_dataset_is_writable(dataset: Dataset) -> None:
    """
    An archived dataset accepts no writes, to itself or to its data elements.

    This is a 409 and not a 400: the request is well-formed, it just conflicts with the
    current state of the resource. Retrying it unchanged will keep failing.
    """
    if dataset.is_archived:
        raise ConflictError(
            f"Dataset '{dataset.name}' is archived and can no longer be modified.",
            extra={"dataset_uuid": str(dataset.uuid), "lifecycle_status": dataset.lifecycle_status},
        )


def assert_lifecycle_transition_is_allowed(*, current: str, new: str) -> None:
    """Reject a lifecycle change that the state machine above does not allow."""
    if current == new:
        return

    allowed = ALLOWED_LIFECYCLE_TRANSITIONS.get(current, set())
    if new not in allowed:
        raise ConflictError(
            f"A dataset cannot move from '{current}' to '{new}'.",
            extra={
                "lifecycle_status": {
                    "current": current,
                    "requested": new,
                    "allowed": sorted(allowed),
                }
            },
        )


def assert_lifecycle_status_is_creatable(status: str) -> None:
    """Reject creating a dataset directly into a late lifecycle stage."""
    if status not in CREATABLE_LIFECYCLE_STATUSES:
        raise ValidationError(
            f"A dataset cannot be created with status '{status}'.",
            extra={"lifecycle_status": {"allowed": sorted(CREATABLE_LIFECYCLE_STATUSES)}},
        )


def assert_dataset_can_hold_pii(dataset: Dataset) -> None:
    """
    A dataset may only hold PII once it declares how long that data is kept.

    Storage limitation (GDPR Art. 5(1)(e)) says personal data may not be kept indefinitely.
    A metadata catalog is exactly the place to make that answerable, so the rule is: mark a
    field as personal data and the catalog will insist you also say for how long. Enforcing
    it at write time is what keeps the catalog trustworthy -- a nightly report of
    "PII without a retention policy" that is allowed to be non-empty is a report nobody
    acts on.
    """
    if dataset.retention_period_days is None:
        raise ValidationError(
            (
                f"Dataset '{dataset.name}' must declare a retention period before it can "
                f"hold personally identifiable information."
            ),
            extra={"dataset_uuid": str(dataset.uuid), "field": "retention_period_days"},
        )


def assert_retention_period_can_be_cleared(dataset: Dataset) -> None:
    """
    The other half of `assert_dataset_can_hold_pii`: you cannot drop the retention period
    out from under existing PII.

    Without this, the rule would be trivially bypassable in two requests -- declare a
    retention period, add the PII element, then clear the retention period again.
    """
    pii_element_names = list(
        dataset.data_elements.filter(is_pii=True).values_list("name", flat=True)
    )
    if pii_element_names:
        raise ConflictError(
            (
                f"Dataset '{dataset.name}' holds personally identifiable information, so its "
                f"retention period cannot be removed."
            ),
            extra={"pii_data_elements": sorted(pii_element_names)},
        )
