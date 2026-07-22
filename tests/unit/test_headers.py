from django.test import TestCase

from django_outbox_pattern.headers import get_message_headers
from django_outbox_pattern.models import Published


class GetMessageHeadersTest(TestCase):
    def test_should_override_dop_correlation_id_given_custom_header(self):
        published = Published.objects.create(
            destination="destination",
            body={"message": "test"},
            headers={"dop-correlation-id": "custom-id"},
        )

        headers = get_message_headers(published)

        self.assertEqual(headers["dop-correlation-id"], "custom-id")

    def test_should_not_override_dop_msg_id_given_custom_header_with_same_key(self):
        published = Published.objects.create(
            destination="destination",
            body={"message": "test"},
            headers={"dop-msg-id": "colliding-fixed-id"},
        )

        headers = get_message_headers(published)

        self.assertEqual(headers["dop-msg-id"], str(published.id))

    def test_should_keep_custom_header_given_key_not_present_in_defaults(self):
        published = Published.objects.create(
            destination="destination",
            body={"message": "test"},
            headers={"key": "value"},
        )

        headers = get_message_headers(published)

        self.assertEqual(headers["key"], "value")
