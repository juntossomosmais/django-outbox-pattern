from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from django_outbox_pattern.choices import StatusChoice
from django_outbox_pattern.models import Published
from django_outbox_pattern.models import Received


class PurgeCommandTest(TestCase):

    now: timezone.datetime
    thirty_days_ago: timezone.datetime
    current_published_messages: list[Published]
    current_received_messages: list[Received]

    def setUp(self) -> None:
        self.now = timezone.now()
        self.thirty_days_ago = self.now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=30)

        for i in range(10):
            published = Published.objects.create(destination="test", body={"index": i}, status=StatusChoice.SUCCEEDED)
            published.added = self.thirty_days_ago
            published.save()

        for i in range(5):
            received = Received.objects.create(body={"index": i}, status=StatusChoice.SUCCEEDED)
            received.added = self.thirty_days_ago
            received.save()

        # Current messages
        published_1 = Published.objects.create(
            destination="test", body={"index": 11}, status=StatusChoice.SCHEDULE, added=self.now
        )
        published_2 = Published.objects.create(
            destination="test", body={"index": 12}, status=StatusChoice.SUCCEEDED, added=self.now
        )
        received_1 = Received.objects.create(body={"index": 6}, status=StatusChoice.SUCCEEDED, added=self.now)

        self.current_published_messages = [published_1, published_2]
        self.current_received_messages = [received_1]

    def test_purge_command_should_count_published_and_received_messages_when_dry_run(self):
        with self.assertLogs("django_outbox_pattern", level="WARNING") as cm:
            call_command("purge", "--dry-run")

        self.assertEqual(Published.objects.count(), 12)
        self.assertEqual(Received.objects.count(), 6)
        self.assertIn("Dry run would delete 5 received messages", cm.output[0])
        self.assertIn("Dry run would delete 10 published messages", cm.output[1])

    def test_purge_command_should_purge_published_and_received_messages(self):
        with self.assertLogs("django_outbox_pattern", level="INFO") as cm:
            call_command("purge")

        self.assertEqual(Published.objects.count(), 2)
        self.assertEqual(Received.objects.count(), 1)

        current_published_ids = [published.id for published in self.current_published_messages]
        current_received_ids = [received.id for received in self.current_received_messages]

        # Current messages should not be deleted
        self.assertEqual(Published.objects.filter(id__in=current_published_ids).count(), 2)
        self.assertEqual(Received.objects.filter(id__in=current_received_ids).count(), 1)

        assert any("Deleted 10 published messages" in message for message in cm.output)
        assert any("Deleted 5 received messages" in message for message in cm.output)

    def test_purge_should_include_scheduled_messages(self):
        with self.assertLogs("django_outbox_pattern", level="INFO") as cm:
            call_command("purge", "--include-scheduled", "--days=0")

        self.assertEqual(Published.objects.count(), 0)
        self.assertEqual(Received.objects.count(), 0)

        assert any("Deleted 12 published messages" in message for message in cm.output)
        assert any("Deleted 6 received messages" in message for message in cm.output)

    def test_should_purge_received_messages_only(self):
        with self.assertLogs("django_outbox_pattern", level="INFO") as cm:
            call_command("purge", "--purge-received-only", "--days=0", "--include-scheduled")

        self.assertEqual(Published.objects.count(), 12)
        self.assertEqual(Received.objects.count(), 0)

        assert not any("Deleted 12 published messages" in message for message in cm.output)
        assert any("Deleted 6 received messages" in message for message in cm.output)

    def test_should_purge_published_messages_only(self):
        with self.assertLogs("django_outbox_pattern", level="INFO") as cm:
            call_command("purge", "--purge-published-only", "--days=0", "--include-scheduled")

        self.assertEqual(Published.objects.count(), 0)
        self.assertEqual(Received.objects.count(), 6)

        assert any("Deleted 12 published messages" in message for message in cm.output)
        assert not any("Deleted 6 received messages" in message for message in cm.output)

    def test_should_batch_delete_messages(self):
        with self.assertLogs("django_outbox_pattern", level="INFO") as cm:
            call_command("purge", "--batch-size=2", "--days=0", "--include-scheduled")

        self.assertEqual(Published.objects.count(), 0)
        self.assertEqual(Received.objects.count(), 0)

        # Dumbest assert ever
        assert any("Deleted 2/12 published messages" in message for message in cm.output)
        assert any("Deleted 4/12 published messages" in message for message in cm.output)
        assert any("Deleted 6/12 published messages" in message for message in cm.output)
        assert any("Deleted 8/12 published messages" in message for message in cm.output)
        assert any("Deleted 10/12 published messages" in message for message in cm.output)
        assert any("Deleted 12/12 published messages" in message for message in cm.output)
        assert any("Deleted 2/6 received messages" in message for message in cm.output)
        assert any("Deleted 4/6 received messages" in message for message in cm.output)
        assert any("Deleted 6/6 received messages" in message for message in cm.output)

        assert any("Deleted total of 12 published messages" in message for message in cm.output)
        assert any("Deleted total of 6 received messages" in message for message in cm.output)
