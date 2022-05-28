# Generated by Django 3.2.13 on 2022-06-09 12:27

import uuid

from django.db import migrations
from django.db import models

import django_outbox_pattern.models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Published",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Id not sequential using UUID Field",
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                ("version", models.CharField(default="v1", max_length=100)),
                ("destination", models.CharField(max_length=255)),
                ("body", models.JSONField()),
                ("added", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField(default=django_outbox_pattern.models._one_more_day)),
                ("retry", models.PositiveIntegerField(default=0)),
                ("status", models.IntegerField(choices=[(-1, "Failed"), (1, "Schedule"), (2, "Succeeded")], default=1)),
            ],
            options={
                "verbose_name": "published",
                "db_table": "published",
            },
        ),
        migrations.CreateModel(
            name="Received",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Id not sequential using UUID Field",
                        primary_key=True,
                        serialize=False,
                        unique=True,
                    ),
                ),
                ("headers", models.JSONField(null=True)),
                ("body", models.JSONField(null=True)),
                ("added", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField(default=django_outbox_pattern.models._one_more_day)),
                ("retry", models.PositiveIntegerField(default=0)),
                ("status", models.IntegerField(choices=[(-1, "Failed"), (1, "Schedule"), (2, "Succeeded")], default=2)),
            ],
            options={
                "verbose_name": "received",
                "db_table": "received",
            },
        ),
    ]
