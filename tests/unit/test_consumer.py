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
        # Provide enough values for all the is_connected calls during start and stop
        self.consumer.connection.is_connected.side_effect = [False, True, True, True, True]
        self.consumer.start(lambda p: p, "/topic/destination.v3")
        self.consumer.stop()
        self.assertGreaterEqual(self.consumer.connection.is_connected.call_count, 3)
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

            body = '{"k": 1}'
            headers = {"message-id": "m2"}
            consumer.handle_incoming_message(body, headers)

            consumer._pool_executor.submit.assert_called_once()
            # Ensure it is submitting the message_handler with the same args
            submit_args, _submit_kwargs = consumer._pool_executor.submit.call_args
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
                body = '{"k": 2}'
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
        consumer._pool_executor.shutdown.assert_called_once_with(wait=True, cancel_futures=False)


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


class ConsumerHeartbeatThreadingTest(SimpleTestCase):
    def setUp(self):
        # Avoid real broker connections
        self.factory_conn_patcher = patch("django_outbox_pattern.factories.factory_connection")
        self.factory_conn_patcher.start()

    def tearDown(self):
        self.factory_conn_patcher.stop()

    def test_slow_callback_does_not_block_heartbeat_thread(self):
        import threading
        import time

        HEARTBEAT_INTERVAL = 0.05  # 50ms
        SLOW_CALLBACK_SLEEP = HEARTBEAT_INTERVAL * 3  # sleep longer than heartbeat

        with patch("django_outbox_pattern.settings.DEFAULT_CONSUMER_PROCESS_MSG_ON_BACKGROUND", True):
            from django_outbox_pattern.factories import factory_consumer

            consumer = factory_consumer()

            # Event to signal callback completion, capture info holder
            done_event = threading.Event()
            callback_thread_name = {"value": None}

            def slow_handler(body, headers):  # simulate internal message_handler workload
                callback_thread_name["value"] = threading.current_thread().name
                time.sleep(SLOW_CALLBACK_SLEEP)
                done_event.set()

            # Route background task to our slow handler
            consumer.message_handler = slow_handler

            # Heartbeat ticker that must keep running while callback sleeps
            hb_ticks = {"count": 0}
            hb_stop = threading.Event()

            def heartbeat():
                while not hb_stop.is_set():
                    hb_ticks["count"] += 1
                    time.sleep(HEARTBEAT_INTERVAL)

            hb_thread = threading.Thread(target=heartbeat, name="heartbeat-thread", daemon=True)
            hb_thread.start()

            # Invoke processing; should submit to ThreadPool and return quickly
            body = "{}"
            headers = {"message-id": "m-heartbeat"}
            consumer.handle_incoming_message(body, headers)
            # Immediately after, callback shouldn't be done
            self.assertFalse(done_event.is_set())

            # Wait a bit to allow some heartbeat iterations while callback sleeps
            time.sleep(HEARTBEAT_INTERVAL * 2)
            self.assertGreaterEqual(hb_ticks["count"], 2, "Heartbeat should have ticked while callback sleeps")

            # Wait for callback to finish
            self.assertTrue(done_event.wait(timeout=SLOW_CALLBACK_SLEEP * 2), "Callback did not finish in time")

            # Stop heartbeat and ensure thread made progress past callback duration as well
            hb_stop.set()
            hb_thread.join(timeout=1)
            self.assertTrue(hb_ticks["count"] >= 2)

            # Verify callback executed on a worker thread (ThreadPoolExecutor uses listener_name as prefix)
            self.assertIsNotNone(callback_thread_name["value"])
            self.assertTrue(
                callback_thread_name["value"].startswith(consumer.listener_name),
                f"Callback should run on worker thread prefixed by listener_name, got {callback_thread_name['value']}",
            )


