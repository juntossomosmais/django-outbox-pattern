from unittest.mock import Mock
from unittest.mock import patch

from django.test import TestCase
from django.test import override_settings
from stomp.exception import StompException

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
        self.assertEqual(self.producer.connection.send.call_count, 1)

    @override_settings(
        DJANGO_OUTBOX_PATTERN={
            "DEFAULT_WAIT_RETRY": 1,
            "DEFAULT_PAUSE_FOR_RETRY": 1,
            "DEFAULT_MAXIMUM_RETRY_ATTEMPTS": 5,
        }
    )
    def test_producer_on_exceeded_send_attempts(self):
        with patch.object(self.producer.connection, "send", side_effect=StompException()):
            published = Published.objects.create(destination="destination", body={"message": "Message test"})
            self.producer.start()
            with self.assertRaises(ExceededSendAttemptsException):
                self.producer.send(published)
            self.assertEqual(self.producer.connection.send.call_count, 5)

    @override_settings(
        DJANGO_OUTBOX_PATTERN={
            "DEFAULT_MAXIMUM_RETRY_ATTEMPTS": 1,
        }
    )
    def test_producer_successful_after_fail(self):
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
