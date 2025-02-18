from datetime import datetime
from datetime import timedelta
from time import sleep
from unittest import mock

from django.core.cache import cache
from django.test import TransactionTestCase
from stomp.listener import TestListener

from django_outbox_pattern import settings
from django_outbox_pattern.factories import factory_consumer
from django_outbox_pattern.models import Received


def get_callback(raise_except=False):
    def callback(payload):
        if raise_except:
            raise KeyError("Test exception")
        payload.save()

    return callback


class ConsumerTest(TransactionTestCase):
    def setUp(self):
        self.consumer = factory_consumer()
        self.consumer.set_listener("test_listener", TestListener(print_to_log=True))
        self.listener = self.consumer.get_listener("test_listener")

    def tearDown(self) -> None:
        cache.delete(settings.OUTBOX_PATTERN_CONSUMER_CACHE_KEY)

    def test_when_message_handler_no_raise_exception(self):
        destination = "/topic/consumer.v0"
        callback = get_callback()
        self.consumer.start(callback, destination)
        self.consumer.connection.send(destination=destination, body='{"message": "mock message"}')
        self.listener.wait_for_message()
        received_message = self.listener.get_latest_message()
        assert received_message is not None
        self.assertEqual(1, self.listener.connections)
        self.assertEqual(1, self.listener.messages)
        count_message = Received.objects.all().count()
        self.assertEqual(1, count_message)

    def test_when_send_message_twice(self):
        callback = get_callback()
        destination = "/topic/consumer.v1"
        body = '{"message": "Message twice"}'
        headers = {"dop-msg-id": "fbb5aaf7-8c0b-453e-a23c-1b8a072a2573"}
        self.consumer.start(callback, destination)
        self.consumer.connection.send(destination=destination, body=body, headers=headers)
        self.consumer.connection.send(destination=destination, body=body, headers=headers)
        self.listener.wait_for_message()
        self.listener.wait_for_message()
        received_message = self.listener.get_latest_message()
        assert received_message is not None
        self.assertEqual(1, self.listener.connections)
        self.assertEqual(2, self.listener.messages)

        count_message = Received.objects.all().count()
        self.assertEqual(1, count_message)

    def test_when_message_handler_raise_exception(self):
        callback = get_callback(True)
        self.consumer.start(callback, "/topic/consumer.v2")
        self.consumer.connection.send(destination="/topic/consumer.v2", body='{"message": "Message test raise"}')
        self.listener.wait_for_message()
        self.assertEqual(1, self.listener.connections)
        self.assertEqual(1, self.listener.messages)

    def test_when_not_started(self):
        self.consumer.stop()
        self.assertEqual(0, self.listener.connections)
        self.assertEqual(0, self.listener.disconnects)

    def test_when_start(self):
        self.consumer.start(lambda p: p, "destination")
        self.assertEqual(1, self.listener.connections)

    def test_when_stop(self):
        self.consumer.start(lambda p: p, "destination")
        self.consumer.stop()
        self.listener.wait_on_disconnected()
        self.assertEqual(1, self.listener.connections)
        self.assertEqual(1, self.listener.disconnects)

    def test_consumer_message_should_remove_old_messages(self):
        self._create_message_in_the_past(31, 1)
        self._create_message_in_the_past(31, 2)
        self._create_message_in_the_past(31, 3)
        self._create_message_in_the_past(30, 4)
        self._create_message_in_the_past(29, 5)
        self._create_message_in_the_past(29, 6)

        destination = "/topic/consumer.v4"
        callback = get_callback()

        self.consumer.start(callback, destination)
        self.consumer.connection.send(destination=destination, body='{"message": "Message Body"}')
        self.listener.wait_for_message()
        received_message = self.listener.get_latest_message()

        assert received_message is not None
        self.assertEqual(1, self.listener.connections)
        self.assertEqual(1, self.listener.messages)
        count_message = Received.objects.all().count()
        self.assertEqual(3, count_message)
        self.assertFalse(self.consumer.received_class.objects.filter(msg_id=1).exists())
        self.assertFalse(self.consumer.received_class.objects.filter(msg_id=2).exists())
        self.assertFalse(self.consumer.received_class.objects.filter(msg_id=3).exists())
        self.assertFalse(self.consumer.received_class.objects.filter(msg_id=4).exists())

    def test_consumer_should_not_remove_old_message_when_cache_exists(self):
        self._create_message_in_the_past(35, 1)
        self.consumer._remove_old_messages()
        self.assertFalse(self.consumer.received_class.objects.filter(msg_id=1).exists())
        self._create_message_in_the_past(35, 2)
        self.consumer._remove_old_messages()
        self.assertTrue(self.consumer.received_class.objects.filter(msg_id=2).exists())

    def _create_message_in_the_past(self, day_ago, msg_id):
        now = datetime.now()
        date_days_ago = now - timedelta(days=day_ago)
        self.consumer.received_class(body={}, headers={}, msg_id=msg_id, added=date_days_ago).save()
        message = self.consumer.received_class.objects.filter(msg_id=msg_id).first()
        message.added = date_days_ago
        message.save()

    @mock.patch("django_outbox_pattern.consumers.cache")
    def test_consumer_should_consume_message_event_if_a_exception_happen_in_cache(self, mock_cache):
        mock_cache.get.side_effect = Exception("Cache get failed")
        destination = "/topic/consumer.v5"
        callback = get_callback()
        self.consumer.start(callback, destination)
        with self.assertRaises(Exception):  # noqa
            self.consumer.connection.send(destination=destination, body='{"message": "Message test no raise"}')
            sleep(1)
            self.listener.get_latest_message()

        count_message = Received.objects.all().count()
        self.assertEqual(1, count_message)

        mock_cache.get.assert_called_once_with(settings.OUTBOX_PATTERN_CONSUMER_CACHE_KEY)
