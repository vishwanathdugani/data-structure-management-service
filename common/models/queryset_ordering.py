"""
Declarative, whitelist-based queryset ordering.

Ordering comes from user input (`?ordering=-created_at`), so it can never be passed to
`QuerySet.order_by()` directly: that would expose every column and every relation on the
model, including columns we deliberately do not publish. Instead each endpoint declares an
`OrderingService` listing exactly which public names are orderable and what each one maps
to in the database.

    class DatasetOrderingService(ordering.OrderingService):
        name = ordering.StringField()
        created_at = ordering.DateTimeField()

        _defaults = ("-created_at",)

    queryset = DatasetOrderingService.order_queryset(queryset, ["-name"])

Adding a new sortable field is one line; nothing else in the stack changes. The service
also appends a deterministic tiebreaker, see `order_queryset`.
"""

from collections.abc import Iterable, Sequence

from django.db import models
from django.db.models.expressions import OrderBy
from django.db.models.functions import Lower

from common.exceptions import ValidationError


class OrderingField:
    """
    One orderable public name.

    `source` maps the public name onto a different model field or relation lookup, so the
    API contract does not have to follow the database schema (for example
    `owner = StringField(source="owning_team__name")`).

    Nulls sort last in both directions by default. That is almost always what a human
    means by "sort by retention period": rows without a value belong at the end, not
    bunched at the top of the descending page.
    """

    def __init__(self, *, source: str | None = None, nulls_last: bool = True):
        self.source = source
        self.nulls_last = nulls_last
        self.name: str | None = None

    def bind(self, name: str) -> None:
        """Called when the field is collected onto its `OrderingService`."""
        self.name = name
        if self.source is None:
            self.source = name

    def get_expression(self, *, descending: bool) -> OrderBy:
        expression = self.get_source_expression()
        if descending:
            return expression.desc(nulls_last=self.nulls_last)
        return expression.asc(nulls_last=self.nulls_last)

    def get_source_expression(self) -> models.Expression | models.F:
        return models.F(self.source)


class StringField(OrderingField):
    """
    Orders text case-insensitively.

    Without this, a plain column sort puts every capitalised value before every lowercase
    one ("Order" < "customer"), which reads as broken to anyone looking at the list.
    """

    def get_source_expression(self) -> models.Expression:
        return Lower(self.source)


class NumberField(OrderingField):
    """Orders a numeric column."""


class BooleanField(OrderingField):
    """Orders a boolean column. Ascending puts `false` first."""


class DateTimeField(OrderingField):
    """Orders a date or datetime column."""


class OrderingService:
    """
    Base class for per-endpoint ordering declarations.

    Subclasses declare `OrderingField` attributes and a `_defaults` tuple that is applied
    when the caller asks for no ordering at all.
    """

    #: Ordering tokens applied when the caller supplies none, e.g. ``("-created_at",)``.
    _defaults: Sequence[str] = ()

    #: Populated by `__init_subclass__`; maps public name -> field.
    _fields: dict[str, OrderingField] = {}

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        fields: dict[str, OrderingField] = {}
        # Walk the MRO in reverse so that a subclass can override an inherited field.
        for klass in reversed(cls.__mro__):
            for name, value in vars(klass).items():
                if isinstance(value, OrderingField):
                    value.bind(name)
                    fields[name] = value
        cls._fields = fields

        # Fail at import time rather than at request time on a typo in `_defaults`.
        for token in cls._defaults:
            if token.lstrip("-") not in fields:
                raise ValueError(
                    f"{cls.__name__}._defaults refers to unknown ordering field {token!r}."
                )

    @classmethod
    def allowed_fields(cls) -> list[str]:
        return sorted(cls._fields)

    @classmethod
    def order_queryset(cls, queryset: models.QuerySet, ordering: Iterable[str] | None):
        """
        Apply `ordering` to `queryset`.

        `ordering` is a list of public field names, optionally prefixed with `-` for
        descending, in priority order. Unknown names raise a `ValidationError` rather than
        being silently dropped: a client that misspells a field should be told, not handed
        a differently-sorted page that looks plausible.

        A primary-key tiebreaker is always appended. Sorting by a non-unique column such as
        `name` leaves rows with equal values in an order the database is free to change
        between queries, which makes LIMIT/OFFSET pagination silently repeat or skip rows.
        """
        tokens = [token.strip() for token in (ordering or []) if token and token.strip()]
        if not tokens:
            tokens = list(cls._defaults)

        expressions: list[OrderBy] = []
        seen: set[str] = set()

        for token in tokens:
            descending = token.startswith("-")
            name = token.removeprefix("-")

            field = cls._fields.get(name)
            if field is None:
                raise ValidationError(
                    f"Cannot order by {name!r}.",
                    extra={"ordering": {"allowed": cls.allowed_fields()}},
                )

            # First occurrence wins; a repeated column would be ignored by SQL anyway.
            if name in seen:
                continue
            seen.add(name)

            expressions.append(field.get_expression(descending=descending))

        expressions.append(models.F("pk").desc())
        return queryset.order_by(*expressions)
