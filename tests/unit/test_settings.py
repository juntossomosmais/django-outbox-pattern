import types

from django.test import TestCase
from django.test import override_settings

from django_outbox_pattern.settings import settings


class SettingsTest(TestCase):
    def test_compatibility_with_override_settings(self):

        assert isinstance(
            settings.DEFAULT_GENERATE_HEADERS, types.FunctionType
        ), "Checking a known default should be func"

        with override_settings(DJANGO_OUTBOX_PATTERN={"DEFAULT_GENERATE_HEADERS": None}):
            assert settings.DEFAULT_GENERATE_HEADERS is None, "Setting should have been updated"

        assert isinstance(settings.DEFAULT_GENERATE_HEADERS, types.FunctionType), "Setting should have been restored"
