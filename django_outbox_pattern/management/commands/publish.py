import logging
from datetime import timedelta

from django.db import DatabaseError
from django.utils import timezone

from django_outbox_pattern.choices import StatusChoice
from django_outbox_pattern.exceptions import ExceededSendAttemptsException
from django_outbox_pattern.factories import factory_producer
from django_outbox_pattern.management.commands.base import Command as BaseCommand
from django_outbox_pattern.settings import settings

logger = logging.getLogger("django_outbox_pattern")


class Command(BaseCommand):
    help = "Publish command"
    producer = factory_producer()
    published_class = settings.DEFAULT_PUBLISHED_CLASS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def handle(self, *args, **options):
        try:
            self._publish()
        except KeyboardInterrupt:
            self._exit()

    def _publish(self):
        self.producer.start()
        while self.running:
            try:
                published = self.published_class.objects.filter(status=StatusChoice.SCHEDULE)
                for message in published:
                    try:
                        attempts = self.producer.send(message)
                    except ExceededSendAttemptsException as exc:
                        logger.exception(exc)
                        message.retry = exc.attempts
                        message.status = StatusChoice.FAILED
                        message.expires_at = timezone.now() + timedelta(15)
                        self.stdout.write(f"Message no published with body:\n{message.body}")
                    else:
                        message.retry = attempts
                        message.status = StatusChoice.SUCCEEDED
                        self.stdout.write(f"Message published with body:\n{message.body}")
                    finally:
                        message.save()
            except DatabaseError:
                self._waiting("Starting publisher 🤔")
            else:
                self._waiting("Waiting for messages to be published 😋")
