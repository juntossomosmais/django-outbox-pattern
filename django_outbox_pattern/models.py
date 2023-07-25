import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone

from django_outbox_pattern.choices import StatusChoice
from django_outbox_pattern.headers import get_message_headers


def _one_more_day():
    return timezone.now() + timedelta(1)


class Published(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Id not sequential using UUID Field",
    )
    version = models.CharField(max_length=100, null=True)
    destination = models.CharField(max_length=255)
    body = models.JSONField()
    added = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(default=_one_more_day)
    retry = models.PositiveIntegerField(default=0)
    status = models.IntegerField(choices=StatusChoice.choices, default=StatusChoice.SCHEDULE)
    headers = models.JSONField(default=dict)

    class Meta:
        verbose_name = "published"
        db_table = "published"

    def __str__(self):
        return f"{self.destination} - {self.body}"

    def save(self, *args, **kwargs):
        if self._state.adding and self.version:
            self.destination = f"{self.destination}.{self.version}"
        self.headers = get_message_headers(self)

        super().save(*args, **kwargs)


class Received(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Id not sequential using UUID Field",
    )
    msg_id = models.CharField(max_length=100, null=True, unique=True, db_index=True)
    headers = models.JSONField(null=True)
    body = models.JSONField(null=True)
    added = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(default=_one_more_day)
    retry = models.PositiveIntegerField(default=0)
    status = models.IntegerField(choices=StatusChoice.choices, default=StatusChoice.SUCCEEDED)

    @property
    def destination(self):
        return self.headers.get("destination", "") if self.headers else ""

    class Meta:
        verbose_name = "received"
        db_table = "received"

    def __str__(self):
        return f"{self.destination} - {self.body}"
