"""
The catalog data model: `Dataset` and `DataElement`.

A **dataset** is a business entity that the organisation holds data about -- Customer,
Order, Invoice. A **data element** is a single named piece of information inside one of
those entities -- `email`, `date_of_birth`. The relationship is one dataset to many data
elements, and a data element has no meaning outside its dataset, which is what makes the
composition (`on_delete=CASCADE`, uniqueness scoped per dataset) the right modelling
choice rather than a shared, reusable element table.

Correctness rules that can be expressed as a property of a single row live here, as
database constraints, so they hold no matter who writes -- the API, a management command,
the Django admin, or someone at a `manage.py shell`. Rules that need to look at other rows
or at a state transition live in `catalog/services/`; see the README for the split.
"""

from django.db import models
from django.db.models.functions import Lower

from common.models import BaseModel


class DataType(models.TextChoices):
    """
    The vocabulary a data element's type is drawn from.

    This is a closed, storage-agnostic set rather than free text or a link to a
    `DataType` table. Free text would make `?data_type=` useless within a week ("str",
    "String", "varchar"), and a lookup table would buy nothing here: the vocabulary changes
    at the pace of a code release, not at the pace of user input, so the enum keeps the
    values greppable, validatable and safe to branch on. Widening it later is an additive
    migration; a value is never repurposed.
    """

    STRING = "string", "String"
    INTEGER = "integer", "Integer"
    DECIMAL = "decimal", "Decimal"
    BOOLEAN = "boolean", "Boolean"
    DATE = "date", "Date"
    DATETIME = "datetime", "Datetime"
    UUID = "uuid", "UUID"
    JSON = "json", "JSON"


class DatasetLifecycleStatus(models.TextChoices):
    """
    Where a dataset sits in its life.

    Allowed transitions are enforced in `catalog.services.datasets`; the column itself only
    guarantees the value is one of these.
    """

    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    DEPRECATED = "deprecated", "Deprecated"
    ARCHIVED = "archived", "Archived"


class DatasetQuerySet(models.QuerySet):
    """Reusable dataset queries, kept on the manager so any caller can compose them."""

    def active(self):
        return self.filter(lifecycle_status=DatasetLifecycleStatus.ACTIVE)

    def editable(self):
        """Datasets that still accept writes -- everything that is not archived."""
        return self.exclude(lifecycle_status=DatasetLifecycleStatus.ARCHIVED)

    def containing_pii(self):
        return self.filter(data_elements__is_pii=True).distinct()

    def with_data_element_count(self):
        """
        Annotate `data_element_count` in one aggregate query.

        List responses expose the count instead of the elements themselves, so a client can
        show "Customer (12 fields)" without the endpoint fanning out into N+1 queries or
        shipping the full schema of every dataset on the page.
        """
        return self.annotate(data_element_count=models.Count("data_elements", distinct=True))