class ConsumerHeartbeatThreadingSyncTest(SimpleTestCase):
    def setUp(self):
        # Avoid real broker connections
        self.factory_conn_patcher = patch("django_outbox_pattern.factories.factory_connection")
        self.factory_conn_patcher.start()

    def tearDown(self):
        self.factory_conn_patcher.stop()

    def test_slow_sync_callback_blocks_current_thread_and_raises(self):
        import threading
        import time

        HEARTBEAT_INTERVAL = 0.05  # 50ms
        SLOW_CALLBACK_SLEEP = HEARTBEAT_INTERVAL * 3  # sleep longer than heartbeat

        with patch("django_outbox_pattern.settings.DEFAULT_CONSUMER_PROCESS_MSG_ON_BACKGROUND", False):
            from django_outbox_pattern.factories import factory_consumer

            consumer = factory_consumer()
            # Ensure background pool isn't used
            consumer._pool_executor = Mock()
            consumer._pool_executor.submit = Mock()

            callback_thread_name = {"value": None}

            def slow_and_raise(body, headers):
                callback_thread_name["value"] = threading.current_thread().name
                time.sleep(SLOW_CALLBACK_SLEEP)
                raise RuntimeError("sync boom")

            consumer.message_handler = slow_and_raise

            # Heartbeat ticker that must keep running while callback sleeps
            hb_ticks = {"count": 0}
            hb_stop = threading.Event()

            def heartbeat():
                while not hb_stop.is_set():
                    hb_ticks["count"] += 1
                    time.sleep(HEARTBEAT_INTERVAL)

            hb_thread = threading.Thread(target=heartbeat, name="heartbeat-thread", daemon=True)
            hb_thread.start()

            current_thread_name = threading.current_thread().name

            # Because background is disabled, this call should block and then raise
            t0 = time.time()
            with self.assertRaises(RuntimeError):
                consumer.handle_incoming_message("{}", {"message-id": "m-sync-heartbeat"})
            elapsed = time.time() - t0

            # ensure it blocked roughly at least the slow duration
            self.assertGreaterEqual(elapsed, SLOW_CALLBACK_SLEEP * 0.9)

            # Stop heartbeat and ensure it ticked during the blocking call
            hb_stop.set()
            hb_thread.join(timeout=1)
            self.assertGreaterEqual(hb_ticks["count"], 2)

            # Verify executor was not used and the callback ran on the current (test) thread
            consumer._pool_executor.submit.assert_not_called()
            self.assertIsNotNone(callback_thread_name["value"])
            self.assertEqual(callback_thread_name["value"], current_thread_name)


class ConsumerGracefulShutdownTest(TransactionTestCase):
    def setUp(self):
        with patch("django_outbox_pattern.factories.factory_connection"):
            self.consumer = factory_consumer()

    def test_stop_sets_shutting_down_flag(self):
        self.assertFalse(self.consumer._shutting_down)
        self.consumer.stop()
        self.assertTrue(self.consumer._shutting_down)

    def test_stop_waits_for_processing_event_before_disconnect(self):
        import threading

        self.consumer.connection.is_connected.side_effect = [False, True, True, True]
        self.consumer.start(lambda p: p, "/topic/destination.v1")

        # Simulate a message being processed
        self.consumer._processing_event.clear()

        disconnect_called = threading.Event()
        original_disconnect = self.consumer.connection.disconnect

        def track_disconnect(*args, **kwargs):
            disconnect_called.set()
            return original_disconnect(*args, **kwargs)

        self.consumer.connection.disconnect = track_disconnect

        # Release the processing event after a short delay
        def release_processing():
            import time

            time.sleep(0.1)
            self.consumer._processing_event.set()

        release_thread = threading.Thread(target=release_processing)
        release_thread.start()

        self.consumer.stop()
        release_thread.join()

        # Disconnect should have been called after processing finished
        self.assertTrue(disconnect_called.is_set())
        self.assertTrue(self.consumer._processing_event.is_set())

    def test_stop_waits_for_processing_before_unsubscribe(self):
        call_order = []

        self.consumer.connection.is_connected.side_effect = [False, True, True, True]
        self.consumer.start(lambda p: p, "/topic/destination.v1")

        original_unsubscribe = self.consumer.connection.unsubscribe

        def track_unsubscribe(*args, **kwargs):
            call_order.append("unsubscribe")
            return original_unsubscribe(*args, **kwargs)

        self.consumer.connection.unsubscribe = track_unsubscribe

        original_wait = self.consumer._processing_event.wait

        def track_wait(*args, **kwargs):
            call_order.append("wait_processing")
            return original_wait(*args, **kwargs)

        self.consumer._processing_event.wait = track_wait

        self.consumer.stop()

        # wait for processing should happen before unsubscribe so ACK/NACK can complete
        self.assertEqual(call_order, ["wait_processing", "unsubscribe"])

    def test_submit_task_skips_executor_recreation_when_shutting_down(self):
        self.consumer._shutting_down = True
        self.consumer._pool_executor = Mock()
        self.consumer._pool_executor.submit = Mock(side_effect=RuntimeError())

        with self.assertLogs("django_outbox_pattern", level="WARNING") as log:
            self.consumer._submit_task_to_worker_pool("{}", {"message-id": "m1"})
            self.assertIn("graceful shutdown", "\n".join(log.output))

    def test_listener_does_not_reconnect_when_shutting_down(self):
        from django_outbox_pattern.listeners import ConsumerListener

        self.consumer._shutting_down = True
        listener = ConsumerListener(self.consumer)

        self.consumer.start = Mock()
        listener.on_disconnected()

        self.consumer.start.assert_not_called()

    def test_processing_event_is_set_after_message_handler_completes(self):
        self.consumer.callback = lambda p: p.save()
        self.assertTrue(self.consumer._processing_event.is_set())

        self.consumer.message_handler('{"message": "test"}', {"message-id": "test-1"})

        self.assertTrue(self.consumer._processing_event.is_set())

    def test_processing_event_is_set_after_message_handler_exception(self):
        self.consumer.callback = Mock(side_effect=Exception("boom"))

        with self.assertLogs("django_outbox_pattern", level="ERROR"):
            self.consumer.message_handler('{"message": "test"}', {"message-id": "test-2"})

        self.assertTrue(self.consumer._processing_event.is_set())


