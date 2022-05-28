import json

from django.core import serializers
from django.db import transaction

from django_outbox_pattern.models import Published


def publish(destination, fields=None, serializer="serializer", version="v1"):
    def save(self, *args, **kwargs):
        with transaction.atomic():
            super(self.__class__, self).save(*args, **kwargs)
            body = _get_body(fields, self, serializer)
            message = Published(version=version, destination=destination, body=body)
            message.save()

    def decorator_publish(cls):
        cls.save = save
        return cls

    return decorator_publish


def _get_body(fields, obj, serializer):
    if hasattr(obj, serializer):
        body = getattr(obj, serializer)()
    else:
        body = _serializer(obj, fields)
    return body


def _serializer(obj, fields):
    data = json.loads(serializers.serialize("json", [obj], fields=fields))[0]
    ret = {"id": data["pk"]}
    for key, value in data["fields"].items():
        ret[key] = value
    return ret
