"""
Django settings for django outbox pattern project.

"""

SECRET_KEY = "django-insecure"

DEBUG = True

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
