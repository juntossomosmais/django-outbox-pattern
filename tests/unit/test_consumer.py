from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

from django.db import transaction
from django.test import SimpleTestCase
from django.test import TransactionTestCase
from request_id_django_log import local_threading
from stomp.exception import StompException

from django_outbox_pattern.choices import StatusChoice
from django_outbox_pattern.consumers import _get_or_create_correlation_id
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
        self.consumer.message_handler('{"message": "my message"}', {"message-id": 1})
        self.assertEqual(self.consumer.received_class.objects.filter(status=StatusChoice.SUCCEEDED).count(), 1)
        message = self.consumer.received_class.objects.filter(status=StatusChoice.SUCCEEDED).first()
        self.assertEqual({"message": "my message"}, message.body)
        self.assertEqual({"message-id": 1}, message.headers)
        self.assertEqual("1", message.msg_id)

    def test_consumer_message_handler_should_print_warning_when_save_or_nack_is_not_executed_on_callback(self):
        self.consumer.callback = lambda p: p
        with self.assertLogs(level="WARNING") as log:
            self.consumer.message_handler('{"message": "mocked"}', {"message-id": 2})
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
                raise StompException("mocked")

        with self.assertLogs(level="ERROR") as log:
            self.consumer.callback = callback
            self.consumer.message_handler('{"message": "mock message"}', {"message-id": 1})
            self.assertEqual(self.consumer.received_class.objects.filter(status=StatusChoice.SUCCEEDED).count(), 0)
            self.assertEqual(len(log.output), 1)
            self.assertEqual(len(log.records), 1)
            self.assertIn("mocked", log.output[0])

        self.assertEqual(self.consumer.received_class.objects.filter().count(), 0)

    def test_consumer_message_handler_should_discard_duplicated_message(self):
        message_body = '{"message": "message test"}'
        self.consumer.callback = lambda p: p.save()
        self.consumer.message_handler(message_body, {"message-id": 1})
        self.assertEqual(self.consumer.received_class.objects.filter(status=StatusChoice.SUCCEEDED).count(), 1)

        with self.assertLogs(level="INFO") as log:
            self.consumer.message_handler(message_body, {"message-id": 1})
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

    def test_consumer_start_with_correct_headers(self):
        self.consumer.connection.is_connected.side_effect = [False, True]
        self.consumer.start(lambda p: p, "/topic/destination.v1")
        self.assertIn("exclusive", self.consumer.subscribe_headers)
        self.assertIn("x-queue-name", self.consumer.subscribe_headers)
        self.assertIn("x-dead-letter-routing-key", self.consumer.subscribe_headers)
        self.assertIn("x-dead-letter-exchange", self.consumer.subscribe_headers)

    def test_consumer_message_handler_should_add_correlation_id_from_header_into_local_threading(self):
        self.consumer.callback = lambda p: p.save()

        self.consumer.message_handler('{"message": "my message"}', {"message-id": 1, "dop-correlation-id": "1234"})

        self.assertEqual(self.consumer.received_class.objects.filter(status=StatusChoice.SUCCEEDED).count(), 1)
        message = self.consumer.received_class.objects.filter(status=StatusChoice.SUCCEEDED).first()
        self.assertEqual({"message": "my message"}, message.body)
        self.assertEqual({"message-id": 1, "dop-correlation-id": "1234"}, message.headers)
        self.assertEqual("1", message.msg_id)
        self.assertIsNone(local_threading.request_id)


class GetOrCreateCorrelationIdTest(SimpleTestCase):

    def test_should_return_correlation_id_from_headers(self):
        headers = {"dop-correlation-id": "1234"}
        with patch(f"{_get_or_create_correlation_id.__module__}.uuid4", wraps=uuid4) as uuid4_spy:
            self.assertEqual("1234", _get_or_create_correlation_id(headers))
            uuid4_spy.assert_not_called()

        self.assertEqual("1234", _get_or_create_correlation_id(headers))

    def test_should_create_a_new_correlation_id_given_header_without_correlation_id(self) -> None:
        headers: dict = {}
        with patch(f"{_get_or_create_correlation_id.__module__}.uuid4", wraps=uuid4) as uuid4_spy:
            self.assertIsNotNone(_get_or_create_correlation_id(headers))
            uuid4_spy.assert_called_once()


