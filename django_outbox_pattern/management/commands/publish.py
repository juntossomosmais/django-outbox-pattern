import logging
import sys

from concurrent.futures import ThreadPoolExecutor
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
        self._should_process_on_background = settings.DEFAULT_PRODUCER_PROCESS_MSG_ON_BACKGROUND
        self._pool_executor = self._create_new_worker_executor() if self._should_process_on_background else None

    def handle(self, *args, **options):
        try:
            self._publish()
        except KeyboardInterrupt:
            self._exit()

    def _exit(self):
        self.stdout.write("\nI'm not waiting for messages anymore 🥲!")
        try:
            if self._pool_executor:
                self._pool_executor.shutdown(wait=True)
        except Exception:
            pass
        sys.exit(0)

    def _create_new_worker_executor(self):
        return ThreadPoolExecutor(
            max_workers=settings.DEFAULT_PRODUCER_PROCESS_MSG_WORKERS,
            thread_name_prefix="publisher",
        )

    def _submit_publish_task(self, message):
        try:
            self._pool_executor.submit(self._safe_send_and_update, message)
        except RuntimeError:
            logger.warning("Publisher worker pool was shutdown!")
            self._pool_executor = self._create_new_worker_executor()
            self._pool_executor.submit(self._safe_send_and_update, message)

    def _safe_send_and_update(self, message):
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

    def _publish(self):
        self.producer.start()
        self.stdout.write("Waiting for messages to be published 😋\nQuit with CONTROL-C")
        while self.running:
            try:
                published = self.published_class.objects.filter(
                    status=StatusChoice.SCHEDULE, expires_at__gte=timezone.now()
                ).iterator(chunk_size=int(settings.DEFAULT_PUBLISHED_CHUNK_SIZE))
                for message in published:
                    if self._should_process_on_background:
                        self._submit_publish_task(message)
                    else:
                        self._safe_send_and_update(message)
            except DatabaseError:
                self.stdout.write("Starting publisher 🤔\nQuit with CONTROL-C")
                _waiting()
            else:
                _waiting()
