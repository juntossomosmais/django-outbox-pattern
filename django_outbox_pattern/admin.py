from django.contrib import admin
from django.contrib.admin import ModelAdmin

from .models import Published
from .models import Received


@admin.register(Published)
class PublishedAdmin(ModelAdmin):
    list_display = ("destination", "body", "status")


@admin.register(Received)
class ReceivedAdmin(ModelAdmin):
    list_display = ("destination", "body", "status")
