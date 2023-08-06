# pylint: disable=R0902
import json
import logging
from datetime import timedelta

from django import db
from django.core.cache import cache
from django.utils import timezone
from django.utils.module_loading import import_string
from stomp.utils import get_uuid

from django_outbox_pattern import settings
from django_outbox_pattern.bases import Base
from django_outbox_pattern.payloads import Payload

logger = logging.getLogger("django_outbox_pattern")


def _get_msg_id(headers):
    ret = None
    for key, value in headers.items():
        if key.endswith("-id"):
            ret = value
    return ret


class Consumer(Base):
    def __init__(self, connection, username, passcode):
        super().__init__(connection, username, passcode)
        self.callback = lambda p: p
        self.destination = None
        self.queue_name = None
        self.subscribe_id = None
        self.listener_name = f"consumer-listener-{get_uuid()}"
        self.listener_class = import_string(settings.DEFAULT_CONSUMER_LISTENER_CLASS)
        self.received_class = import_string(settings.DEFAULT_RECEIVED_CLASS)
        self.subscribe_headers = settings.DEFAULT_STOMP_QUEUE_HEADERS
        self.set_listener(self.listener_name, self.listener_class(self))

    def message_handler(self, body, headers):
        try:
            body = json.loads(body)
        except json.JSONDecodeError as exc:
            logger.exception(exc)

        payload = Payload(self.connection, body, headers)
        message_id = _get_msg_id(headers)

        if self.received_class.objects.filter(msg_id=message_id).exists():
            db.close_old_connections()
            logger.info(f"Message with msg_id: {message_id} already exists. discarding the message")
            payload.ack()
            return

        received = self.received_class(body=body, headers=headers, msg_id=message_id)

        payload.message = received

        try:
            self.callback(payload)
            if payload.saved:
                payload.ack()
            elif not payload.saved or not payload.nacked:
                logger.warning(
                    "The save or nack command was not executed, and the routine finished running "
                    "without receiving an acknowledgement or a negative acknowledgement. "
                    "message-id: %s",
                    message_id,
                )

        except BaseException:  # pylint: disable=broad-exception-caught
            logger.exception("An exception has been caught during callback processing flow")
            payload.nack()

        finally:
            try:
                self._remove_old_messages()
            finally:
                db.close_old_connections()

    def start(self, callback, destination, queue_name=None):
        self.connect()
        self.callback = callback
        self.destination = destination
        self.queue_name = queue_name
        self._create_dlq_queue(destination, self.subscribe_headers, queue_name)
        self._create_queue(destination, self.subscribe_headers, queue_name)
        logger.info("Consumer started with id: %s", self.subscribe_id)

    def stop(self):
        if self.subscribe_id and self.is_connected():
            self._unsubscribe()
            self.remove_listener(self.listener_name)
            self._disconnect()
        else:
            logger.info("Consumer not started")

    def _create_dlq_queue(self, destination, headers, queue_name=None):
        if not self.subscribe_id:
            subscribe_id = get_uuid()
            self._subscribe(destination, subscribe_id, headers, queue_name, dlq=True)
            self.connection.unsubscribe(subscribe_id)

    def _create_queue(self, destination, headers, queue_name=None):
        if self.subscribe_id is None:
            self.subscribe_id = get_uuid()
        self._subscribe(destination, self.subscribe_id, headers, queue_name)

    def _subscribe(self, destination, subscribe_id, headers, queue_name=None, dlq=False):
        # pylint: disable=too-many-arguments
        routing_key = destination.split("/")[-1]
        queue_name = queue_name if queue_name else routing_key
        if dlq:
            queue_name = f"DLQ.{queue_name}"
        headers.update(
            {
                "exclusive": settings.DAFAULT_EXCLUSIVE_QUEUE,
                "x-queue-name": queue_name,
                "x-dead-letter-routing-key": f"DLQ.DLQ.{queue_name}" if dlq else f"DLQ.{queue_name}",
                "x-dead-letter-exchange": "",
            }
        )
        if dlq:
            self.connection.subscribe(queue_name, subscribe_id, ack="client", headers=headers)
        else:
            self.connection.subscribe(destination, subscribe_id, ack="client", headers=headers)
        logger.info("Created queue %s with id: %s", queue_name, subscribe_id)

    def _unsubscribe(self):
        self.connection.unsubscribe(self.subscribe_id)
        logger.info("Subscription with id %s canceled", self.subscribe_id)
        self.subscribe_id = None

    def _remove_old_messages(self):
        if cache.get(settings.OUTBOX_PATTERN_CONSUMER_CACHE_KEY):
            return
        days_ago = timezone.now() - timedelta(days=settings.DAYS_TO_KEEP_DATA)
        self.received_class.objects.filter(added__lt=days_ago).delete()

        cache.set(settings.OUTBOX_PATTERN_CONSUMER_CACHE_KEY, True, settings.REMOVE_DATA_CACHE_TTL)
