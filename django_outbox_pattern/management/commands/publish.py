import logging
import sys
from datetime import timedelta
from time import sleep

from django.core.management.base import BaseCommand
from django.db import DatabaseError
from django.utils import timezone
from django.utils.module_loading import import_string

from django_outbox_pattern import settings
from django_outbox_pattern.choices import StatusChoice
from django_outbox_pattern.exceptions import ExceededSendAttemptsException
from django_outbox_pattern.factories import factory_producer

logger = logging.getLogger("django_outbox_pattern")


def _waiting():
    sleep(1)


class Command(BaseCommand):
    help = "Publish command"
    running = True
    producer = factory_producer()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.published_class = import_string(settings.DEFAULT_PUBLISHED_CLASS)

    def handle(self, *args, **options):
        try:
            self._publish()
        except KeyboardInterrupt:
            self._exit()

    def _exit(self):
        self.stdout.write("\nI'm not waiting for messages anymore 🥲!")
        sys.exit(0)

    def _publish(self):
        self.producer.start()
        self.stdout.write("Waiting for messages to be published 😋\nQuit with CONTROL-C")
        while self.running:
            try:
                published = self.published_class.objects.filter(
                    status=StatusChoice.SCHEDULE, expires_at__gte=timezone.now()
                )
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
                self.stdout.write("Starting publisher 🤔\nQuit with CONTROL-C")
                _waiting()
            else:
                _waiting()
