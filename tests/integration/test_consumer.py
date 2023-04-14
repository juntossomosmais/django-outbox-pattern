from django.test import TransactionTestCase
from stomp.listener import TestListener

from django_outbox_pattern.factories import factory_consumer
from django_outbox_pattern.models import Received


def get_callback(raise_except=False):
    def callback(payload):  # pylint: disable=unused-argument
        if raise_except:
            raise KeyError("Test exception")
        payload.save()

    return callback


class ConsumerTest(TransactionTestCase):
    def setUp(self):
        self.consumer = factory_consumer()
        self.consumer.set_listener("test_listener", TestListener(print_to_log=True))
        self.listener = self.consumer.get_listener("test_listener")

    def test_when_message_handler_no_raise_exception(self):
        destination = "/topic/consumer.v0"
        callback = get_callback()
        self.consumer.start(callback, destination)
        self.consumer.connection.send(destination=destination, body='{"message": "Message test no raise"}')
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
        headers = {"msg-id": "fbb5aaf7-8c0b-453e-a23c-1b8a072a2573"}
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
