from django.contrib import admin
from django.contrib.admin import ModelAdmin
from django.utils import timezone

from .models import Published
from .models import Received


@admin.register(Published)
class PublishedAdmin(ModelAdmin):
    list_display = ("destination", "body", "headers", "status", "expired")

    @admin.display(description="can be published?", boolean=True, ordering="expires_at")
    def expired(self, obj):
        return obj.expires_at >= timezone.now()


@admin.register(Received)
class ReceivedAdmin(ModelAdmin):
    list_display = ("destination", "body", "headers", "status")
