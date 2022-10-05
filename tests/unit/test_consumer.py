from unittest.mock import Mock
from unittest.mock import patch

from django.test import TestCase
from stomp.exception import StompException

from django_outbox_pattern.choices import StatusChoice
from django_outbox_pattern.factories import factory_consumer


class ConsumerTest(TestCase):
    def setUp(self):
        with patch("django_outbox_pattern.factories.factory_connection"):
            self.consumer = factory_consumer()
            self.consumer.received_class.objects.all().delete()

    def test_consumer_is_connect(self):
        self.consumer.is_connected()
        self.assertEqual(self.consumer.connection.is_connected.call_count, 1)

    def test_consumer_message_handler(self):
        self.consumer.callback = lambda p: p
        self.consumer.message_handler('{"message": "message test"}', {"message-id": 1})
        self.assertEqual(self.consumer.received_class.objects.filter(status=StatusChoice.SUCCEEDED).count(), 1)

    def test_consumer_message_handler_exception(self):
        self.consumer.callback = Mock(side_effect=Exception())
        self.consumer.message_handler('{"message": "message test"}', {})
        self.assertEqual(self.consumer.received_class.objects.filter(status=StatusChoice.FAILED).count(), 1)

    def test_consumer_start(self):
        self.consumer.connection.is_connected.side_effect = [False, True]
        self.consumer.start(lambda p: p, "/topic/destination.v1")
        self.assertEqual(self.consumer.connection.unsubscribe.call_count, 1)
        self.assertEqual(self.consumer.connection.subscribe.call_count, 2)
        self.assertEqual(self.consumer.connection.connect.call_count, 1)

    def test_consumer_start_with_stomp_exception(self):
        self.consumer.connection.is_connected = Mock(side_effect=[False, True])
        self.consumer.connection.connect = Mock(side_effect=StompException())
        self.consumer.start(lambda p: p, "/topic/destination.v2")
        self.assertEqual(self.consumer.connection.connect.call_count, 1)
        self.assertEqual(self.consumer.connection.is_connected.call_count, 2)

    def test_consumer_stop(self):
        self.consumer.connection.is_connected.side_effect = [False, True, True]
        self.consumer.start(lambda p: p, "/topic/destination.v3")
        self.consumer.stop()
        self.assertEqual(self.consumer.connection.is_connected.call_count, 3)
        self.assertEqual(self.consumer.connection.unsubscribe.call_count, 2)
        self.assertEqual(self.consumer.connection.disconnect.call_count, 1)

    def test_consumer_message_handler_with_invalid_message(self):
        self.consumer.callback = Mock(side_effect=Exception())
        body_format_invalid = '{"message": "message with format invalid",}'
        with self.assertLogs() as captured:
            self.consumer.message_handler(body_format_invalid, {})
        self.assertIn("Expecting property name enclosed in double quotes", captured.records[0].getMessage())
