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

_logger = logging.getLogger("django_outbox_pattern")


def _waiting():
    sleep(settings.DEFAULT_PRODUCER_WAITING_TIME)


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
        _logger.info("I'm not waiting for messages anymore 🥲!")
        sys.exit(0)

    def _publish(self):
        _logger.info("Waiting for messages to be published 😋.")
        while self.running:
            try:
                objects_to_publish = self.published_class.objects.filter(
                    status=StatusChoice.SCHEDULE, expires_at__gte=timezone.now()
                )
                if not objects_to_publish.exists():
                    _logger.debug("No objects to publish")
                    _waiting()
                    continue

                published = objects_to_publish.iterator(chunk_size=settings.DEFAULT_PUBLISHED_CHUNK_SIZE)
                self.producer.start()
                for message in published:
                    message_id = message.id
                    _logger.debug("Message to published with body: %s", message.body)
                    try:
                        attempts = self.producer.send(message)
                    except ExceededSendAttemptsException as exc:
                        _logger.exception("Exceeded send attempts")
                        message.retry = exc.attempts
                        message.status = StatusChoice.FAILED
                        message.expires_at = timezone.now() + timedelta(15)
                        _logger.info(f"Message no published with id: {message_id}")
                    else:
                        message.retry = attempts
                        message.status = StatusChoice.SUCCEEDED
                        _logger.info(f"Message published with id: {message_id}")
                    finally:
                        message.save()
                self.producer.stop()
            except DatabaseError:
                _logger.info("Starting publisher 🤔.")
                _waiting()
            else:
                _waiting()
