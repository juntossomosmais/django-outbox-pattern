from django.test import TransactionTestCase

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
