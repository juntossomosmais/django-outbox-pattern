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
        parser.add_argument("queue_name", nargs="?", help="Optional queue name for subscribe")

    def handle(self, *args, **options):
        callback = _import_from_string(options.get("callback"))
        destination = options.get("destination")
        queue_name = options.get("queue_name")
        print(queue_name)
        consumer = factory_consumer()
        try:
            self._start(consumer, callback, destination, queue_name)
        except KeyboardInterrupt:
            consumer.stop()
            self._exit()

    def _start(self, consumer, callback, destination, queue_name):
        consumer.start(callback, destination, queue_name)
        while self.running and consumer.is_connected():
            self._waiting("Waiting for messages to be consume 😋")
        consumer.stop()