class ConsumerBackgroundProcessingTest(SimpleTestCase):
    def setUp(self):
        # Patch out the real connection creation so factory_consumer doesn't try to reach a broker
        self.factory_conn_patcher = patch("django_outbox_pattern.factories.factory_connection")
        self.factory_conn_patcher.start()

    def tearDown(self):
        self.factory_conn_patcher.stop()

    def test_handle_incoming_message_sync_when_background_disabled(self):
        with patch("django_outbox_pattern.settings.DEFAULT_CONSUMER_PROCESS_MSG_ON_BACKGROUND", False):
            from django_outbox_pattern.factories import factory_consumer

            consumer = factory_consumer()
            # Protect against accidental submit usage
            consumer._pool_executor = Mock()
            consumer._pool_executor.submit = Mock()
            consumer.message_handler = Mock()

            body = "{}"
            headers = {"message-id": "m1"}
            consumer.handle_incoming_message(body, headers)

            consumer.message_handler.assert_called_once_with(body, headers)
            consumer._pool_executor.submit.assert_not_called()

    def test_handle_incoming_message_background_enabled_submits(self):
        with patch("django_outbox_pattern.settings.DEFAULT_CONSUMER_PROCESS_MSG_ON_BACKGROUND", True):
            from django_outbox_pattern.factories import factory_consumer

            consumer = factory_consumer()
            consumer.message_handler = Mock()
            consumer._pool_executor = Mock()
            consumer._pool_executor.submit = Mock()

            body = "{\"k\": 1}"
            headers = {"message-id": "m2"}
            consumer.handle_incoming_message(body, headers)

            consumer._pool_executor.submit.assert_called_once()
            # Ensure it is submitting the message_handler with the same args
            submit_args, submit_kwargs = consumer._pool_executor.submit.call_args
            self.assertEqual(submit_args[0], consumer.message_handler)
            self.assertEqual(submit_args[1], body)
            self.assertEqual(submit_args[2], headers)
            consumer.message_handler.assert_not_called()

    def test_submit_runtimeerror_recreates_executor_and_submits(self):
        with patch("django_outbox_pattern.settings.DEFAULT_CONSUMER_PROCESS_MSG_ON_BACKGROUND", True):
            from django_outbox_pattern.factories import factory_consumer

            consumer = factory_consumer()
            # First executor raises RuntimeError when submitting
            first_exec = Mock()
            first_exec.submit = Mock(side_effect=RuntimeError())
            # Replace consumer's pool executor with our first mock
            consumer._pool_executor = first_exec

            # New executor to be returned by _create_new_worker_executor
            new_exec = Mock()
            new_exec.submit = Mock()
            with patch.object(consumer, "_create_new_worker_executor", return_value=new_exec) as create_exec_spy:
                body = "{\"k\": 2}"
                headers = {"message-id": "m3"}
                consumer.handle_incoming_message(body, headers)

                create_exec_spy.assert_called_once()
                new_exec.submit.assert_called_once()
                submit_args, _ = new_exec.submit.call_args
                self.assertEqual(submit_args[0], consumer.message_handler)
                self.assertEqual(submit_args[1], body)
                self.assertEqual(submit_args[2], headers)

    def test_stop_shuts_down_executor(self):
        from django_outbox_pattern.factories import factory_consumer

        consumer = factory_consumer()
        consumer._pool_executor = Mock()
        consumer._pool_executor.shutdown = Mock()

        # Ensure stop calls shutdown regardless of connection status
        consumer.stop()
        consumer._pool_executor.shutdown.assert_called_once_with(wait=False)


class ConsumerListenerRoutingTest(SimpleTestCase):
    def setUp(self):
        self.factory_conn_patcher = patch("django_outbox_pattern.factories.factory_connection")
        self.factory_conn_patcher.start()

    def tearDown(self):
        self.factory_conn_patcher.stop()

    def test_listener_on_message_routes_to_handle_incoming_message(self):
        from django_outbox_pattern.factories import factory_consumer
        from django_outbox_pattern.listeners import ConsumerListener

        consumer = factory_consumer()
        consumer.subscribe_id = "sub-123"
        consumer.handle_incoming_message = Mock()

        frame = Mock()
        frame.body = "{}"
        frame.headers = {"message-id": "m4", "subscription": "sub-123"}

        listener = ConsumerListener(consumer)
        listener.on_message(frame)

        consumer.handle_incoming_message.assert_called_once_with(frame.body, frame.headers)
