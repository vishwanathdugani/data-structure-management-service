"""Tests for `inline_serializer`."""

from rest_framework import serializers

from api.v2.core.serializers import create_serializer_class, inline_serializer


class TestCreateSerializerClass:
    def test_builds_a_named_serializer_class(self):
        serializer_class = create_serializer_class(
            name="ExampleSerializer",
            fields={"count": serializers.IntegerField()},
        )

        assert issubclass(serializer_class, serializers.Serializer)
        # The name drives the OpenAPI component name, and therefore generated client types.
        assert serializer_class.__name__ == "ExampleSerializer"


class TestInlineSerializer:
    def test_serializes_an_object(self):
        serializer = inline_serializer(
            name="ExampleSerializer",
            fields={"count": serializers.IntegerField()},
            instance={"count": 3},
        )

        assert serializer.data == {"count": 3}

    def test_validates_input_when_given_data(self):
        serializer = inline_serializer(
            name="ExampleSerializer",
            fields={"count": serializers.IntegerField()},
            data={"count": "7"},
        )

        assert serializer.is_valid()
        assert serializer.validated_data == {"count": 7}

    def test_reports_invalid_input(self):
        serializer = inline_serializer(
            name="ExampleSerializer",
            fields={"count": serializers.IntegerField()},
            data={"count": "not a number"},
        )

        assert not serializer.is_valid()
        assert "count" in serializer.errors

    def test_supports_many(self):
        serializer = inline_serializer(
            name="ExampleSerializer",
            fields={"count": serializers.IntegerField()},
            many=True,
            instance=[{"count": 1}, {"count": 2}],
        )

        assert serializer.data == [{"count": 1}, {"count": 2}]
