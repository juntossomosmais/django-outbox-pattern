from django_outbox_pattern.consumers import Consumer
from django_outbox_pattern.producers import Producer
from django_outbox_pattern.settings import settings

USERNAME = settings.DEFAULT_STOMP_USERNAME
PASSCODE = settings.DEFAULT_STOMP_PASSCODE


def factory_connection():
    host_and_ports = settings.DEFAULT_STOMP_HOST_AND_PORTS
    heartbeats = settings.DEFAULT_STOMP_HEARTBEATS
    vhost = settings.DEFAULT_STOMP_VHOST
    connection_class = settings.DEFAULT_CONNECTION_CLASS
    connection = connection_class(
        host_and_ports=host_and_ports,
        heartbeats=heartbeats,
        vhost=vhost,
    )
    return connection


def factory_consumer():
    username = USERNAME
    passcode = PASSCODE
    connection = factory_connection()
    return Consumer(connection, username, passcode)


def factory_producer():
    username = USERNAME
    passcode = PASSCODE
    connection = factory_connection()
    return Producer(connection, username, passcode)
