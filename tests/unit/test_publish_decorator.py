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

    def assert_destination(self, published, destination_1, destination_2):
        self.assertEqual(published[0].destination, f"{destination_1}.v1")
        self.assertEqual(published[1].destination, f"{destination_2}.v1")

    def create_user(self, model):
        model.objects.create(username="test", email=self.email)

    def test_when_is_correct_destination(self):
        destination = "queue"
        user_publish = publish(destinations=destination)(User)
        self.create_user(user_publish)
        published = Published.objects.first()
        self.assertEqual(published.destination, f"{destination}.v1")

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
        user_publish = publish(destinations="queue")(User)
        user_publish.objects.create(username="test", date_joined=date_joined)
        published = Published.objects.first()
        self.assertEqual(published.body, fields_expected)

    def test_when_has_specified_fields(self):
        user_publish = publish(destinations="queue", fields=["email", "username"])(User)
        self.create_user(user_publish)
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
        user_publish = publish(destinations="queue", serializers="my_serializer")(User)
        self.create_user(user_publish)
        published = Published.objects.first()
        self.assertEqual(published.body, self.fields_expected)

    def test_when_has_multi_destinations_and_no_serializers(self):
        destination_1 = "queue_1"
        destination_2 = "queue_2"
        user_publish = publish(destinations=[destination_1, destination_2], fields=["email", "username"])(User)
        self.create_user(user_publish)
        published = Published.objects.all()
        self.assert_destination(published, destination_1, destination_2)
        self.assertEqual(published[0].body, self.fields_expected)
        self.assertEqual(published[1].body, self.fields_expected)

    def test_when_has_multi_destinations_and_one_serializer(self):
        destination_1 = "queue_1"
        destination_2 = "queue_2"
        date_joined = timezone.now()
        fields_expected = {
            "id": 1,
            "email": self.email,
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

        def my_serializer_1(obj):
            return {
                "id": obj.id,
                "email": obj.email,
            }

        User.my_serializer_1 = my_serializer_1
        user_publish = publish(destinations=[destination_1, destination_2], serializers="my_serializer_1")(User)
        self.create_user(user_publish)
        published = Published.objects.all()
        self.assert_destination(published, destination_1, destination_2)
        self.assertEqual(
            published[0].body,
            {
                "id": 1,
                "email": self.email,
            },
        )
        self.assertEqual(published[1].body, fields_expected)

    def test_when_has_multi_destinations_and_multi_serializers(self):
        destination_1 = "queue_1"
        destination_2 = "queue_2"

        def my_serializer_1(obj):
            return {
                "id": obj.id,
                "email": obj.email,
            }

        def my_serializer_2(obj):
            return {
                "id": obj.id,
                "username": obj.username,
            }

        User.my_serializer_1 = my_serializer_1
        User.my_serializer_2 = my_serializer_2
        user_publish = publish(
            destinations=[destination_1, destination_2],
            serializers=["my_serializer_1", "my_serializer_2"],
        )(User)
        self.create_user(user_publish)
        published = Published.objects.all()
        self.assert_destination(published, destination_1, destination_2)
        self.assertEqual(
            published[0].body,
            {
                "id": 1,
                "email": self.email,
            },
        )
        self.assertEqual(
            published[1].body,
            {
                "id": 1,
                "username": "test",
            },
        )
