from django.utils.module_loading import import_string

from django_outbox_pattern import settings
from django_outbox_pattern.consumers import Consumer
from django_outbox_pattern.producers import Producer

USERNAME = settings.DEFAULT_STOMP_USERNAME
PASSCODE = settings.DEFAULT_STOMP_PASSCODE


def factory_connection():
    host_and_ports = settings.DEFAULT_STOMP_HOST_AND_PORTS
    heartbeats = settings.DEFAULT_STOMP_HEARTBEATS
    vhost = settings.DEFAULT_STOMP_VHOST
    connection_class = import_string(settings.DEFAULT_CONNECTION_CLASS)
    connection = connection_class(
        host_and_ports=host_and_ports,
        heartbeats=heartbeats,
        vhost=vhost,
    )
    use_ssl = settings.DEFAULT_STOMP_USE_SSL
    if use_ssl:
        key_file = settings.DEFAULT_STOMP_KEY_FILE
        cert_file = settings.DEFAULT_STOMP_CERT_FILE
        ca_certs = settings.DEFAULT_STOMP_CA_CERTS
        cert_validator = settings.DEFAULT_STOMP_CERT_VALIDATOR
        ssl_version = settings.DEFAULT_STOMP_SSL_VERSION
        password = settings.DEFAULT_STOMP_SSL_PASSWORD
        connection.set_ssl(
            for_hosts=host_and_ports,
            key_file=key_file,
            cert_file=cert_file,
            ca_certs=ca_certs,
            cert_validator=cert_validator,
            ssl_version=ssl_version,
            password=password,
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
