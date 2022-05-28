from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from django_outbox_pattern.decorators import publish
from django_outbox_pattern.models import Published

User = get_user_model()


class PublisherDecoratorTestCase(TestCase):
    def setUp(self):
        self.email = "test@test.com"
        self.fields_expected = {
            "id": 1,
            "email": self.email,
            "username": "test",
        }

    def test_when_is_correct_queue_name(self):
        queue_name = "queue"
        user_publish = publish(destination=queue_name)(User)
        user_publish.objects.create(username="test")
        published = Published.objects.first()
        self.assertEqual(published.destination, f"{queue_name}.v1")

    def test_when_no_has_specified_field(self):
        date_joined = timezone.now()
        fields_expected = {
            "id": 1,
            "email": "",
            "groups": [],
            "is_staff": False,
            "password": "",
            "username": "test",
            "is_active": True,
            "last_name": "",
            "first_name": "",
            "last_login": None,
            "date_joined": date_joined.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3],
            "is_superuser": False,
            "user_permissions": [],
        }
        user_publish = publish(destination="queue")(User)
        user_publish.objects.create(username="test", date_joined=date_joined)
        published = Published.objects.first()
        self.assertEqual(published.body, fields_expected)

    def test_when_has_specified_fields(self):
        user_publish = publish(destination="queue", fields=["email", "username"])(User)
        user_publish.objects.create(username="test", email=self.email)
        published = Published.objects.first()
        self.assertEqual(published.body, self.fields_expected)

    def test_when_has_serializer_method(self):
        def my_serializer(obj):
            return {
                "id": obj.id,
                "email": obj.email,
                "username": obj.username,
            }

        User.my_serializer = my_serializer
        user_publish = publish(destination="queue", serializer="my_serializer")(User)
        user_publish.objects.create(username="test", email=self.email)
        published = Published.objects.first()
        self.assertEqual(published.body, self.fields_expected)
