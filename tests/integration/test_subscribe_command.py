from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from django_outbox_pattern.management.commands.subscribe import Command


class SubscribeCommandTest(TestCase):
    def setUp(self):
        self.out = StringIO()

    def test_command_output_when_waiting_message(self):
        with patch("django_outbox_pattern.management.commands.subscribe.factory_consumer") as mock_factory:
            mock_consumer = mock_factory.return_value
            # Make the consumer appear disconnected so the while loop exits immediately
            mock_consumer.is_connected.return_value = False
            with self.assertLogs("django_outbox_pattern", level="INFO") as cm:
                call_command("subscribe", "tests.integration.callback.callback", "destination")
            self.assertIn("Waiting for messages to be consumed", "\n".join(cm.output))
            mock_consumer.start.assert_called_once()
            mock_consumer.stop.assert_called_once()

    def test_command_no_has_enough_arguments(self):
        with self.assertRaisesMessage(CommandError, "Error: the following arguments are required: destination"):
            call_command("subscribe", "callback")

    def test_command_on_keyboard_input_error(self):
        with patch.object(Command, "_start", side_effect=KeyboardInterrupt()):
            with self.assertLogs("django_outbox_pattern", level="INFO") as cm:
                call_command("subscribe", "tests.integration.callback.callback", "destination")
            self.assertIn("Received KeyboardInterrupt, initiating graceful shutdown", "\n".join(cm.output))
