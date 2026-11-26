# Changelog

All notable changes to `django-outbox-pattern` will be documented in this file.

## [3.3.0] - 2026-11-26

### Features

- Added the `DEFAULT_CONSUMER_LOG_MESSAGE_ID_KEY` setting: the `extra` key under which consumer logs related to a message
  carry its id. The default is the legacy name `MessageId`, so services keep their current logging pipeline. Services
  whose pipeline accepts dotted keys (for example, services that write the `jsm.log.schema: v2` route marker) can set it
  to the OpenTelemetry semantic convention key `messaging.message.id`. An invalid value (empty, not a string, or a
  `LogRecord` attribute such as `message`) raises `ImproperlyConfigured` when the consumer is created.

### Changes

- Moved the per-message receipt log from the STOMP listener (`ConsumerListener.on_message`) to the start of
  `Consumer.message_handler`. The log was emitted on the STOMP receiver thread before any tracing span existed, so it
  carried no `trace_id`/`span_id`. It now runs inside the span that tracing instrumentations wrapping
  `message_handler` (such as `opentelemetry-instrumentation-django-outbox-pattern`) open, in both synchronous and
  background processing modes, as long as the instrumentation manages to create the span. It is also emitted after the
  correlation id is set, so it carries the correlation id of the message (taken from the `dop-correlation-id` header,
  or generated when the header is absent).
- Removed the debug logs with the full message body and headers (`Message body received: ...` and
  `Message headers received: ...`), since they could expose personal data or sensitive header values.
- In background processing mode (`DEFAULT_CONSUMER_PROCESS_MSG_ON_BACKGROUND`), the receipt log now marks the moment the
  worker starts processing the message, not the moment the broker delivered it. Messages waiting in the worker queue are
  not logged until they are picked up, and messages cancelled by a shutdown timeout are never logged as received (they
  are redelivered by the broker).
- Custom listener classes (`DEFAULT_CONSUMER_LISTENER_CLASS`) that override `on_message` with their own receipt log and
  still call `Consumer.handle_incoming_message` now get two receipt logs per message.
- Consumer logs related to a message now carry the message id in the `extra` key set by
  `DEFAULT_CONSUMER_LOG_MESSAGE_ID_KEY` instead of interpolating it into the message text, which keeps log message
  cardinality low.
- The id logged on receipt is now the deduplication id, resolved as `cap-msg-id`, then `dop-msg-id`, then the broker
  `message-id`. Previously it was always the broker `message-id`.
- The warnings for messages skipped or discarded during shutdown, and for the worker pool being recreated, now also
  carry the message id.
- A message body that cannot be decoded is now logged as a warning (with the exception attached) instead of an error,
  since the raw body is still handed to the callback, which decides to save or nack the message.
- Dashboards or alerts filtering on the old texts must be updated:

  | Before | After |
  |---|---|
  | `Message id received: <broker message-id>` (INFO) | `Message received` (INFO) |
  | `Message with msg_id: <id> already exists. discarding the message` | `Message already exists, discarding the message` |
  | `The save or nack command was not executed, ... message-id: <id>` | `The save or nack command was not executed, ...` |
  | `All <n> retries exhausted, sending to DLQ, message-id: <id>` | `All <n> retries exhausted, sending to DLQ` |
  | `<JSONDecodeError message>` (ERROR) | `Message body is not valid JSON` (WARNING, exception attached) |
  | `OperationalError while removing old messages, skipping cleanup this cycle` | `Error while removing old messages, skipping cleanup this cycle` (exception attached) |

  The texts of `Retry <n>/<max> failed, retrying in <s>s` and of the shutdown and worker pool warnings are unchanged;
  they only gained the message id field.

### Fixes

- `Consumer.message_handler` now always restores its state, even when an error happens before the message is processed
  or while removing old messages. Previously, such an error could leave the processing flag cleared, which made
  `Consumer.stop()` wait for the whole shutdown timeout (or forever when no timeout is configured), and leave the
  correlation id set on the thread for the next message. Any error while removing old messages (not only
  `OperationalError`, for example a cache backend outage) is now logged and skipped.
- A message body that cannot be decoded, including a non-string body (for example `None`) and bytes with invalid UTF-8,
  is now logged and handed to the callback as is. Previously, these raised outside the error handling and the message
  was left unacknowledged until it was redelivered. A body that is already a `dict` or `list` (for example, from a
  custom listener) is now passed to the callback without being decoded.
- Messages without any id header (`cap-msg-id`, `dop-msg-id` or `message-id`) are no longer discarded as duplicates of
  the first id-less message stored in the database.
- The consumer listener now ignores messages that arrive after the consumer unsubscribed, instead of raising
  `TypeError` on the STOMP receiver thread.

## [3.2.1] - 2026-08-25

### Fixes

- Fixed the publisher (`Producer.publish_message_from_database`) getting stuck reusing a broken database connection
  after a transient `django.db.DatabaseError` (for example, a database or network hiccup). It now calls
  `django.db.close_old_connections()` before waiting for the next polling iteration, discarding the broken connection
  so a new one is opened automatically as soon as the database is available again. Previously, the process required a
  manual restart to recover once the connection broke.

## [3.2.0] - 2026-07-22

### Features

- Custom headers passed via `Published.objects.create(headers={...})` can now override the
  `dop-correlation-id` default header. This allows consumers to set a unique `dop-correlation-id`
  per published message, keeping individual traceability in the logs even when several messages
  are published within the same callback. Behaviour is unchanged when no custom headers are
  provided: the `dop-correlation-id` still comes from the thread-local request id or is generated
  automatically. Other default headers, such as `dop-msg-id`, always come from the automatically
  generated value and cannot be overridden, since the consumer relies on `dop-msg-id` to detect
  duplicate messages.
- Added automatic retry with linear backoff for `django.db.OperationalError` in the consumer
  message handler, covering both the idempotency check and the callback execution. Transient
  database errors (for example, a DNS failure) are retried up to
  `DEFAULT_CONSUMER_MAX_RETRY_ATTEMPTS` times, waiting `DEFAULT_CONSUMER_RETRY_WAIT` seconds
  multiplied by the attempt number between tries, before the message is sent to the DLQ. The
  idempotency check is re-evaluated on every retry attempt, so a message that was already
  persisted before a connection drop is acknowledged instead of causing a duplicate insert. Any
  other exception results in an immediate nack, including when it is raised during a retry
  attempt. Two new configurable settings were added: `DEFAULT_CONSUMER_MAX_RETRY_ATTEMPTS` (default `3`)
  and `DEFAULT_CONSUMER_RETRY_WAIT` (default `2`).
