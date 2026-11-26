import json
import logging
import threading
import time

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

from django import db
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import OperationalError
from django.utils import timezone
from django.utils.module_loading import import_string
from request_id_django_log import local_threading
from stomp.utils import get_uuid

from django_outbox_pattern import settings
from django_outbox_pattern.bases import Base
from django_outbox_pattern.payloads import Payload

_logger = logging.getLogger("django_outbox_pattern")

# Attributes every LogRecord already has: using one of them as an `extra` key makes logging raise KeyError.
_RESERVED_LOG_RECORD_ATTRIBUTES = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def _message_log_extra(message_id):
    """
    Builds the log `extra` that carries the message id, under the key configured in
    DEFAULT_CONSUMER_LOG_MESSAGE_ID_KEY (the legacy name `MessageId` by default, or the OpenTelemetry semantic
    convention key `messaging.message.id` for services whose logging pipeline accepts dotted keys).
    """
    return {settings.DEFAULT_CONSUMER_LOG_MESSAGE_ID_KEY: message_id}


def _validate_log_message_id_key(key):
    if not isinstance(key, str) or not key or key in _RESERVED_LOG_RECORD_ATTRIBUTES:
        raise ImproperlyConfigured(
            "DEFAULT_CONSUMER_LOG_MESSAGE_ID_KEY must be a non-empty string that is not a LogRecord attribute, "
            f"got {key!r}"
        )


def _get_msg_id(headers):
    """
    Retrieves the first header value that matches cap-msg-id, dop-msg-id or message-id, in this order of precedence.

    These values are used to be added as the received message id, so we can track if the message was already received.

    The cap-msg-id is a header that is used by the CAP .NET library, and it's used to identify the message.

    The dop-msg-id is a header that is used by the Django Outbox Pattern library, and it's used to identify the message.
    """
    return headers.get("cap-msg-id") or headers.get("dop-msg-id") or headers.get("message-id")


def _parse_body(body, message_id):
    """
    Decodes the JSON message body. A body that is already a dict or list (e.g. from a custom listener) is returned as
    is, and a body that cannot be decoded is logged and returned unchanged, so the callback still decides what to do.
    """
    if isinstance(body, (dict, list)):
        return body
    try:
        return json.loads(body)
    # log-score: ignore LOG-ERR-003 - the raw body is handed to the callback, which decides to save or nack it
    except (ValueError, TypeError, RecursionError):
        _logger.warning("Message body is not valid JSON", exc_info=True, extra=_message_log_extra(message_id))
        return body


def _get_or_create_correlation_id(headers: dict) -> str:
    if "dop-correlation-id" in headers:
        return headers["dop-correlation-id"]

    correlation_id = str(uuid4())
    _logger.debug("A new dop-correlation-id was generated %s", correlation_id)
    return correlation_id


