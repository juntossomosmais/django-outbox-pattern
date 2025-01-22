from uuid import uuid4

from django.test import TransactionTestCase
from request_id_django_log import local_threading

from django_outbox_pattern.models import Published
from django_outbox_pattern.models import Received


class ReceivedTest(TransactionTestCase):
    def test_received_should_return_destination_empty_when_object_have_headers_none(self):
        received = Received()
        self.assertEqual("", received.destination)

    def test_received_should_return_destination_value_when_have_headers(self):
        received = Received(headers={"destination": "fake"})
        self.assertEqual("fake", received.destination)

    def test_received_should_return_destination_empty_when_object_have_headers_but_without_key_destination(self):
        received = Received(headers={"fake": "fake"})
        self.assertEqual("", received.destination)


class PublishedTest(TransactionTestCase):

    def test_published_should_add_correlation_id_header_from_current_request_id(self):
        request_id = str(uuid4())
        local_threading.request_id = request_id
        published = Published.objects.create(destination="destination", body={"message": "Message test"})
        self.assertEqual(published.headers["dop-correlation-id"], request_id)

    def test_published_should_not_add_correlation_id_given_custom_header(self):
        request_id = str(uuid4())
        local_threading.request_id = request_id
        published = Published.objects.create(
            destination="destination", body={"message": "Message test"}, headers={"custom": "xpto-lalala"}
        )
        self.assertNotIn("dop-correlation-id", published.headers)
