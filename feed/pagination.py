from rest_framework.pagination import CursorPagination

class FeedCursorPagination(CursorPagination):
    page_size = 10
    max_page_size = 50
    page_size_query_param = "page_size"
    ordering = ("-created_at", "-id")

class RepliesCursorPagination(FeedCursorPagination):
    ordering = ["-created_at", "id"]
    page_size = 20