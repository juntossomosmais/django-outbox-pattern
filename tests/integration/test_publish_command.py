from io import StringIO
from unittest.mock import PropertyMock
from unittest.mock import patch

from django.core.management import call_command
from django.db import DatabaseError
from django.test import TestCase
from django.test import override_settings

from django_outbox_pattern.exceptions import ExceededSendAttemptsException
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
        with patch.object(Command.published_class.objects, "filter", side_effect=DatabaseError()):
            call_command("publish", stdout=self.out)
            self.assertIn("Starting publisher", self.out.getvalue())

    @override_settings(DJANGO_OUTBOX_PATTERN={"DEFAULT_RETRY_SEND_ATTEMPTS": 1})
    def test_command_on_exceeded_send_attempts(self):
        with patch.object(Command.producer, "send", side_effect=ExceededSendAttemptsException(1)):
            Published.objects.create(destination="test", body={})
            call_command("publish", stdout=self.out)
            self.assertIn("Message no published with body", self.out.getvalue())
