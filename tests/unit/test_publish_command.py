from io import StringIO
from unittest.mock import MagicMock
from unittest.mock import PropertyMock
from unittest.mock import patch

from django.core.management import call_command
from django.db import DatabaseError
from django.test import TestCase

from django_outbox_pattern.management.commands import publish
from django_outbox_pattern.management.commands.publish import Command
from django_outbox_pattern.models import Published

PUBLISH_COMMAND_PATH = "django_outbox_pattern.management.commands.publish"


class PublishCommandTest(TestCase):
    def setUp(self):
        Command.running = PropertyMock(side_effect=[True, False])
        self.out = StringIO()

    def test_command_output_when_no_message_published(self):
        with patch(f"{PUBLISH_COMMAND_PATH}.factory_producer"):
            with self.assertLogs("django_outbox_pattern", level="INFO") as cm:
                call_command("publish")
            self.assertIn("Waiting for messages to be published", "\n".join(cm.output))

    def test_command_output_when_message_published(self):
        published = Published.objects.create(destination="test", body={})
        with patch(f"{PUBLISH_COMMAND_PATH}.factory_producer"):
            with self.assertLogs("django_outbox_pattern", level="INFO") as cm:
                call_command("publish")
            self.assertIn(f"Message published with id: {str(published.id)}", "\n".join(cm.output))

    def test_command_on_database_error(self):
        Published.objects.create(destination="test", body={})
        with patch(f"{PUBLISH_COMMAND_PATH}.factory_producer"):
            with patch.object(publish, "import_string") as import_string:
                magic_import_string = MagicMock()
                magic_import_string.objects.filter.side_effect = DatabaseError()
                import_string.return_value = magic_import_string
                with self.assertLogs("django_outbox_pattern", level="INFO") as cm:
                    call_command("publish")
                self.assertIn("Starting publisher", "\n".join(cm.output))

    def test_command_on_keyboard_input_error(self):
        with patch.object(Command, "_publish", side_effect=KeyboardInterrupt()):
            with self.assertRaises(SystemExit):
                call_command("publish")
