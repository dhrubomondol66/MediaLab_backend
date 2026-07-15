from django.db import connection
from django.test import TestCase


class FeedSchemaTests(TestCase):
    def test_post_table_has_likes_count_column(self):
        with connection.cursor() as cursor:
            columns = {row[0] for row in connection.introspection.get_table_description(cursor, "feed_post")}

        self.assertIn("likes_count", columns)
