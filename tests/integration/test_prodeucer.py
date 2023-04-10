import json

from django.test import TestCase
from stomp.listener import TestListener

from django_outbox_pattern.factories import factory_producer
from django_outbox_pattern.models import Published


class ProducerTest(TestCase):
    def test_producer_send(self):
        some_body = {"message": "Message test"}
        some_destination = "/topic/destination"
        producer = factory_producer()
        producer.set_listener("test_listener", TestListener(print_to_log=True))
        producer.start()
        producer.connection.subscribe(destination=some_destination, id=1)
        listener = producer.get_listener("test_listener")
        message = Published(destination=some_destination, body=some_body)
        producer.send(message)
        listener.wait_for_message()

        received_message = listener.get_latest_message()
        assert received_message is not None

        producer.stop()
        listener.wait_on_disconnected()
        self.assertEqual(1, listener.connections)
        self.assertEqual(1, listener.messages)
        self.assertEqual(1, listener.disconnects)

        received_header = received_message[0]
        assert received_header["destination"] == some_destination
        assert received_header["message-id"] is not None
        received_body = json.loads(received_message[1])
        assert received_body == some_body

    def test_producer_send_event(self):
        some_body = {"message": "Test send event"}
        some_destination = "/topic/destination_send_event"
        producer = factory_producer()
        producer.set_listener("test_listener", TestListener(print_to_log=True))
        producer.start()
        producer.connection.subscribe(destination=some_destination, id=1)
        listener = producer.get_listener("test_listener")
        producer.send_event(destination=some_destination, body=some_body)

        listener.wait_for_message()
        received_message = listener.get_latest_message()
        assert received_message is not None

        producer.stop()
        listener.wait_on_disconnected()
        self.assertEqual(1, listener.connections)
        self.assertEqual(1, listener.messages)
        self.assertEqual(1, listener.disconnects)

        received_header = received_message[0]
        assert received_header["destination"] == some_destination
        assert received_header["message-id"] is not None
        received_body = json.loads(received_message[1])
        assert received_body == some_body

    def test_producer_send_event_with_context_manager(self):
        with factory_producer() as producer:
            producer.set_listener("test_listener", TestListener(print_to_log=True))
            producer.connection.subscribe(destination="/topic/destination_send_event_context", id=1)
            listener = producer.get_listener("test_listener")
            producer.send_event(
                destination="/topic/destination_send_event_context", body={"message": "Test send event"}
            )
            listener.wait_for_message()
        listener.wait_on_disconnected()
        self.assertEqual(1, listener.messages)
        self.assertEqual(1, listener.disconnects)
