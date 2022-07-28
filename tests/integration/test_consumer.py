from django.test import TestCase
from stomp.listener import TestListener

from django_outbox_pattern.factories import factory_consumer


def get_callback(raise_except=False):
    def callback(payload):
        if raise_except:
            raise KeyError("Test exception")
    return callback


class ConsumerTest(TestCase):
    def setUp(self):
        self.consumer = factory_consumer()
        self.consumer.set_listener("test_listener", TestListener(print_to_log=True))
        self.listener = self.consumer.get_listener("test_listener")

    def test_when_message_handler_no_raise_exception(self):
        callback = get_callback()
        self.consumer.start(callback, "/topic/consumer.v0")
        self.consumer.connection.send(destination="/topic/consumer.v0", body='{"message": "Message test no raise"}')
        self.listener.wait_for_message()
        self.assertEqual(self.listener.connections, 1)
        self.assertEqual(self.listener.messages, 1)

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
        self.assertEqual(self.listener.connections, 1)
        self.assertEqual(self.listener.messages, 2)

    def test_when_message_handler_raise_exception(self):
        callback = get_callback(True)
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
