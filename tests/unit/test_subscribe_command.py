import signal

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from django_outbox_pattern.management.commands.subscribe import Command

SUBSCRIBE_COMMAND_PATH = "django_outbox_pattern.management.commands.subscribe"


class SubscribeCommandTest(TestCase):
    def setUp(self):
        self.out = StringIO()

    def test_command_output_when_waiting_message(self):
        with patch(f"{SUBSCRIBE_COMMAND_PATH}.factory_consumer") as mock_factory:
            mock_consumer = mock_factory.return_value
            mock_consumer.is_connected.return_value = False
            with patch(f"{SUBSCRIBE_COMMAND_PATH}.import_string") as import_string:
                import_string.return_value = "callback"
                with self.assertLogs("django_outbox_pattern", level="INFO") as cm:
                    call_command("subscribe", "callback", "destination")
                    self.assertIn("Waiting for messages to be consume", "\n".join(cm.output))

    def test_command_no_has_enough_arguments(self):
        with patch(f"{SUBSCRIBE_COMMAND_PATH}.factory_consumer"):
            with self.assertRaisesMessage(CommandError, "Error: the following arguments are required: destination"):
                call_command("subscribe", "callback")

    def test_command_on_import_error(self):
        with patch(f"{SUBSCRIBE_COMMAND_PATH}.import_string") as import_string:
            import_string.side_effect = ImportError()
            with self.assertRaisesMessage(CommandError, "Could not import 'callback"):
                call_command("subscribe", "callback", "destination")

    def test_command_calls_consumer_stop_on_exit(self):
        with patch(f"{SUBSCRIBE_COMMAND_PATH}.factory_consumer") as mock_factory:
            mock_consumer = mock_factory.return_value
            mock_consumer.is_connected.return_value = False
            with patch(f"{SUBSCRIBE_COMMAND_PATH}.import_string") as import_string:
                import_string.return_value = "callback"
                with self.assertLogs("django_outbox_pattern", level="INFO"):
                    call_command("subscribe", "callback", "destination")
                mock_consumer.stop.assert_called_once()

    def test_sigterm_handler_sets_running_false_and_stop_event(self):
        handlers = {}

        def capture_handler(signum, handler):
            handlers[signum] = handler

        command = Command()
        with patch(f"{SUBSCRIBE_COMMAND_PATH}.signal.signal", side_effect=capture_handler):
            command._register_signal_handlers()

        handlers[signal.SIGTERM](signal.SIGTERM, None)

        self.assertFalse(command.running)
        self.assertTrue(command._stop_event.is_set())

    def test_sigint_handler_sets_running_false_and_stop_event(self):
        handlers = {}

        def capture_handler(signum, handler):
            handlers[signum] = handler

        command = Command()
        with patch(f"{SUBSCRIBE_COMMAND_PATH}.signal.signal", side_effect=capture_handler):
            command._register_signal_handlers()

        handlers[signal.SIGINT](signal.SIGINT, None)

        self.assertFalse(command.running)
        self.assertTrue(command._stop_event.is_set())

    def test_second_signal_forces_immediate_exit(self):
        handlers = {}

        def capture_handler(signum, handler):
            handlers[signum] = handler

        command = Command()
        with patch(f"{SUBSCRIBE_COMMAND_PATH}.signal.signal", side_effect=capture_handler):
            command._register_signal_handlers()

        # First signal - graceful shutdown
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        self.assertTrue(command._shutdown_initiated)

        # Second signal - force exit
        with patch(f"{SUBSCRIBE_COMMAND_PATH}.os._exit") as mock_exit:
            with self.assertLogs("django_outbox_pattern", level="WARNING") as log:
                handlers[signal.SIGINT](signal.SIGINT, None)

            mock_exit.assert_called_once_with(1)
            self.assertIn("Forcing immediate exit", "\n".join(log.output))
