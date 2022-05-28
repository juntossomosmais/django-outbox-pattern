import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone

from django_outbox_pattern.choices import StatusChoice


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
    version = models.CharField(max_length=100, default="v1")
    destination = models.CharField(max_length=255)
    body = models.JSONField()
    added = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_one_more_day)
    retry = models.PositiveIntegerField(default=0)
    status = models.IntegerField(choices=StatusChoice.choices, default=StatusChoice.SCHEDULE)

    class Meta:
        verbose_name = "published"
        db_table = "published"

    def __str__(self):
        return f"{self.destination} - {self.body}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            self.destination = f"{self.destination}.{self.version}"
        super().save(*args, **kwargs)


class Received(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        editable=False,
        help_text="Id not sequential using UUID Field",
    )
    headers = models.JSONField(null=True)
    body = models.JSONField(null=True)
    added = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_one_more_day)
    retry = models.PositiveIntegerField(default=0)
    status = models.IntegerField(choices=StatusChoice.choices, default=StatusChoice.SUCCEEDED)

    @property
    def destination(self):
        return self.headers.get("destination")

    class Meta:
        verbose_name = "received"
        db_table = "received"

    def __str__(self):
        return f"{self.destination} - {self.body}"
