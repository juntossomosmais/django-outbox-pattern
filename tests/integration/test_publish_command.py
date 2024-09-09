from io import StringIO
from unittest.mock import MagicMock
from unittest.mock import PropertyMock
from unittest.mock import patch

from django.core.management import call_command
from django.db import DatabaseError
from django.test import TestCase

from django_outbox_pattern import settings
from django_outbox_pattern.exceptions import ExceededSendAttemptsException
from django_outbox_pattern.management.commands import publish
from django_outbox_pattern.management.commands.publish import Command
from django_outbox_pattern.models import Published


class PublishCommandTest(TestCase):
    def setUp(self):
        Command.running = PropertyMock(side_effect=[True, False])
        self.out = StringIO()

    def test_command_output_when_no_message_published(self):
        call_command("publish", stdout=self.out)
        self.assertIn("Waiting for messages to be published", self.out.getvalue())

    def test_command_output_when_message_published(self):
        Published.objects.create(destination="test", body={})
        call_command("publish", stdout=self.out)

        self.assertIn("Message published with body", self.out.getvalue())

    def test_command_on_database_error(self):
        with patch.object(publish, "import_string") as import_string:
            magic_import_string = MagicMock()
            magic_import_string.objects.filter.side_effect = DatabaseError()
            import_string.return_value = magic_import_string
            call_command("publish", stdout=self.out)
            self.assertIn("Starting publisher", self.out.getvalue())

    def test_command_on_exceeded_send_attempts(self):
        settings.DEFAULT_MAXIMUM_RETRY_ATTEMPTS = 1
        with patch.object(Command.producer, "send", side_effect=ExceededSendAttemptsException(1)):
            Published.objects.create(destination="test", body={})
            call_command("publish", stdout=self.out)
            self.assertIn("Message no published with body", self.out.getvalue())
