# Changelog

All notable changes to `django-outbox-pattern` will be documented in this file.

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
