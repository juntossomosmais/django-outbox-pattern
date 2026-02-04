import logging
import os
import signal
import threading

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.utils.module_loading import import_string

from django_outbox_pattern.factories import factory_consumer

_logger = logging.getLogger("django_outbox_pattern")


def _import_from_string(value):
    try:
        return import_string(value)
    except ImportError as exc:
        msg = f"Could not import '{value}'. {exc.__class__}: {exc}."
        raise CommandError(msg) from exc


class Command(BaseCommand):
    help = "Subscribe command"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = True
        self._stop_event = threading.Event()
        self._shutdown_initiated = False

    def add_arguments(self, parser):
        parser.add_argument("callback", help="A dotted module path with the function to process messages")
        parser.add_argument("destination", help="Source destination used to consume messages")
        parser.add_argument("queue_name", nargs="?", help="Optional queue name for subscribe")

    def handle(self, *args, **options):
        callback = _import_from_string(options.get("callback"))
        destination = options.get("destination")
        queue_name = options.get("queue_name")
        consumer = factory_consumer()

        self._register_signal_handlers()

        try:
            self._start(consumer, callback, destination, queue_name)
        except KeyboardInterrupt:
            _logger.info("Received KeyboardInterrupt, initiating graceful shutdown...")
            self.running = False
            self._stop_event.set()

        _logger.info("Stopping consumer gracefully")
        consumer.stop()
        _logger.info("Consumer stopped")

    def _register_signal_handlers(self):
        def _shutdown_handler(signum, frame):
            sig_name = signal.Signals(signum).name

            if self._shutdown_initiated:
                _logger.warning("Received %s during shutdown. Forcing immediate exit...", sig_name)
                os._exit(1)

            _logger.info("Received %s, initiating graceful shutdown...", sig_name)
            self._shutdown_initiated = True
            self.running = False
            self._stop_event.set()

        signal.signal(signal.SIGQUIT, _shutdown_handler)
        signal.signal(signal.SIGTERM, _shutdown_handler)
        signal.signal(signal.SIGINT, _shutdown_handler)

    def _start(self, consumer, callback, destination, queue_name):
        consumer.start(callback, destination, queue_name)
        _logger.info("Waiting for messages to be consumed...")
        while self.running and consumer.is_connected():
            self._stop_event.wait(timeout=1)