class ConsumerShutdownTimeoutTest(TransactionTestCase):
    def setUp(self):
        with patch("django_outbox_pattern.factories.factory_connection"):
            self.consumer = factory_consumer()

    def test_stop_waits_indefinitely_when_timeout_is_none(self):
        """Test that stop() waits indefinitely when DEFAULT_CONSUMER_SHUTDOWN_TIMEOUT is None"""
        import threading

        with patch("django_outbox_pattern.settings.DEFAULT_CONSUMER_SHUTDOWN_TIMEOUT", None):
            self.consumer.connection.is_connected.side_effect = [False, True, True, True]
            self.consumer.start(lambda p: p, "/topic/destination.v1")

            # Simulate a message being processed
            self.consumer._processing_event.clear()

            # Release the processing event after a short delay
            def release_processing():
                import time

                time.sleep(0.2)
                self.consumer._processing_event.set()

            release_thread = threading.Thread(target=release_processing)
            release_thread.start()

            with self.assertLogs("django_outbox_pattern", level="INFO") as log:
                self.consumer.stop()

            release_thread.join()

            # Should log indefinite wait message
            self.assertIn("Waiting indefinitely for message processing to complete", "\n".join(log.output))
            self.assertTrue(self.consumer._processing_event.is_set())

    def test_stop_respects_timeout_when_configured(self):
        """Test that stop() respects timeout and proceeds after timeout expires"""
        import threading

        with patch("django_outbox_pattern.settings.DEFAULT_CONSUMER_SHUTDOWN_TIMEOUT", 0.1):
            self.consumer.connection.is_connected.side_effect = [False, True, True, True]
            self.consumer.start(lambda p: p, "/topic/destination.v1")

            # Simulate a message being processed that takes longer than timeout
            self.consumer._processing_event.clear()

            # Keep the event blocked for longer than timeout
            def keep_blocked():
                import time

                time.sleep(0.3)  # Longer than 0.1s timeout
                self.consumer._processing_event.set()

            block_thread = threading.Thread(target=keep_blocked)
            block_thread.start()

            with self.assertLogs("django_outbox_pattern", level="WARNING") as log:
                self.consumer.stop()

            block_thread.join()

            # Should log timeout warning
            warning_logs = "\n".join(log.output)
            self.assertIn("Message processing did not complete within", warning_logs)
            self.assertIn("0.1 seconds", warning_logs)
            self.assertIn("message may be redelivered", warning_logs)

    def test_stop_completes_normally_when_processing_finishes_before_timeout(self):
        """Test that stop() completes normally when message finishes within timeout"""
        import threading

        with patch("django_outbox_pattern.settings.DEFAULT_CONSUMER_SHUTDOWN_TIMEOUT", 0.5):
            self.consumer.connection.is_connected.side_effect = [False, True, True, True]
            self.consumer.start(lambda p: p, "/topic/destination.v1")

            # Simulate a message being processed
            self.consumer._processing_event.clear()

            # Release before timeout
            def release_processing():
                import time

                time.sleep(0.05)  # Much less than 0.5s timeout
                self.consumer._processing_event.set()

            release_thread = threading.Thread(target=release_processing)
            release_thread.start()

            with self.assertLogs("django_outbox_pattern", level="INFO") as log:
                self.consumer.stop()

            release_thread.join()

            # Should log timeout value but not timeout warning
            info_logs = "\n".join(log.output)
            self.assertIn("Waiting up to 0.5 seconds for message processing to complete", info_logs)
            self.assertNotIn("did not complete within", info_logs)
            self.assertTrue(self.consumer._processing_event.is_set())

    def test_stop_logs_correct_timeout_value(self):
        """Test that stop() logs the correct timeout value"""
        with patch("django_outbox_pattern.settings.DEFAULT_CONSUMER_SHUTDOWN_TIMEOUT", 42):
            self.consumer.connection.is_connected.side_effect = [False, True, True, True]
            self.consumer.start(lambda p: p, "/topic/destination.v1")

            with self.assertLogs("django_outbox_pattern", level="INFO") as log:
                self.consumer.stop()

            info_logs = "\n".join(log.output)
            self.assertIn("Waiting up to 42 seconds for message processing to complete", info_logs)

    def test_stop_proceeds_with_cleanup_after_timeout(self):
        """Test that stop() proceeds with pool shutdown and disconnect after timeout"""
        import threading

        with patch("django_outbox_pattern.settings.DEFAULT_CONSUMER_SHUTDOWN_TIMEOUT", 0.1):
            self.consumer.connection.is_connected.side_effect = [False, True, True, True]
            self.consumer.start(lambda p: p, "/topic/destination.v1")

            # Simulate a message being processed that takes longer than timeout
            self.consumer._processing_event.clear()

            shutdown_called = threading.Event()
            disconnect_called = threading.Event()

            original_shutdown = self.consumer._pool_executor.shutdown
            original_disconnect = self.consumer.connection.disconnect

            def track_shutdown(*args, **kwargs):
                shutdown_called.set()
                return original_shutdown(*args, **kwargs)

            def track_disconnect(*args, **kwargs):
                disconnect_called.set()
                return original_disconnect(*args, **kwargs)

            self.consumer._pool_executor.shutdown = track_shutdown
            self.consumer.connection.disconnect = track_disconnect

            # Keep blocked longer than timeout
            def keep_blocked():
                import time

                time.sleep(0.3)
                self.consumer._processing_event.set()

            block_thread = threading.Thread(target=keep_blocked)
            block_thread.start()

            with self.assertLogs("django_outbox_pattern", level="WARNING"):
                self.consumer.stop()

            block_thread.join()

            # Cleanup should happen despite timeout
            self.assertTrue(shutdown_called.is_set())
            self.assertTrue(disconnect_called.is_set())

    def test_stop_with_zero_timeout_returns_immediately(self):
        """Test that stop() with timeout=0 returns immediately if event not set"""
        with patch("django_outbox_pattern.settings.DEFAULT_CONSUMER_SHUTDOWN_TIMEOUT", 0):
            self.consumer.connection.is_connected.side_effect = [False, True, True, True]
            self.consumer.start(lambda p: p, "/topic/destination.v1")

            # Clear the event
            self.consumer._processing_event.clear()

            import time

            start_time = time.time()

            with self.assertLogs("django_outbox_pattern", level="WARNING") as log:
                self.consumer.stop()

            elapsed = time.time() - start_time

            # Should return almost immediately (within 0.1s)
            self.assertLess(elapsed, 0.1)

            # Should log timeout warning
            self.assertIn("Message processing did not complete within 0 seconds", "\n".join(log.output))

    def test_stop_when_already_idle_proceeds_immediately_with_timeout(self):
        """Test that stop() proceeds immediately when event is already set (idle state)"""
        with patch("django_outbox_pattern.settings.DEFAULT_CONSUMER_SHUTDOWN_TIMEOUT", 10):
            self.consumer.connection.is_connected.side_effect = [False, True, True, True]
            self.consumer.start(lambda p: p, "/topic/destination.v1")

            # Event is already set (idle state)
            self.assertTrue(self.consumer._processing_event.is_set())

            import time

            start_time = time.time()

            with self.assertLogs("django_outbox_pattern", level="INFO") as log:
                self.consumer.stop()

            elapsed = time.time() - start_time

            # Should return quickly (not wait full 10 seconds)
            self.assertLess(elapsed, 0.5)

            # Should not log timeout warning
            info_logs = "\n".join(log.output)
            self.assertNotIn("did not complete within", info_logs)

    def test_stop_timeout_with_background_processing_enabled(self):
        """Test that stop() timeout works correctly with background message processing"""
        import threading

        with patch("django_outbox_pattern.settings.DEFAULT_CONSUMER_SHUTDOWN_TIMEOUT", 0.1):
            with patch("django_outbox_pattern.settings.DEFAULT_CONSUMER_PROCESS_MSG_ON_BACKGROUND", True):
                # Recreate consumer with background processing enabled
                with patch("django_outbox_pattern.factories.factory_connection"):
                    consumer = factory_consumer()

                consumer.connection.is_connected.side_effect = [False, True, True, True]
                consumer.start(lambda p: p, "/topic/destination.v1")

                # Simulate background thread processing
                consumer._processing_event.clear()

                def keep_processing():
                    import time

                    time.sleep(0.3)  # Longer than timeout
                    consumer._processing_event.set()

                process_thread = threading.Thread(target=keep_processing)
                process_thread.start()

                with self.assertLogs("django_outbox_pattern", level="WARNING") as log:
                    consumer.stop()

                process_thread.join()

                # Should log timeout warning
                self.assertIn("Message processing did not complete within 0.1 seconds", "\n".join(log.output))
