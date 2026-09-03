"""The base class every view in the service inherits from."""

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import APIView


class BaseView(APIView):
    """
    A plain `APIView` plus the pagination helpers from DRF's generic views.

    We deliberately do *not* build on `ModelViewSet` / generic views. Those infer the
    queryset, the serializer, the filtering and the write behaviour from class attributes,
    which means the actual flow of a request is spread across half a dozen mixins and
    hooks. Handlers here read top to bottom -- validate, call a service or selector,
    serialize -- so what a route does is visible in the route.

    What we *do* borrow is pagination, because reimplementing `?limit=&offset=` per view
    would be pure duplication. The three members below are the pagination half of
    `GenericAPIView`, without the queryset machinery.
    """

    pagination_class = api_settings.DEFAULT_PAGINATION_CLASS

    @property
    def paginator(self):
        """The paginator instance for this view, or `None` if pagination is disabled."""
        if not hasattr(self, "_paginator"):
            self._paginator = None if self.pagination_class is None else self.pagination_class()
        return self._paginator

    def paginate_queryset(self, queryset):
        """Return one page of `queryset`, or `None` when pagination is disabled."""
        if self.paginator is None:
            return None
        return self.paginator.paginate_queryset(queryset, self.request, view=self)

    def get_paginated_response(self, data) -> Response:
        """Wrap already-serialized page data in the pagination envelope."""
        assert self.paginator is not None, "`get_paginated_response` needs a paginator."
        return self.paginator.get_paginated_response(data)

    def get_ordering(self, request: Request) -> list[str]:
        """
        Read repeatable `?ordering=` parameters in the order the client sent them.

        `getlist` (rather than `get`) is what makes multi-key sorting work:
        `?ordering=-is_pii&ordering=name` sorts by one, then the other.
        """
        return request.query_params.getlist("ordering")
