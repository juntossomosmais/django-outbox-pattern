import json

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.utils.module_loading import import_string

from django_outbox_pattern import settings


def generate_headers(message):
    return {
        "dop-msg-id": str(message.id),
        "dop-msg-destination": message.destination,
        "dop-msg-type": message.__class__.__name__,
        "dop-msg-sent-time": timezone.now(),
    }


def get_message_headers(published):
    if not published.headers:
        default_headers = import_string(settings.DEFAULT_GENERATE_HEADERS)
        return json.loads(json.dumps(default_headers(published), cls=DjangoJSONEncoder))
    return published.headers
