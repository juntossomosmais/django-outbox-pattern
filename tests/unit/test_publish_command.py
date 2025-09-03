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

    def test_publish_background_enabled_uses_executor(self):
        # Ensure command uses background mode
        with patch(
            "django_outbox_pattern.management.commands.publish.settings.DEFAULT_PRODUCER_PROCESS_MSG_ON_BACKGROUND",
            True,
        ):
            # Patch the producer instance on the Command to avoid real connections
            with patch.object(Command, "producer") as mock_producer:
                mock_producer.start.return_value = None
                # Prepare one message to publish
                Published.objects.create(destination="test", body={})
                # Spy on submit vs sync path
                with (
                    patch.object(publish.Command, "_submit_publish_task") as submit_spy,
                    patch.object(publish.Command, "_safe_send_and_update") as sync_spy,
                ):
                    call_command("publish", stdout=self.out)
                    submit_spy.assert_called()
                    sync_spy.assert_not_called()

    def test_submit_runtimeerror_recreates_executor_and_submits(self):
        cmd = Command()
        # Enable background processing by simulating executor presence
        cmd._pool_executor = mock_exec_1 = MagicMock()
        # First executor raises RuntimeError
        mock_exec_1.submit.side_effect = RuntimeError()
        # New executor which will accept the task
        mock_exec_2 = MagicMock()
        with patch.object(cmd, "_create_new_worker_executor", return_value=mock_exec_2):
            msg = Published.objects.create(destination="x", body={})
            cmd._submit_publish_task(msg)
            mock_exec_2.submit.assert_called_once()

    def test_exit_shuts_down_executor(self):
        cmd = Command()
        cmd._pool_executor = MagicMock()
        with self.assertRaises(SystemExit):
            cmd._exit()
        cmd._pool_executor.shutdown.assert_called_once_with(wait=True)

    def test_command_output_when_no_message_published(self):
        with patch(f"{PUBLISH_COMMAND_PATH}.factory_producer"):
            call_command("publish", stdout=self.out)
            self.assertIn("Waiting for messages to be published", self.out.getvalue())

    def test_command_output_when_message_published(self):
        with patch(f"{PUBLISH_COMMAND_PATH}.factory_producer"):
            Published.objects.create(destination="test", body={})
            call_command("publish", stdout=self.out)
            self.assertIn("Message published with body", self.out.getvalue())

    def test_command_on_database_error(self):
        with patch(f"{PUBLISH_COMMAND_PATH}.factory_producer"):
            with patch.object(publish, "import_string") as import_string:
                magic_import_string = MagicMock()
                magic_import_string.objects.filter.side_effect = DatabaseError()
                import_string.return_value = magic_import_string
                call_command("publish", stdout=self.out)
                self.assertIn("Starting publisher", self.out.getvalue())

    def test_command_on_keyboard_input_error(self):
        with patch.object(Command, "_publish", side_effect=KeyboardInterrupt()):
            with self.assertRaises(SystemExit):
                call_command("publish", stdout=self.out)
