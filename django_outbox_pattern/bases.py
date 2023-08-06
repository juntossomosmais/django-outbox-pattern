import logging
import random
import time

from stomp.exception import StompException

from django_outbox_pattern import settings

logger = logging.getLogger("django_outbox_pattern")


class Base:
    def __init__(self, connection, username, passcode):
        self._credentials = dict(username=username, passcode=passcode)  # pylint: disable=R1735
        self.attempts = 0
        self.connection = connection

    def connect(self):
        while not self.is_connected():
            try:
                self.connection.connect(**self._credentials, wait=True)
            except StompException:
                self._wait()
            else:
                self.attempts = 0

    def is_connected(self):
        return self.connection.is_connected()

    def get_listener(self, name):
        return self.connection.get_listener(name)

    def set_listener(self, name, listener):
        self.connection.set_listener(name, listener)

    def remove_listener(self, name):
        self.connection.remove_listener(name)

    def _disconnect(self):
        self.connection.disconnect()

    def _exponential_backoff(self):
        return min(2**self.attempts + random.uniform(0, 1), settings.DEFAULT_MAXIMUM_BACKOFF)

    def _wait(self):
        self.attempts += 1
        seconds = self._exponential_backoff()
        logger.debug("%s waiting for %.1f seconds before attempting reconnect", self.__class__.__name__, seconds)
        time.sleep(seconds)
