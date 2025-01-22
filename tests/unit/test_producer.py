from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase
from request_id_django_log import local_threading
from stomp.exception import StompException

from django_outbox_pattern import settings
from django_outbox_pattern.exceptions import ExceededSendAttemptsException
from django_outbox_pattern.factories import factory_producer
from django_outbox_pattern.models import Published


class ProducerTest(TestCase):
    def setUp(self):
        with patch("django_outbox_pattern.factories.factory_connection"):
            self.producer = factory_producer()

    def test_producer_send(self):
        published = Published.objects.create(destination="destination", body={"message": "Message test"})
        self.producer.start()
        self.producer.send(published)
        self.producer.stop()
        self.assertEqual(self.producer.connection.send.call_count, 1)
        self.assertTrue(published.headers is not None)

    def test_producer_send_should_add_correlation_id_header_from_current_request_id(self):
        request_id = str(uuid4())
        local_threading.request_id = request_id
        published = Published.objects.create(destination="destination", body={"message": "Message test"})
        self.producer.start()
        self.producer.send(published)
        self.producer.stop()
        self.assertEqual(self.producer.connection.send.call_count, 1)
        self.assertIsNotNone(published.headers)
        self.assertEqual(published.headers["dop-correlation-id"], request_id)

    def test_producer_send_with_header(self):
        headers = {"key": "value"}
        published = Published.objects.create(
            destination="destination", body={"message": "Message test"}, headers=headers
        )
        self.producer.start()
        self.producer.send(published)
        self.producer.stop()
        self.assertEqual(self.producer.connection.send.call_count, 1)
        self.assertTrue(published.headers is not None)
        self.assertEqual(published.headers["key"], headers["key"])

    def test_producer_send_event(self):
        self.producer.start()
        self.producer.send_event(destination="destination", body={"message": "Test send event"})
        self.producer.stop()
        self.assertEqual(self.producer.connection.send.call_count, 1)

    def test_producer_send_event_with_context_manager(self):
        with patch("django_outbox_pattern.factories.factory_connection"):
            with factory_producer() as producer:
                producer.send_event(destination="destination", body={"message": "Test send event"})
        self.assertEqual(producer.connection.send.call_count, 1)

    def test_producer_on_exceeded_send_attempts(self):
        settings.DEFAULT_WAIT_RETRY = 1
        settings.DEFAULT_PAUSE_FOR_RETRY = 1
        settings.DEFAULT_MAXIMUM_RETRY_ATTEMPTS = 5
        with patch.object(self.producer.connection, "send", side_effect=StompException()):
            published = Published.objects.create(destination="destination", body={"message": "Message test"})
            self.producer.start()
            with self.assertRaises(ExceededSendAttemptsException):
                self.producer.send(published)
            self.assertEqual(self.producer.connection.send.call_count, 5)

    def test_producer_successful_after_fail(self):
        settings.DEFAULT_MAXIMUM_RETRY_ATTEMPTS = 1
        with patch.object(self.producer.connection, "send", side_effect=StompException()):
            published = Published.objects.create(destination="destination", body={"message": "Message test 1"})
            self.producer.start()
            with self.assertRaises(ExceededSendAttemptsException):
                attempts = self.producer.send(published)
                self.assertEqual(attempts, 1)
                self.assertEqual(self.producer.connection.send.call_count, 1)
        published = Published.objects.create(destination="destination", body={"message": "Message test 2"})
        attempts = self.producer.send(published)
        self.assertEqual(attempts, 0)
        self.assertEqual(self.producer.connection.send.call_count, 1)

    def test_producer_not_started(self):
        self.producer.connection.is_connected = Mock(return_value=False)
        self.producer.stop()
        self.assertEqual(self.producer.connection.connect.call_count, 0)
