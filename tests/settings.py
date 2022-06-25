"""
Django settings for django outbox pattern project.

"""

SECRET_KEY = "django-insecure"

DEBUG = False

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django_outbox_pattern",
]

ROOT_URLCONF = __name__

urlpatterns = []

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "db.sqlite3",
    }
}

DJANGO_OUTBOX_PATTERN = {
    "DEFAULT_STOMP_HOST_AND_PORTS": [("rabbitmq", 61613)],
}
