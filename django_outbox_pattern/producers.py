import json
import logging
from time import sleep

from django.core.serializers.json import DjangoJSONEncoder
from stomp.exception import StompException
from stomp.utils import get_uuid

from django_outbox_pattern.bases import Base
from django_outbox_pattern.settings import settings

logger = logging.getLogger("django_outbox_pattern")


class Producer(Base):
    settings = settings
    listener_class = settings.DEFAULT_PRODUCER_LISTENER_CLASS

    def __init__(self, connection, username, passcode):
        super().__init__(connection, username, passcode)
        self.attempts = 0
        self.is_stopped = False
        self.set_listener(f"producer-listener-{get_uuid()}", self.listener_class(self))

    def start(self):
        if not self.is_stopped:
            self.connect()

    def stop(self):
        if self.is_connected():
            self._disconnect()
            self.is_stopped = True
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
        self._send_with_retry(kwargs)

    def _send_with_retry(self, kwargs):
        """
        During the message sending process, when the broker crashes or the connection fails or an abnormality occurs,
        will retry the sending. Retry 3 times for the first time, retry every minute after 4 minutes.
        When the total number of retries reaches 50 (DEFAULT_MAXIMUM_RETRY_ATTEMPTS), will stop retrying.
        """
        while self.attempts < self.settings.DEFAULT_MAXIMUM_RETRY_ATTEMPTS:
            try:
                self.connection.send(**kwargs)
            except StompException:
                self._wait()
            else:
                self.attempts = 0
                break
        if self.attempts:
            raise StompException

    def _wait(self):
        self.attempts += 1
        if self.attempts == 3:
            sleep(self.settings.DEFAULT_PAUSE_FOR_RETRY)
        elif self.attempts > 3:
            sleep(self.settings.DEFAULT_WAIT_RETRY)
