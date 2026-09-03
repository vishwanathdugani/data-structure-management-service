"""Pagination defaults shared by every list endpoint."""

from collections import OrderedDict

from rest_framework.pagination import LimitOffsetPagination as DRFLimitOffsetPagination
from rest_framework.response import Response


class LimitOffsetPagination(DRFLimitOffsetPagination):
    """
    Limit/offset pagination with a hard ceiling on page size.

    `max_limit` is the important part: without it a single `?limit=1000000` can pull an
    entire table into memory and serialize it. Every list endpoint in the service is
    paginated, including ones that look small today.
    """

    #: The response shape below is documented for OpenAPI by
    #: `api.v2.core.openapi.paginated_response`. Overriding DRF's
    #: `get_paginated_response_schema` here would be a second, silently diverging copy of
    #: the same structure: drf-spectacular never calls it for a plain `APIView`.
    default_limit = 25
    max_limit = 100
    limit_query_param = "limit"
    offset_query_param = "offset"

    def get_paginated_response(self, data) -> Response:
        return Response(
            OrderedDict(
                [
                    ("count", self.count),
                    ("limit", self.limit),
                    ("offset", self.offset),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )
