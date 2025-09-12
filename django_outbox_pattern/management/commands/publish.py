import logging
import sys

from django.core.management.base import BaseCommand

from django_outbox_pattern.factories import factory_producer

_logger = logging.getLogger("django_outbox_pattern")


class Command(BaseCommand):
    help = "Publish command"
    running = True
    producer = factory_producer()

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
            self.producer.publish_message_from_database()
