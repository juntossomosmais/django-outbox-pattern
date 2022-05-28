from django.test import TestCase
from stomp.listener import TestListener

from django_outbox_pattern.factories import factory_producer
from django_outbox_pattern.models import Published


class ProducerTest(TestCase):
    def test_producer_send(self):
        producer = factory_producer()
        producer.set_listener("test_listener", TestListener(print_to_log=True))
        producer.start()
        producer.connection.subscribe(destination="/topic/destination", id=1)
        listener = producer.get_listener("test_listener")
        message = Published(destination="/topic/destination", body={"message": "Message test"})
        producer.send(message)
        listener.wait_for_message()
        producer.stop()
        listener.wait_on_disconnected()
        self.assertEqual(listener.connections, 1)
        self.assertEqual(listener.messages, 1)
        self.assertEqual(listener.disconnects, 1)
