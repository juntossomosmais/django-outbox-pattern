import json

from uuid import uuid4

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.utils.module_loading import import_string
from request_id_django_log.request_id import current_request_id
from request_id_django_log.settings import NO_REQUEST_ID

from django_outbox_pattern import settings


def generate_headers(message):
    correlation_id = current_request_id()
    if not correlation_id or correlation_id == NO_REQUEST_ID:
        correlation_id = uuid4()

    return {
        "dop-msg-id": str(message.id),
        "dop-msg-destination": message.destination,
        "dop-msg-type": message.__class__.__name__,
        "dop-msg-sent-time": timezone.now(),
        "dop-correlation-id": correlation_id,
    }


def get_message_headers(published):
    default_headers = import_string(settings.DEFAULT_GENERATE_HEADERS)(published)
    return json.loads(
        json.dumps(
            default_headers if not published.headers else published.headers | default_headers, cls=DjangoJSONEncoder
        )
    )