class Consumer(Base):
    def __init__(self, connection, username, passcode):
        super().__init__(connection, username, passcode)
        _validate_log_message_id_key(settings.DEFAULT_CONSUMER_LOG_MESSAGE_ID_KEY)
        self.callback = lambda p: p
        self.destination = None
        self.queue_name = None
        self.subscribe_id = None
        self.listener_name = f"consumer-listener-{get_uuid()}"
        self.listener_class = import_string(settings.DEFAULT_CONSUMER_LISTENER_CLASS)
        self.received_class = import_string(settings.DEFAULT_RECEIVED_CLASS)
        self.subscribe_headers = settings.DEFAULT_STOMP_QUEUE_HEADERS

        # Background processing controls
        self._should_process_msg_on_background = settings.DEFAULT_CONSUMER_PROCESS_MSG_ON_BACKGROUND
        self._pool_executor = self._create_new_worker_executor()
        self._shutting_down = False
        self._processing_event = threading.Event()
        self._processing_event.set()  # Initially idle
        self.set_listener(self.listener_name, self.listener_class(self))

    def _create_new_worker_executor(self):
        return ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=self.listener_name,
        )

    def handle_incoming_message(self, body, headers):
        if self._shutting_down:
            _logger.warning(
                "Received message during shutdown, skipping (will be redelivered)",
                extra=_message_log_extra(_get_msg_id(headers)),
            )
            return
        if self._should_process_msg_on_background:
            self._submit_task_to_worker_pool(body, headers)
        else:
            self.message_handler(body, headers)

    def _submit_task_to_worker_pool(self, body, headers):
        try:
            self._pool_executor.submit(self.message_handler, body, headers)
        except RuntimeError:
            if self._shutting_down:
                _logger.warning(
                    "Worker pool was shutdown during graceful shutdown, discarding message",
                    extra=_message_log_extra(_get_msg_id(headers)),
                )
                return
            _logger.warning("Worker pool was shutdown!", extra=_message_log_extra(_get_msg_id(headers)))
            self._pool_executor = self._create_new_worker_executor()
            self._pool_executor.submit(self.message_handler, body, headers)

    def message_handler(self, body, headers):
        self._processing_event.clear()
        try:
            local_threading.request_id = _get_or_create_correlation_id(headers)
            message_id = _get_msg_id(headers)
            # Logged here rather than in the STOMP listener so the record is emitted inside the span that
            # tracing instrumentations open around message_handler, in both sync and background modes.
            _logger.info("Message received", extra=_message_log_extra(message_id))
            body = _parse_body(body, message_id)

            payload = Payload(self.connection, body, headers)
            self._process_message_with_retry(payload, body, headers, message_id)

        finally:
            try:
                try:
                    self._remove_old_messages()
                # log-score: ignore LOG-ERR-003 - cleanup of old messages is best effort, processing already finished
                except Exception:
                    _logger.warning("Error while removing old messages, skipping cleanup this cycle", exc_info=True)
                finally:
                    db.close_old_connections()
            finally:
                local_threading.request_id = None
                self._processing_event.set()

    def _process_message_with_retry(self, payload, body, headers, message_id, attempt=0):
        max_retries = settings.DEFAULT_CONSUMER_MAX_RETRY_ATTEMPTS
        try:
            # Without an id there is nothing to deduplicate on: filtering by NULL would discard every id-less message
            # after the first one as a duplicate.
            if message_id is not None and self.received_class.objects.filter(msg_id=message_id).exists():
                db.close_old_connections()
                _logger.info("Message already exists, discarding the message", extra=_message_log_extra(message_id))
                payload.ack()
                return

            received = self.received_class(body=body, headers=headers, msg_id=message_id)
            payload.message = received

            self.callback(payload)
            if payload.saved:
                payload.ack()
            elif not payload.nacked:
                _logger.warning(
                    "The save or nack command was not executed, and the routine finished running "
                    "without receiving an acknowledgement or a negative acknowledgement",
                    extra=_message_log_extra(message_id),
                )

        except OperationalError:
            if attempt >= max_retries:
                # log-score: ignore JSM-LOG-014 - max_retries comes from settings and is not queried
                _logger.error(
                    "All %s retries exhausted, sending to DLQ",
                    max_retries,
                    extra=_message_log_extra(message_id),
                )
                payload.nack()
                return

            wait_time = settings.DEFAULT_CONSUMER_RETRY_WAIT * (attempt + 1)
            # log-score: ignore JSM-LOG-014 - retry counters and wait time come from settings and are not queried
            _logger.warning(
                "Retry %s/%s failed, retrying in %ss",
                attempt + 1,
                max_retries,
                wait_time,
                extra=_message_log_extra(message_id),
            )
            db.close_old_connections()
            time.sleep(wait_time)
            retry_payload = Payload(self.connection, body, headers)
            self._process_message_with_retry(retry_payload, body, headers, message_id, attempt + 1)

        except Exception:
            _logger.exception("An exception has been caught during callback processing flow")
            payload.nack()

    def start(self, callback, destination, queue_name=None):
        self.connect()
        self.callback = callback
        self.destination = destination
        self.queue_name = queue_name
        self._create_dlq_queue(destination, self.subscribe_headers, queue_name)
        self._create_queue(destination, self.subscribe_headers, queue_name)
        _logger.info("Consumer started with id: %s", self.subscribe_id)

    def stop(self):
        self._shutting_down = True

        shutdown_timeout = settings.DEFAULT_CONSUMER_SHUTDOWN_TIMEOUT
        processing_completed = True
        if shutdown_timeout is not None:
            _logger.info("Waiting up to %s seconds for message processing to complete", shutdown_timeout)
            processing_completed = self._processing_event.wait(timeout=shutdown_timeout)
            if not processing_completed:
                _logger.warning(
                    "Message processing did not complete within %s seconds. "
                    "Proceeding with shutdown (message may be redelivered)",
                    shutdown_timeout,
                )
        else:
            _logger.info("Waiting indefinitely for message processing to complete")
            self._processing_event.wait()

        try:
            self._pool_executor.shutdown(wait=processing_completed, cancel_futures=not processing_completed)
        except Exception:
            pass

        if self.subscribe_id and self.is_connected():
            self._unsubscribe()

        if self.is_connected():
            self.remove_listener(self.listener_name)
            self._disconnect()

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
        routing_key = destination.split("/")[-1]
        queue_name = queue_name if queue_name else routing_key
        if dlq:
            queue_name = f"DLQ.{queue_name}"
        headers.update(
            {
                "exclusive": settings.DEFAULT_EXCLUSIVE_QUEUE,
                "x-queue-name": queue_name,
                "x-dead-letter-routing-key": f"DLQ.DLQ.{queue_name}" if dlq else f"DLQ.{queue_name}",
                "x-dead-letter-exchange": "",
            }
        )
        if dlq:
            self.connection.subscribe(queue_name, subscribe_id, ack="client", headers=headers)
        else:
            self.connection.subscribe(destination, subscribe_id, ack="client", headers=headers)
        _logger.info("Created queue %s with id: %s", queue_name, subscribe_id)

    def _unsubscribe(self):
        self.connection.unsubscribe(self.subscribe_id)
        _logger.info("Subscription with id %s canceled", self.subscribe_id)
        self.subscribe_id = None

    def _remove_old_messages(self):
        if cache.get(settings.OUTBOX_PATTERN_CONSUMER_CACHE_KEY):
            return
        days_ago = timezone.now() - timedelta(days=settings.DAYS_TO_KEEP_DATA)
        self.received_class.objects.filter(added__lt=days_ago).delete()

        cache.set(settings.OUTBOX_PATTERN_CONSUMER_CACHE_KEY, True, settings.REMOVE_DATA_CACHE_TTL)
