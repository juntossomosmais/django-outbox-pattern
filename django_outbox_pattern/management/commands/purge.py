import logging

from argparse import ArgumentParser
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.db.models import QuerySet
from django.db.models.query_utils import tree
from django.utils import timezone

from django_outbox_pattern.choices import StatusChoice
from django_outbox_pattern.models import Published
from django_outbox_pattern.models import Received

_logger = logging.getLogger("django_outbox_pattern")


class Command(BaseCommand):
    help = "Clean outbox received/published messages command"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--days", type=int, default=30, help="Days to keep data")
        parser.add_argument("--dry-run", action="store_true", help="Dry run")
        parser.add_argument("--purge-received-only", action="store_true", help="Purge received messages only")
        parser.add_argument("--purge-published-only", action="store_true", help="Purge published messages only")
        parser.add_argument("--include-scheduled", action="store_true", help="Include scheduled messages")
        parser.add_argument("--batch-size", type=int, default=500, help="Batch size")

    def _base_filter(self, days: int, include_scheduled: bool) -> tree.Node:
        filters = Q(added__lte=timezone.now() - timedelta(days=days))
        status_to_filter = [StatusChoice.SUCCEEDED, StatusChoice.FAILED]
        if include_scheduled:
            status_to_filter.append(StatusChoice.SCHEDULE)

        filters &= Q(status__in=status_to_filter)
        return filters

    def _delete_batch(self, queryset: QuerySet, batch_size: int, dry_run: bool) -> None:
        model_name = queryset.model._meta.verbose_name
        total = queryset.count()
        if dry_run:
            _logger.warning("Dry run would delete %d %s messages", total, model_name)
            return

        deleted = 0
        while pks := queryset.values_list("pk", flat=True)[:batch_size]:
            if not pks:
                break

            queryset.filter(pk__in=pks).delete()
            deleted += min(batch_size, len(pks))
            _logger.info("Deleted %d/%d %s messages", deleted, total, model_name)

        _logger.info("Deleted total of %d %s messages", total, model_name)

    def _purge(
        self, model: type[Published | Received], days: int, dry_run: bool, batch_size: int, include_scheduled: bool
    ) -> None:
        _logger.info("Purging %s messages for %d days...", model._meta.verbose_name, days)
        queryset = model.objects.filter(self._base_filter(days, include_scheduled))
        total = queryset.count()
        self._delete_batch(queryset, batch_size, dry_run)
        _logger.info("Deleted %d %s messages", total, model._meta.verbose_name)

    def handle(self, *args, **options) -> None:
        _logger.info("Purging outbox received/published messages...")

        days = options.get("days", 30)
        dry_run = options.get("dry_run", False)
        purge_received_only = options.get("purge_received_only", False)
        purge_published_only = options.get("purge_published_only", False)
        include_scheduled = options.get("include_scheduled", False)
        batch_size = options.get("batch_size", 500)

        _logger.info(
            "Days: %d, Dry run: %s, Purge received: %s, Purge published: %s, Include scheduled: %s, Batch size: %d",
            days,
            dry_run,
            purge_received_only,
            purge_published_only,
            include_scheduled,
            batch_size,
        )

        if purge_received_only and purge_published_only:
            _logger.warning("Purge received and purge published options cannot be used together")
            return

        if not purge_published_only:
            self._purge(Received, days, dry_run, batch_size, include_scheduled)

        if not purge_received_only:
            self._purge(Published, days, dry_run, batch_size, include_scheduled)

        _logger.info("Done!")
