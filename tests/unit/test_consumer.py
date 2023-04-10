from unittest.mock import Mock
from unittest.mock import patch

from django.db import transaction
from django.test import TransactionTestCase
from stomp.exception import StompException

from django_outbox_pattern.choices import StatusChoice
from django_outbox_pattern.factories import factory_consumer
from django_outbox_pattern.payloads import Payload


class ConsumerTest(TransactionTestCase):
    def setUp(self):
        with patch("django_outbox_pattern.factories.factory_connection"):
            self.consumer = factory_consumer()

    def test_consumer_is_connect(self):
        self.consumer.is_connected()
        self.assertEqual(self.consumer.connection.is_connected.call_count, 1)

    def test_consumer_message_handler_should_save_message_when_save_is_executed_on_callback(self):
        self.consumer.callback = lambda p: p.save()
        self.consumer.message_handler('{"message": "message test"}', {"message-id": 1})
        self.assertEqual(self.consumer.received_class.objects.filter(status=StatusChoice.SUCCEEDED).count(), 1)
        message = self.consumer.received_class.objects.filter(status=StatusChoice.SUCCEEDED).first()
        self.assertEqual({"message": "message test"}, message.body)
        self.assertEqual({"message-id": 1}, message.headers)
        self.assertEqual("1", message.msg_id)

    def test_consumer_message_handler_should_print_warning_when_save_or_nack_is_not_executed_on_callback(self):
        self.consumer.callback = lambda p: p
        with self.assertLogs(level="WARNING") as log:
            self.consumer.message_handler('{"message": "message test"}', {"message-id": 2})
            self.assertEqual(len(log.output), 1)
            self.assertEqual(len(log.records), 1)
            self.assertIn(
                "The save or nack command was not executed, and the routine finished running without receiving an acknowledgement or a negative acknowledgement. message-id",  # noqa: E501 pylint: disable=C0301
                log.output[0],
            )
        self.assertEqual(self.consumer.received_class.objects.filter().count(), 0)

    def test_consumer_message_handler_should_not_save_message_when_have_a_exception_in_callback(self):
        def callback(payload: Payload):
            with transaction.atomic():
                payload.save()
                raise Exception("mocked")  # pylint: disable=broad-exception-raised

        with self.assertLogs(level="ERROR") as log:
            self.consumer.callback = callback
            self.consumer.message_handler('{"message": "message test"}', {"message-id": 1})
            self.assertEqual(self.consumer.received_class.objects.filter(status=StatusChoice.SUCCEEDED).count(), 0)
            self.assertEqual(len(log.output), 1)
            self.assertEqual(len(log.records), 1)
            self.assertIn("mocked", log.output[0])

        self.assertEqual(self.consumer.received_class.objects.filter().count(), 0)
        # assert no broker para garantir que a mensagem foi para dlq

    def test_consumer_message_handler_should_discard_duplicated_message(self):
        self.consumer.callback = lambda p: p.save()
        self.consumer.message_handler('{"message": "message test"}', {"message-id": 1})
        self.assertEqual(self.consumer.received_class.objects.filter(status=StatusChoice.SUCCEEDED).count(), 1)

        with self.assertLogs(level="INFO") as log:
            self.consumer.message_handler('{"message": "message test"}', {"message-id": 1})
            self.assertEqual(self.consumer.received_class.objects.filter(status=StatusChoice.SUCCEEDED).count(), 1)
            self.assertIn("Message with msg_id: 1 already exists. discarding the message", log.output[0])

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
