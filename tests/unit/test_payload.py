from unittest.mock import MagicMock

from django.test import TestCase

from django_outbox_pattern.models import Received
from django_outbox_pattern.payloads import Payload


class PayloadTest(TestCase):
    def test_should_change_payload_saved_to_true_when_save_is_called(self):
        payload = Payload(None, None, None, Received())
        payload.save()
        self.assertTrue(payload.saved)

    def test_should_change_payload_acked_to_true_when_ack_is_called(self):
        mock_connection = MagicMock()
        message_id = "1"
        payload = Payload(mock_connection, None, {"message-id": message_id}, Received())
        payload.ack()
        self.assertTrue(payload.acked)
        mock_connection.ack.assert_called_once_with(message_id)

    def test_should_change_payload_nacked_to_true_when_nack_is_called(self):
        mock_connection = MagicMock()
        message_id = "1"
        payload = Payload(mock_connection, None, {"message-id": message_id}, Received())
        payload.nack()
        self.assertTrue(payload.nacked)
        mock_connection.nack.assert_called_once_with(message_id, requeue=False)

    def test_should_not_call_ack_twice(self):
        mock_connection = MagicMock()
        message_id = "1"
        payload = Payload(mock_connection, None, {"message-id": message_id}, Received())
        payload.ack()
        payload.ack()
        self.assertTrue(payload.acked)
        mock_connection.ack.assert_called_once_with(message_id)

    def test_should_not_call_nack_twice(self):
        mock_connection = MagicMock()
        message_id = "1"
        payload = Payload(mock_connection, None, {"message-id": message_id}, Received())
        payload.nack()
        payload.nack()
        self.assertTrue(payload.nacked)
        mock_connection.nack.assert_called_once_with(message_id, requeue=False)

    def test_should_not_call_ack_when_nack_was_called(self):
        mock_connection = MagicMock()
        message_id = "1"
        payload = Payload(mock_connection, None, {"message-id": message_id}, Received())
        payload.nack()
        payload.ack()
        self.assertTrue(payload.nacked)
        mock_connection.nack.assert_called_once_with(message_id, requeue=False)
        mock_connection.ack.assert_not_called()

    def test_should_not_call_nack_when_ack_was_called(self):
        mock_connection = MagicMock()
        message_id = "1"
        payload = Payload(mock_connection, None, {"message-id": message_id}, Received())
        payload.ack()
        payload.nack()
        self.assertTrue(payload.acked)
        mock_connection.ack.assert_called_once_with(message_id)
        mock_connection.nack.assert_not_called()
