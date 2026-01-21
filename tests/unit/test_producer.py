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

    def test_publish_message_from_database_uses_select_for_update_with_skip_locked(self):
        Published.objects.create(destination="destination", body={"message": "test"}, status=StatusChoice.SCHEDULE)
        with patch.object(self.producer.published_class.objects, "select_for_update") as mock_select:
            mock_select.return_value.filter.return_value.values_list.return_value.__getitem__.return_value = []
            self.producer.publish_message_from_database()
            mock_select.assert_called_with(skip_locked=True)

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

        # Simulate another worker processing the message first
        message.status = StatusChoice.SUCCEEDED
        message.save()

        with patch.object(self.producer, "send") as mock_send:
            # Method should detect message was already processed and not call send()
            self.producer.publish_message_from_database()
            mock_send.assert_not_called()

    def test_concurrent_publishers_cannot_process_same_message(self):
        Published.objects.create(destination="destination", body={"message": "test1"}, status=StatusChoice.SCHEDULE)
        Published.objects.create(destination="destination", body={"message": "test2"}, status=StatusChoice.SCHEDULE)

        # Mock select_for_update to return empty result (simulating skip_locked behavior)
        with patch.object(self.producer.published_class.objects, "select_for_update") as mock_select:
            # Simulate that another publisher got the messages first
            mock_select.return_value.filter.return_value.values_list.return_value.__getitem__.return_value = []

            with patch.object(self.producer, "send") as mock_send:
                self.producer.publish_message_from_database()
                # Verify skip_locked=True was used (prevents concurrent access)
                mock_select.assert_called_with(skip_locked=True)
                # No messages should be sent since they were locked by other publishers
                mock_send.assert_not_called()

    def test_adaptive_waiting_strategy(self):
        # Mock sleep to avoid actual waiting and capture wait times
        with patch("django_outbox_pattern.producers.sleep") as mock_sleep:
            # Test progressive wait times with consecutive empty polls

            # First empty poll - should wait 1 second (default)
            self.producer._consecutive_empty_polls = 0
            self.producer._waiting()
            mock_sleep.assert_called_with(settings.DEFAULT_PRODUCER_WAITING_TIME)

            # 2nd-5th empty polls - should wait 3 seconds
            self.producer._consecutive_empty_polls = 3
            self.producer._waiting()
            mock_sleep.assert_called_with(settings.DEFAULT_PRODUCER_WAITING_TIME * 3)

            # 6th-10th empty polls - should wait 5 seconds
            self.producer._consecutive_empty_polls = 7
            self.producer._waiting()
            mock_sleep.assert_called_with(settings.DEFAULT_PRODUCER_WAITING_TIME * 5)

            # 10+ empty polls - should wait 10 seconds max
            self.producer._consecutive_empty_polls = 15
            self.producer._waiting()
            mock_sleep.assert_called_with(settings.DEFAULT_PRODUCER_WAITING_TIME * 10)

    def test_empty_polls_counter_increments_and_resets(self):
        # Start with no empty polls
        self.assertEqual(self.producer._consecutive_empty_polls, 0)

        # Mock to simulate no messages found
        with patch.object(self.producer.published_class.objects, "select_for_update") as mock_select:
            with patch("django_outbox_pattern.producers.sleep"):
                mock_select.return_value.filter.return_value.values_list.return_value.__getitem__.return_value = []

                # First empty poll
                self.producer.publish_message_from_database()
                self.assertEqual(self.producer._consecutive_empty_polls, 1)

                # Second empty poll
                self.producer.publish_message_from_database()
                self.assertEqual(self.producer._consecutive_empty_polls, 2)

        # Now simulate finding messages - counter should reset
        Published.objects.create(destination="destination", body={"message": "test"}, status=StatusChoice.SCHEDULE)

        with patch.object(self.producer, "send", return_value=0):
            with patch("django_outbox_pattern.producers.sleep"):
                self.producer.publish_message_from_database()

        # Counter should be reset to 0 after processing messages
        self.assertEqual(self.producer._consecutive_empty_polls, 0)
