import json
from datetime import datetime
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from stomp.listener import TestListener

from django_outbox_pattern import settings
from django_outbox_pattern.factories import factory_producer
from django_outbox_pattern.models import Published


class ProducerTest(TestCase):
    fake_destination = "/topic/destination_send_event_context"

    def tearDown(self) -> None:
        cache.delete(settings.OUTBOX_PATTERN_PUBLISHER_CACHE_KEY)

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
        some_body = {"message": "fake body"}
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
            producer.connection.subscribe(destination=self.fake_destination, id=1)
            listener = producer.get_listener("test_listener")
            producer.send_event(destination=self.fake_destination, body={"message": "fake message body"})
            listener.wait_for_message()
        listener.wait_on_disconnected()
        self.assertEqual(1, listener.messages)
        self.assertEqual(1, listener.disconnects)

    def test_producer_should_remove_old_messages(self):
        ms1 = self._create_message_in_the_past(31)
        ms2 = self._create_message_in_the_past(31)
        ms3 = self._create_message_in_the_past(31)
        ms4 = self._create_message_in_the_past(30)
        ms5 = self._create_message_in_the_past(29)
        ms6 = self._create_message_in_the_past(29)

        with factory_producer() as producer:
            producer.set_listener("test_listener", TestListener(print_to_log=True))
            producer.connection.subscribe(destination=self.fake_destination, id=1)
            listener = producer.get_listener("test_listener")
            producer.send_event(destination=self.fake_destination, body={"message": "Test send event"})
            listener.wait_for_message()
        listener.wait_on_disconnected()
        self.assertEqual(1, listener.messages)
        self.assertEqual(1, listener.disconnects)

        self.assertFalse(Published.objects.filter(id=ms1.id).exists())
        self.assertFalse(Published.objects.filter(id=ms2.id).exists())
        self.assertFalse(Published.objects.filter(id=ms3.id).exists())
        self.assertFalse(Published.objects.filter(id=ms4.id).exists())
        self.assertTrue(Published.objects.filter(id=ms5.id).exists())
        self.assertTrue(Published.objects.filter(id=ms6.id).exists())

        self.assertEqual(2, Published.objects.count())

    def test_consumer_should_not_remove_old_message_when_cache_exists(self):
        message = self._create_message_in_the_past(31)
        producer = factory_producer()
        producer._remove_old_messages()  # pylint: disable=W0212
        self.assertFalse(Published.objects.filter(id=message.id).exists())
        message1 = self._create_message_in_the_past(31)
        producer._remove_old_messages()  # pylint: disable=W0212
        self.assertTrue(Published.objects.filter(id=message1.id).exists())

    @mock.patch("django_outbox_pattern.producers.cache")
    def test_producer_should_send_message_event_if_a_exception_happen_in_cache(self, mock_cache):
        mock_cache.get.side_effect = Exception("Cache get failed")
        with factory_producer() as producer:
            producer.set_listener("test_listener", TestListener(print_to_log=True))
            producer.connection.subscribe(destination=self.fake_destination, id=1)
            listener = producer.get_listener("test_listener")
            with self.assertRaises(Exception):
                producer.send_event(destination=self.fake_destination, body={"message": "fake message body"})

            listener.wait_for_message()

        listener.wait_on_disconnected()
        self.assertEqual(1, listener.messages)
        self.assertEqual(1, listener.disconnects)

        mock_cache.get.assert_called_once_with(settings.OUTBOX_PATTERN_PUBLISHER_CACHE_KEY)

    def _create_message_in_the_past(self, day_ago):
        now = datetime.now()
        date_days_ago = now - timedelta(days=day_ago)
        message = Published(body={})
        message.save()
        message.added = date_days_ago
        message.save()
        return message
