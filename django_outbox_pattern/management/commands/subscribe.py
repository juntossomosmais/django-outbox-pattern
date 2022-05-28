from django.core.management.base import CommandError
from django.utils.module_loading import import_string

from django_outbox_pattern.factories import factory_consumer
from django_outbox_pattern.management.commands.base import Command as BaseCommand


def _import_from_string(value):
    try:
        return import_string(value)
    except ImportError as exc:
        msg = f"Could not import '{value}'. {exc.__class__}: {exc}."
        raise CommandError(msg) from exc


class Command(BaseCommand):
    help = "Subscribe command"

    def add_arguments(self, parser):
        parser.add_argument("callback", help="A dotted module path with the function to process messages")
        parser.add_argument("destination", help="Source destination used to consume messages")

    def handle(self, *args, **options):
        callback = _import_from_string(options.get("callback"))
        destination = options.get("destination")
        consumer = factory_consumer()
        try:
            self._start(consumer, callback, destination)
        except KeyboardInterrupt:
            consumer.stop()
            self._exit()

    def _start(self, consumer, callback, destination):
        consumer.start(callback, destination)
        while self.running and consumer.is_connected():
            self._waiting("Waiting for messages to be consume 😋")
        consumer.stop()
