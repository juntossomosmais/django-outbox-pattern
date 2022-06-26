import json
from itertools import zip_longest

from django.core.serializers import serialize
from django.db import transaction

from django_outbox_pattern.models import Published


def publish(destinations, fields=None, serializers=None, version="v1"):
    if not isinstance(destinations, (list, tuple)):
        destinations = [destinations]
    if not isinstance(serializers, (list, tuple)):
        serializers = [serializers]

    def save(self, *args, **kwargs):
        with transaction.atomic():
            super(self.__class__, self).save(*args, **kwargs)
            for destination, serializer in zip_longest(destinations, serializers):
                _create_published(destination, fields, self, serializer, version)

    def decorator_publish(cls):
        cls.save = save
        return cls

    return decorator_publish


def _create_published(destination, fields, obj, serializer, version):
    body = _get_body(fields, obj, serializer)
    message = Published(version=version, destination=destination, body=body)
    message.save()


def _get_body(fields, obj, serializer):
    if serializer is not None and hasattr(obj, serializer):
        body = getattr(obj, serializer)()
    else:
        body = _serializer(obj, fields)
    return body


def _serializer(obj, fields):
    data = json.loads(serialize("json", [obj], fields=fields))[0]
    ret = {"id": data["pk"]}
    for key, value in data["fields"].items():
        ret[key] = value
    return ret
