from django.contrib import admin
from django.contrib.admin import ModelAdmin
from django.utils import timezone

from .models import Published
from .models import Received


@admin.register(Published)
class PublishedAdmin(ModelAdmin):
    ordering = ["-added"]
    list_display = ("destination", "body", "headers", "status", "expired", "added")
    search_fields = ["destination"]
    list_filter = ["added"]

    @admin.display(description="can be published?", boolean=True, ordering="expires_at")
    def expired(self, obj):
        return obj.expires_at >= timezone.now()


@admin.register(Received)
class ReceivedAdmin(ModelAdmin):
    ordering = ["-added"]
    list_display = ("destination", "body", "headers", "status", "added")
    search_fields = ["headers"]
    list_filter = ["added"]