class Dataset(BaseModel):
    """A business entity whose structure this catalog describes."""

    name = models.CharField(
        max_length=100,
        help_text="Business entity name, e.g. 'Customer'. Unique, case-insensitively.",
    )
    description = models.TextField(
        blank=True,
        help_text="What this dataset represents and where it comes from.",
    )
    owner = models.CharField(
        max_length=150,
        blank=True,
        help_text="Team or person accountable for this dataset, e.g. 'growth-team'.",
    )
    lifecycle_status = models.CharField(
        max_length=20,
        choices=DatasetLifecycleStatus.choices,
        default=DatasetLifecycleStatus.DRAFT,
        db_index=True,
        help_text="Lifecycle stage. Archived datasets are read-only.",
    )
    retention_period_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "How long records of this dataset may be kept, in days. "
            "Null means no retention limit has been declared."
        ),
    )

    objects = models.Manager.from_queryset(DatasetQuerySet)()

    class Meta:
        verbose_name = "dataset"
        verbose_name_plural = "datasets"
        constraints = [
            # Two datasets called "Customer" and "customer" are the same dataset to every
            # human reading the catalog, so uniqueness is case-insensitive. A functional
            # unique index is what makes that true concurrently; checking in Python first
            # would still lose the race between two simultaneous creates.
            models.UniqueConstraint(
                Lower("name"),
                name="dataset_name_unique_ci",
                violation_error_message="A dataset with this name already exists.",
            ),
            models.CheckConstraint(
                condition=~models.Q(name=""),
                name="dataset_name_not_blank",
                violation_error_message="Dataset name cannot be blank.",
            ),
            # `choices` is validation, not storage: it is enforced by forms and by
            # `full_clean()`, but nothing stops `.update(lifecycle_status="banana")`.
            # The check constraint is what actually keeps the column trustworthy.
            models.CheckConstraint(
                condition=models.Q(lifecycle_status__in=DatasetLifecycleStatus.values),
                name="dataset_lifecycle_status_valid",
                violation_error_message="Unknown lifecycle status.",
            ),
            # `PositiveIntegerField` already excludes negatives; zero days is not a
            # retention policy, it is a mistake.
            models.CheckConstraint(
                condition=models.Q(retention_period_days__isnull=True)
                | models.Q(retention_period_days__gt=0),
                name="dataset_retention_period_positive",
                violation_error_message="Retention period must be a positive number of days.",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_archived(self) -> bool:
        return self.lifecycle_status == DatasetLifecycleStatus.ARCHIVED


class DataElementQuerySet(models.QuerySet):
    """Reusable data element queries."""

    def for_dataset(self, dataset: Dataset):
        return self.filter(dataset=dataset)

    def pii(self):
        return self.filter(is_pii=True)

    def of_type(self, data_type: str):
        return self.filter(data_type=data_type)


class DataElement(BaseModel):
    """A single named field within a dataset, e.g. `email` on `Customer`."""

    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name="data_elements",
        help_text="The dataset this element belongs to.",
    )
    name = models.CharField(
        max_length=100,
        help_text="Field name, e.g. 'email'. Unique within its dataset, case-insensitively.",
    )
    description = models.TextField(blank=True)
    data_type = models.CharField(
        max_length=20,
        choices=DataType.choices,
        help_text="Logical type of the value this element holds.",
    )
    max_length = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum length. Only meaningful for, and only allowed on, string elements.",
    )
    is_nullable = models.BooleanField(
        default=True,
        help_text="Whether this element may be absent on a record.",
    )
    is_primary_key = models.BooleanField(
        default=False,
        help_text="Whether this element identifies a record. At most one per dataset.",
    )
    is_pii = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this element holds personally identifiable information.",
    )

    objects = models.Manager.from_queryset(DataElementQuerySet)()

    class Meta:
        verbose_name = "data element"
        verbose_name_plural = "data elements"
        indexes = [
            # Covers the two queries this table exists to serve: "the elements of dataset
            # X" and, within that, "the PII ones".
            models.Index(fields=["dataset", "is_pii"], name="data_element_dataset_pii_idx"),
            models.Index(fields=["data_type"], name="data_element_data_type_idx"),
        ]
        constraints = [
            # Scoped to the dataset, not global: `Customer.email` and `Supplier.email` are
            # different elements and must both be allowed to exist.
            models.UniqueConstraint(
                "dataset",
                Lower("name"),
                name="data_element_name_unique_per_dataset",
                violation_error_message="This dataset already has a data element with this name.",
            ),
            # A partial unique index: unique across rows where `is_primary_key` is true,
            # unconstrained everywhere else. This is the whole rule "a dataset has at most
            # one primary key" expressed as a single index the database enforces.
            models.UniqueConstraint(
                fields=["dataset"],
                condition=models.Q(is_primary_key=True),
                name="data_element_single_primary_key_per_dataset",
                violation_error_message="This dataset already has a primary key data element.",
            ),
            models.CheckConstraint(
                condition=~models.Q(name=""),
                name="data_element_name_not_blank",
                violation_error_message="Data element name cannot be blank.",
            ),
            models.CheckConstraint(
                condition=models.Q(data_type__in=DataType.values),
                name="data_element_data_type_valid",
                violation_error_message="Unknown data type.",
            ),
            # Keeps type metadata coherent: a `max_length` on a boolean is meaningless, and
            # storing it anyway would leave consumers of this catalog guessing which
            # attributes apply to which type.
            models.CheckConstraint(
                condition=models.Q(max_length__isnull=True)
                | models.Q(data_type=DataType.STRING, max_length__gt=0),
                name="data_element_max_length_only_for_positive_length_strings",
                violation_error_message=(
                    "max_length is only allowed on string data elements, and must be positive."
                ),
            ),
            # An identifier that may be absent identifies nothing.
            models.CheckConstraint(
                condition=~models.Q(is_primary_key=True, is_nullable=True),
                name="data_element_primary_key_not_nullable",
                violation_error_message="A primary key data element cannot be nullable.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.dataset.name}.{self.name}"
