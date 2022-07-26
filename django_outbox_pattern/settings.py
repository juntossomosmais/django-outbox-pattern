"""
Settings for DJANGO OUTBOX are all namespaced in the DJANGO_OUTBOX_PATTERN  setting.
For example your project's `settings.py` file might look like this:
DJANGO_OUTBOX_PATTERN = {
    'DEFAULT_GENERATE_HEADERS': 'django_outbox_pattern.headers.handle_headers'
}

Thanks Django Rest Framework: https://github.com/encode/django-rest-framework/blob/master/rest_framework/settings.py

"""

from django.conf import settings as django_settings
from django.test.signals import setting_changed
from django.utils.module_loading import import_string

DEFAULTS = {
    "DEFAULT_CONNECTION_CLASS": "stomp.StompConnection12",
    "DEFAULT_CONSUMER_LISTENER_CLASS": "django_outbox_pattern.listeners.ConsumerListener",
    "DEFAULT_GENERATE_HEADERS": "django_outbox_pattern.headers.generate_headers",
    "DEFAULT_MAXIMUM_BACKOFF": 3600,
    "DEFAULT_MAXIMUM_RETRY_ATTEMPTS": 50,
    "DEFAULT_PAUSE_FOR_RETRY": 240,
    "DEFAULT_WAIT_RETRY": 60,
    "DEFAULT_PRODUCER_LISTENER_CLASS": "django_outbox_pattern.listeners.ProducerListener",
    "DEFAULT_PUBLISHED_CLASS": "django_outbox_pattern.models.Published",
    "DEFAULT_RECEIVED_CLASS": "django_outbox_pattern.models.Received",
    "DEFAULT_STOMP_HOST_AND_PORTS": [("127.0.0.1", 61613)],
    "DEFAULT_STOMP_QUEUE_HEADERS": {"durable": "true", "auto-delete": "false", "prefetch-count": "1"},
    "DEFAULT_STOMP_HEARTBEATS": (10000, 10000),
    "DEFAULT_STOMP_VHOST": "/",
    "DEFAULT_STOMP_USERNAME": "guest",
    "DEFAULT_STOMP_PASSCODE": "guest",
    "DEFAULT_STOMP_USE_SSL": False,
    "DEFAULT_STOMP_KEY_FILE": None,
    "DEFAULT_STOMP_CERT_FILE": None,
    "DEFAULT_STOMP_CA_CERTS": None,
    "DEFAULT_STOMP_CERT_VALIDATOR": None,
    "DEFAULT_STOMP_SSL_VERSION": None,
    "DEFAULT_STOMP_SSL_PASSWORD": None,
}

# List of settings that may be in string import notation.
IMPORT_STRINGS = [
    "DEFAULT_CONNECTION_CLASS",
    "DEFAULT_CONSUMER_LISTENER_CLASS",
    "DEFAULT_GENERATE_HEADERS",
    "DEFAULT_PRODUCER_LISTENER_CLASS",
    "DEFAULT_PUBLISHED_CLASS",
    "DEFAULT_RECEIVED_CLASS",
    "DEFAULT_STOMP_CERT_VALIDATOR",
]


def perform_import(val, setting_name):
    """
    If the given setting is a string import notation,
    then perform the necessary import or imports.
    """

    if isinstance(val, str):
        val = import_from_string(val, setting_name)
    elif isinstance(val, (list, tuple)):
        val = [import_from_string(item, setting_name) for item in val]
    return val


def import_from_string(val, setting_name):
    """
    Attempt to import a class from a string representation.
    """
    try:
        return import_string(val)
    except ImportError as exc:
        msg = f"Could not import '{val}' for setting '{setting_name}'. {exc.__class__}: {exc}."
        raise ImportError(msg) from exc


class Setting:
    """
    A settings object that allows DJANGO OUTBOX PATTERN settings to be accessed as
    """

    def __init__(self, user_settings=None, defaults=None, import_strings=None):
        if user_settings:
            self._user_settings = user_settings
        self.defaults = defaults or DEFAULTS
        self.import_strings = import_strings or IMPORT_STRINGS
        self._cached_attrs = set()

    @property
    def user_settings(self):
        if not hasattr(self, "_user_settings"):
            self._user_settings = getattr(django_settings, "DJANGO_OUTBOX_PATTERN", {})
        return self._user_settings

    def __getattr__(self, attr):
        if attr not in self.defaults:
            raise AttributeError(f"Invalid setting: '{attr}'")

        try:
            # Check if present in user settings
            val = self.user_settings[attr]
        except KeyError:
            # Fall back to defaults
            val = self.defaults[attr]

        # Coerce import strings into classes
        if attr in self.import_strings:
            val = perform_import(val, attr)

        # Cache the result
        self._cached_attrs.add(attr)
        setattr(self, attr, val)
        return val

    def reload(self):
        for attr in self._cached_attrs:
            delattr(self, attr)
        self._cached_attrs.clear()
        if hasattr(self, "_user_settings"):
            delattr(self, "_user_settings")


settings = Setting(None, DEFAULTS, IMPORT_STRINGS)


def reload_settings(*args, **kwargs):  # pylint:: disable=unused-argument
    setting = kwargs["setting"]
    if setting == "DJANGO_OUTBOX_PATTERN":
        settings.reload()


setting_changed.connect(reload_settings)
