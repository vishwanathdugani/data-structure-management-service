"""Serializer utilities shared across apps."""

from rest_framework import serializers


def create_serializer_class(*, name: str, fields: dict) -> type[serializers.Serializer]:
    """Build a `Serializer` subclass called `name` from a mapping of field name to field."""
    return type(name, (serializers.Serializer,), fields)


def inline_serializer(*, name: str, fields: dict, data=None, **kwargs):
    """
    Declare a nested serializer inline, at its point of use.

    A nested structure that is used by exactly one endpoint does not deserve a top-level
    class somewhere else in the file: defining it inline keeps the whole response shape
    readable in a single screen, with no jumping between definitions.

    `name` is not cosmetic -- it becomes the schema component name in the generated
    OpenAPI document, and therefore the type name in any client generated from it, so it
    should read like a type ("DatasetDataElementSerializer"), not like a variable.
    """
    serializer_class = create_serializer_class(name=name, fields=fields)

    if data is not None:
        return serializer_class(data=data, **kwargs)
    return serializer_class(**kwargs)
