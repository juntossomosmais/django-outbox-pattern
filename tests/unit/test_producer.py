from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase
from django.test import TransactionTestCase
from request_id_django_log import local_threading
from stomp.exception import StompException

from django_outbox_pattern import settings
from django_outbox_pattern.choices import StatusChoice
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

    def test_publish_message_from_database_processes_messages_individually(self):
        message1 = Published.objects.create(
            destination="destination", body={"message": "test1"}, status=StatusChoice.SCHEDULE
        )
        message2 = Published.objects.create(
            destination="destination", body={"message": "test2"}, status=StatusChoice.SCHEDULE
        )

        with patch.object(self.producer, "send", return_value=0) as mock_send:
            self.producer.publish_message_from_database()

        self.assertEqual(mock_send.call_count, 2)
        message1.refresh_from_db()
        message2.refresh_from_db()
        self.assertEqual(message1.status, StatusChoice.SUCCEEDED)
        self.assertEqual(message2.status, StatusChoice.SUCCEEDED)


class ProducerRaceConditionTest(TransactionTestCase):
    def setUp(self):
        with patch("django_outbox_pattern.factories.factory_connection"):
            self.producer = factory_producer()

    def test_double_check_status_prevents_reprocessing(self):
        message = Published.objects.create(
            destination="destination", body={"message": "test"}, status=StatusChoice.SCHEDULE
        )

        # Simulate message being processed by another worker between queries
        with patch.object(self.producer.published_class.objects, "filter") as mock_filter:
            mock_queryset = Mock()
            mock_queryset.exists.return_value = True  # Pass the exists() check
            # Create a message that appears processed when we check its status
            processed_message = Published(id=message.id, status=StatusChoice.SUCCEEDED)
            mock_queryset.select_for_update.return_value.iterator.return_value = iter([processed_message])
            mock_filter.return_value = mock_queryset

            with patch.object(self.producer, "send") as mock_send:
                # Method should detect message was already processed via double-check
                self.producer.publish_message_from_database()
                mock_send.assert_not_called()

    def test_concurrent_publishers_cannot_process_same_message(self):
        Published.objects.create(destination="destination", body={"message": "test"}, status=StatusChoice.SCHEDULE)

        # Mock the chained select_for_update().iterator() call
        with patch.object(self.producer.published_class.objects, "filter") as mock_filter:
            mock_queryset = Mock()
            mock_queryset.exists.return_value = True  # Pass the exists() check
            mock_queryset.select_for_update.return_value.iterator.return_value = iter([])  # No messages available
            mock_filter.return_value = mock_queryset

            with patch.object(self.producer, "send") as mock_send:
                self.producer.publish_message_from_database()
                # Verify select_for_update was called with skip_locked=True
                mock_queryset.select_for_update.assert_called_once_with(skip_locked=True)
                # Verify iterator was called with chunk_size
                mock_queryset.select_for_update.return_value.iterator.assert_called_once_with(
                    chunk_size=settings.DEFAULT_PUBLISHED_CHUNK_SIZE
                )
                # No messages should be sent since skip_locked skipped them
                mock_send.assert_not_called()

    def test_queryset_locking_uses_select_for_update_with_skip_locked(self):
        """Test that select_for_update with skip_locked is used on the queryset with iterator"""
        message = Published.objects.create(
            destination="destination", body={"message": "test"}, status=StatusChoice.SCHEDULE
        )

        # Mock the queryset select_for_update method directly
        with patch.object(self.producer.published_class.objects, "filter") as mock_filter:
            mock_queryset = Mock()
            mock_queryset.exists.return_value = True  # Pass the exists() check
            mock_queryset.select_for_update.return_value.iterator.return_value = iter([message])
            mock_filter.return_value = mock_queryset

            with patch.object(self.producer, "send", return_value=0):
                self.producer.publish_message_from_database()

            # Verify select_for_update was called with skip_locked=True
            mock_queryset.select_for_update.assert_called_once_with(skip_locked=True)
            # Verify iterator was called with chunk_size
            mock_queryset.select_for_update.return_value.iterator.assert_called_once_with(
                chunk_size=settings.DEFAULT_PUBLISHED_CHUNK_SIZE
            )
