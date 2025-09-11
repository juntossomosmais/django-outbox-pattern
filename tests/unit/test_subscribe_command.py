from io import StringIO
from unittest.mock import PropertyMock
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from django_outbox_pattern.management.commands.subscribe import Command

SUBSCRIBE_COMMAND_PATH = "django_outbox_pattern.management.commands.subscribe"


class SubscribeCommandTest(TestCase):
    def setUp(self):
        Command.running = PropertyMock(side_effect=[True, False])
        self.out = StringIO()

    def test_command_output_when_waiting_message(self):
        with patch(f"{SUBSCRIBE_COMMAND_PATH}.factory_consumer"):
            with patch(f"{SUBSCRIBE_COMMAND_PATH}.import_string") as import_string:
                import_string.return_value = "callback"
                with self.assertLogs("django_outbox_pattern", level="INFO") as cm:
                    call_command("subscribe", "callback", "destination")
                    self.assertIn("Waiting for messages to be consume", "\n".join(cm.output))

    def test_command_no_has_enough_arguments(self):
        with patch(f"{SUBSCRIBE_COMMAND_PATH}.factory_consumer"):
            with self.assertRaisesMessage(CommandError, "Error: the following arguments are required: destination"):
                call_command("subscribe", "callback")

    def test_command_on_keyboard_input_error(self):
        with patch.object(Command, "_start", side_effect=KeyboardInterrupt()):
            with patch(f"{SUBSCRIBE_COMMAND_PATH}.import_string"):
                with self.assertRaises(SystemExit):
                    call_command("subscribe", "callback", "destination")

    def test_command_on_import_error(self):
        with patch(f"{SUBSCRIBE_COMMAND_PATH}.import_string") as import_string:
            import_string.side_effect = ImportError()
            with self.assertRaisesMessage(CommandError, "Could not import 'callback"):
                call_command("subscribe", "callback", "destination")
