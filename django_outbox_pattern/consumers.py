import json
import logging

from stomp.utils import get_uuid

from django_outbox_pattern.bases import Base
from django_outbox_pattern.choices import StatusChoice
from django_outbox_pattern.payloads import Payload
from django_outbox_pattern.settings import settings

logger = logging.getLogger("django_outbox_pattern")


class Consumer(Base):
    listener_class = settings.DEFAULT_CONSUMER_LISTENER_CLASS
    received_class = settings.DEFAULT_RECEIVED_CLASS
    subscribe_headers = settings.DEFAULT_STOMP_QUEUE_HEADERS

    def __init__(self, connection, username, passcode):
        super().__init__(connection, username, passcode)
        self.callback = lambda p: p
        self.destination = None
        self.is_stopped = False
        self.subscribe_id = None
        self.set_listener(f"consumer-listener-{get_uuid()}", self.listener_class(self))

    def message_handler(self, body, headers):
        body = json.loads(body)
        payload = Payload(self.connection, body, headers)
        received = self.received_class()
        received.body = body
        received.headers = headers
        try:
            self.callback(payload)
        except Exception as exc:  # pylint: disable=broad-except
            received.status = StatusChoice.FAILED
            if self.is_connected():
                payload.nack()
            logger.exception(exc)
        else:
            received.status = StatusChoice.SUCCEEDED
        finally:
            received.save()

    def start(self, callback, destination):
        if not self.is_stopped:
            self.connect()
            self.callback = callback
            self.destination = destination
            self._create_dlq_queue(destination, self.subscribe_headers)
            self._create_queue(destination, self.subscribe_headers)
            logger.info("Consumer started with id: %s", self.subscribe_id)

    def stop(self):
        if self.subscribe_id and self.is_connected():
            self._unsubscribe()
            self._disconnect()
            self.is_stopped = True
        else:
            logger.info("Consumer not started")

    def _create_dlq_queue(self, destination, headers):
        if not self.subscribe_id:
            subscribe_id = get_uuid()
            self._subscribe(destination, subscribe_id, headers, dlq=True)
            self.connection.unsubscribe(subscribe_id)

    def _create_queue(self, destination, headers):
        if self.subscribe_id is None:
            self.subscribe_id = get_uuid()
        self._subscribe(destination, self.subscribe_id, headers)

    def _subscribe(self, destination, subscribe_id, headers, dlq=False):
        routing_key = destination.split("/")[-1]
        if dlq:
            routing_key = f"DLQ.{routing_key}"
        headers.update(
            {
                "x-queue-name": routing_key,
                "x-dead-letter-routing-key": f"DLQ.DLQ.{routing_key}" if dlq else f"DLQ.{routing_key}",
                "x-dead-letter-exchange": "",
            }
        )
        if dlq:
            self.connection.subscribe(routing_key, subscribe_id, ack="client", headers=headers)
        else:
            self.connection.subscribe(destination, subscribe_id, ack="client", headers=headers)
        logger.info("Created queue %s with id: %s", routing_key, subscribe_id)

    def _unsubscribe(self):
        self.connection.unsubscribe(self.subscribe_id)
        logger.info("Subscription with id %s canceled", self.subscribe_id)
        self.subscribe_id = None
