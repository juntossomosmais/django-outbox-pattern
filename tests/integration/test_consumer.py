from django.test import TestCase
from stomp.listener import TestListener

from django_outbox_pattern.factories import factory_consumer


def get_callback(action, raise_except=False):
    def callback(payload):
        if raise_except:
            raise KeyError("Test exception")
        getattr(payload, action)()

    return callback


class ConsumerTest(TestCase):
    def setUp(self):
        self.consumer = factory_consumer()
        self.consumer.set_listener("test_listener", TestListener(print_to_log=True))
        self.listener = self.consumer.get_listener("test_listener")

    def test_when_message_handler_no_raise_exception(self):
        callback = get_callback("ack")
        self.consumer.start(callback, "/topic/consumer.v1")
        self.consumer.connection.send(destination="/topic/consumer.v1", body='{"message": "Message test no raise"}')
        self.listener.wait_for_message()
        self.assertEqual(self.listener.connections, 1)
        self.assertEqual(self.listener.messages, 1)

    def test_when_message_handler_raise_exception(self):
        callback = get_callback("ack", True)
        self.consumer.start(callback, "/topic/consumer.v2")
        self.consumer.connection.send(destination="/topic/consumer.v2", body='{"message": "Message test raise"}')
        self.listener.wait_for_message()
        self.assertEqual(self.listener.connections, 1)
        self.assertEqual(self.listener.messages, 1)

    def test_when_not_started(self):
        self.consumer.stop()
        self.assertEqual(self.listener.connections, 0)
        self.assertEqual(self.listener.disconnects, 0)

    def test_when_start(self):
        self.consumer.start(lambda p: p, "destination")
        self.assertEqual(self.listener.connections, 1)

    def test_when_stop(self):
        self.consumer.start(lambda p: p, "destination")
        self.consumer.stop()
        self.listener.wait_on_disconnected()
        self.assertEqual(self.listener.connections, 1)
        self.assertEqual(self.listener.disconnects, 1)
