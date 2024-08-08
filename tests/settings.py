import os

SECRET_KEY = "django-insecure"

DEBUG = False

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django_outbox_pattern",
]

DATABASES = {
    "default": {
        "ENGINE": os.getenv("DB_ENGINE"),
        "NAME": os.getenv("DB_DATABASE"),
        "USER": os.environ.get("DB_USER"),
        "HOST": os.environ.get("DB_HOST"),
        "PORT": os.environ.get("DB_PORT"),
        "PASSWORD": os.environ.get("DB_PASSWORD"),
    }
}

DJANGO_OUTBOX_PATTERN = {"DEFAULT_STOMP_HOST_AND_PORTS": [("rabbitmq", 61613)]}

USE_TZ = False
