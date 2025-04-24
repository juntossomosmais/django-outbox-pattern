# pylint: disable=protected-access
import json

from typing import List
from typing import NamedTuple
from typing import Optional

from django.core.serializers import serialize
from django.db import transaction

from django_outbox_pattern.models import Published


class Config(NamedTuple):
    destination: str
    fields: Optional[List[str]] = None
    serializer: Optional[str] = None
    version: Optional[str] = None


def publish(configs: List[Config]):
    def wrapper(cls):
        class PublishModel(cls):
            def save(self, *args, stop=False, **kwargs):
                with transaction.atomic():
                    super().save(*args, **kwargs)
                    if not stop:
                        for config in configs:
                            _create_published(self, *config)

            class Meta(getattr(cls, "Meta", object)):
                proxy = True
                app_label = cls._meta.app_label
                verbose_name = cls._meta.verbose_name
                verbose_name_plural = cls._meta.verbose_name_plural

        return PublishModel

    return wrapper


def _create_published(obj, destination, fields, serializer, version):
    body = _get_body(obj, fields, serializer)
    published = Published(body=body, destination=destination, version=version)
    published.save()


def _get_body(obj, fields, serializer):
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
