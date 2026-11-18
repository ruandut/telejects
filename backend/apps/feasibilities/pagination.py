"""DRF paging for a run's sites: ?page= and ?page_size= (20, 50, 100 or 200)."""

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class ForgivingPaginator(Paginator):
    """A page past the end (a filter or live update shrank the list) is the last page, and a
    page that isn't a number is the first, rather than a 404."""

    def page(self, number):
        try:
            number = self.validate_number(number)
        except PageNotAnInteger:
            number = 1
        except EmptyPage:
            number = 1 if int(number) < 1 else self.num_pages
        return super().page(number)


class SitePagination(PageNumberPagination):
    page_sizes = (20, 50, 100, 200)
    page_size = page_sizes[0]
    page_size_query_param = "page_size"
    max_page_size = page_sizes[-1]
    django_paginator_class = ForgivingPaginator

    def get_page_size(self, request):
        """Only the sizes offered: anything else is the default, not the nearest allowed."""
        asked = request.query_params.get(self.page_size_query_param, "")
        return int(asked) if asked in {str(size) for size in self.page_sizes} else self.page_size

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "page": self.page.number,
                "page_size": self.page.paginator.per_page,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema):
        response = super().get_paginated_response_schema(schema)
        response["properties"] |= {"page": {"type": "integer"}, "page_size": {"type": "integer"}}
        return response
