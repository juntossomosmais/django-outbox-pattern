import json
import logging
from datetime import timedelta
from time import sleep

from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from stomp.exception import StompException
from stomp.utils import get_uuid

from django_outbox_pattern.bases import Base
from django_outbox_pattern.exceptions import ExceededSendAttemptsException
from django_outbox_pattern.settings import settings

logger = logging.getLogger("django_outbox_pattern")


class Producer(Base):
    settings = settings
    listener_class = settings.DEFAULT_PRODUCER_LISTENER_CLASS
    published_class = settings.DEFAULT_PUBLISHED_CLASS

    def __init__(self, connection, username, passcode):
        super().__init__(connection, username, passcode)
        self.listener_name = f"producer-listener-{get_uuid()}"
        self.set_listener(self.listener_name, self.listener_class(self))

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self):
        self.connect()

    def stop(self):
        if self.is_connected():
            self.remove_listener(self.listener_name)
            self._disconnect()
        else:
            logger.info("Producer not started")

    def send(self, message, **kwargs):
        generate_headers = self.settings.DEFAULT_GENERATE_HEADERS
        headers = generate_headers(message)
        kwargs = {
            "body": json.dumps(message.body, cls=DjangoJSONEncoder),
            "destination": message.destination,
            "headers": headers,
            **kwargs,
        }
        return self._send_with_retry(**kwargs)

    def send_event(self, body, destination, **kwargs):
        kwargs = {
            "body": json.dumps(body, cls=DjangoJSONEncoder),
            "destination": destination,
            **kwargs,
        }
        return self._send_with_retry(**kwargs)

    def _send_with_retry(self, **kwargs):
        """
        During the message sending process, when the broker crashes or the connection fails or an abnormality occurs,
        will retry the sending. Retry 3 times for the first time, retry every minute after 4 minutes.
        When the total number of retries reaches 50 (DEFAULT_MAXIMUM_RETRY_ATTEMPTS), will stop retrying.
        """

        attempts = 0

        while attempts < self.settings.DEFAULT_MAXIMUM_RETRY_ATTEMPTS:
            try:
                self.connection.send(**kwargs)
            except StompException:
                attempts += 1
                if attempts == 3:
                    sleep(self.settings.DEFAULT_PAUSE_FOR_RETRY)
                elif attempts > 3:
                    sleep(self.settings.DEFAULT_WAIT_RETRY)
            else:
                break
        else:
            raise ExceededSendAttemptsException(attempts)

        self._remove_old_messages()
        return attempts

    def _remove_old_messages(self):
        if cache.get(settings.OUTBOX_PATTERN_PUBLISHER_CACHE_KEY):
            return

        days_ago = timezone.now() - timedelta(days=settings.DAYS_TO_KEEP_DATA)
        self.published_class.objects.filter(added__lt=days_ago).delete()

        cache.set(settings.OUTBOX_PATTERN_PUBLISHER_CACHE_KEY, True, settings.REMOVE_DATA_CACHE_TTL)
