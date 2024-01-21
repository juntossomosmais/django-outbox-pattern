from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from django_outbox_pattern.decorators import Config
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

    def create_user(self, model):
        return model.objects.create(username="test", email=self.email)

    def test_when_is_correct_destination(self):
        destination = "queue"
        user_publish = publish([Config(destination=destination, version="v1")])(User)
        self.create_user(user_publish)
        published = Published.objects.first()
        self.assertEqual(published.destination, f"{destination}.v1")

    def test_when_no_has_specified_field(self):
        # arrange
        date_joined = timezone.now()
        user_publish = publish([Config(destination="destination")])(User)

        # act
        user_publish.objects.create(username="test", date_joined=date_joined)

        # assert
        published = Published.objects.first()
        self.assertEqual("", published.body["email"])
        self.assertEqual([], published.body["groups"])
        self.assertFalse(published.body["is_staff"])
        self.assertEqual("", published.body["password"])
        self.assertEqual("test", published.body["username"])
        self.assertTrue(published.body["is_active"])
        self.assertEqual("", published.body["last_name"])
        self.assertEqual("", published.body["first_name"])
        self.assertIsNone(published.body["last_login"])
        self.assertEqual(date_joined.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3], published.body["date_joined"])
        self.assertFalse(published.body["is_superuser"])
        self.assertEqual([], published.body["user_permissions"])

    def test_when_has_specified_fields(self):
        user_publish = publish([Config(destination="destination", fields=["email", "username"])])(User)
        self.create_user(user_publish)
        published = Published.objects.first()

        self.assertEqual(self.fields_expected["email"], published.body["email"])
        self.assertEqual(self.fields_expected["username"], published.body["username"])

    def test_when_has_serializer_method(self):
        def my_serializer(obj):
            return {
                "id": obj.id,
                "email": obj.email,
                "username": obj.username,
            }

        User.my_serializer = my_serializer
        user_publish = publish([Config(destination="destination", serializer="my_serializer")])(User)
        self.create_user(user_publish)
        published = Published.objects.first()

        self.assertEqual(self.fields_expected["email"], published.body["email"])
        self.assertEqual(self.fields_expected["username"], published.body["username"])

    def test_when_has_multi_destinations_and_no_serializers(self):
        destination_1 = "queue_1"
        destination_2 = "queue_2"
        user_publish = publish(
            [
                Config(destination=destination_1, fields=["email", "username"]),
                Config(destination=destination_2, fields=["email", "username"]),
            ]
        )(User)
        self.create_user(user_publish)
        published = Published.objects.all()

        self.assertEqual(self.fields_expected["email"], published[0].body["email"])
        self.assertEqual(self.fields_expected["username"], published[0].body["username"])
        self.assertEqual("queue_1", published[0].destination)

        self.assertEqual(self.fields_expected["email"], published[1].body["email"])
        self.assertEqual(self.fields_expected["username"], published[1].body["username"])
        self.assertEqual("queue_2", published[1].destination)

    def test_when_has_multi_destinations_and_one_serializer(self):
        destination_1 = "queue_1"
        destination_2 = "queue_2"
        date_joined = timezone.now()

        def my_serializer_1(obj):
            return {
                "id": obj.id,
                "email": obj.email,
            }

        User.my_serializer_1 = my_serializer_1
        user_publish = publish(
            [Config(destination=destination_1, serializer="my_serializer_1"), Config(destination=destination_2)]
        )(User)
        self.create_user(user_publish)
        published = Published.objects.all()

        self.assertEqual(self.email, published[0].body["email"])
        self.assertEqual("queue_1", published[0].destination)

        self.assertEqual(self.email, published[1].body["email"])
        self.assertEqual([], published[1].body["groups"])
        self.assertFalse(published[1].body["is_staff"])
        self.assertEqual("", published[1].body["password"])
        self.assertEqual("test", published[1].body["username"])
        self.assertTrue(published[1].body["is_active"])
        self.assertEqual("", published[1].body["last_name"])
        self.assertEqual("", published[1].body["first_name"])
        self.assertIsNone(published[1].body["last_login"])
        self.assertFalse(published[1].body["is_superuser"])
        self.assertEqual([], published[1].body["user_permissions"])
        self.assertEqual("queue_2", published[1].destination)

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
            [
                Config(destination=destination_1, serializer="my_serializer_1"),
                Config(destination=destination_2, serializer="my_serializer_2"),
            ]
        )(User)
        self.create_user(user_publish)
        published = Published.objects.all()
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

    def test_when_overriding_save_method(self):
        def save(self, *args, **kwargs):
            self.username = "test orverridden"
            super(User, self).save(*args, **kwargs)

        User.save = save
        user_publish = publish([Config(destination="destination")])(User)
        user = self.create_user(user_publish)
        self.assertEqual(user.username, "test orverridden")
