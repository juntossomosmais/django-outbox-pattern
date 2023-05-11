# Django outbox pattern

[![Build Status](https://dev.azure.com/juntos-somos-mais-loyalty/python/_apis/build/status/juntossomosmais.django-outbox-pattern?branchName=main)](https://dev.azure.com/juntos-somos-mais-loyalty/python/_build/latest?definitionId=307&branchName=main)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=juntossomosmais_django-outbox-pattern&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=juntossomosmais_django-outbox-pattern)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=juntossomosmais_django-outbox-pattern&metric=coverage)](https://sonarcloud.io/summary/new_code?id=juntossomosmais_django-outbox-pattern)
[![Code style: black](https://img.shields.io/badge/code%20style-black-black)](https://github.com/ambv/black)
[![Downloads](https://pepy.tech/badge/django-outbox-pattern)](https://pepy.tech/project/django-outbox-pattern)
[![Downloads](https://pepy.tech/badge/django-outbox-pattern/month)](https://pepy.tech/project/django-outbox-pattern/month)
[![Downloads](https://pepy.tech/badge/django-outbox-pattern/week)](https://pepy.tech/project/django-outbox-pattern/week)
[![PyPI version](https://badge.fury.io/py/django-outbox-pattern.svg)](https://badge.fury.io/py/django-outbox-pattern)
[![GitHub](https://img.shields.io/github/license/mashape/apistatus.svg)](https://github.com/juntossomosmais/django-outbox-pattern/blob/master/LICENSE)

A django application to make it easier to use
the [transactional outbox pattern](https://microservices.io/patterns/data/transactional-outbox.html)

## Installation

Install django-outbox-pattern with pip

```bash
pip install django-outbox-pattern
```

Add to settings

```python
# settings.py

INSTALLED_APPS = [
    "django_outbox_pattern",
]

DJANGO_OUTBOX_PATTERN = {
    "DEFAULT_STOMP_HOST_AND_PORTS": [("127.0.0.1", 61613)],
    "DEFAULT_STOMP_USERNAME": "guest",
    "DEFAULT_STOMP_PASSCODE": "guest",
}

```

Rum migrations

```shell
python manage.py migrate
```

## Usage/Examples

The `publish` decorator adds the [outbox table](https://github.com/juntossomosmais/django-outbox-pattern/blob/main/django_outbox_pattern/models.py#L14) to the model. `publish` accepts list of Config. The Config accepts four params the `destination` which is required,
`fields` which the default are all the fields of the model, `serializer` which by default adds the `id` in the message
to be sent and `version` which by default is empty.

> Note: `fields` and `serializer` are mutually exclusive, serializer overwrites the fields.

### The Config typing

```python
from typing import List
from typing import NamedTuple
from typing import Optional

class Config(NamedTuple):
    destination: str
    fields: Optional[List[str]] = None
    serializer: Optional[str] = None
    version: Optional[str] = None
```

#### Only destination in config

```python
from django.db import models
from django_outbox_pattern.decorators import Config
from django_outbox_pattern.decorators import publish


@publish([Config(destination='/topic/my_route_key')])
class MyModel(models.Model):
    field_one = models.CharField(max_length=100)
    field_two = models.CharField(max_length=100)
```

This generates the following data to be sent.

```text
Published(destination='/topic/my_route_key', body='{"id": 1, "field_one": "Field One", "field_two": "Field Two"}')
```

#### Change destination version in config

```python
from django.db import models
from django_outbox_pattern.decorators import Config
from django_outbox_pattern.decorators import publish


@publish([Config(destination='/topic/my_route_key', version="v1")])
class MyModel(models.Model):
    field_one = models.CharField(max_length=100)
    field_two = models.CharField(max_length=100)
```

This generates the following data to be sent.

```text
Published(destination='/topic/my_route_key.v1', body='{"id": 1, "field_one": "One", "field_two": "Two"}', version="v1")
```

#### With destinations and fields

```python
from django.db import models
from django_outbox_pattern.decorators import Config
from django_outbox_pattern.decorators import publish


@publish([Config(destination='/topic/my_route_key', fields=["field_one"])])
class MyModel(models.Model):
    field_one = models.CharField(max_length=100)
    field_two = models.CharField(max_length=100)
```

This generates the following data to be sent.

```text
Published(destination='/topic/my_route_key', body='{"id": 1, "field_one": "Field One"}')
```

#### With destinations and serializer

```python
from django.db import models
from django_outbox_pattern.decorators import Config
from django_outbox_pattern.decorators import publish


@publish([Config(destination='/topic/my_route_key', serializer='my_serializer')])
class MyModel(models.Model):
    field_one = models.CharField(max_length=100)
    field_two = models.CharField(max_length=100)

    def my_serializer(self):
        return {
            "id": self.id,
            "one": self.field_one,
            "two": self.field_two
        }
```

This generates the following data to be sent.

```text
Published(destination='/topic/my_route_key', body='{"id": 1, "one": "Field One", "two": "Field Two"}')
```

#### With multi destinations and serializers

```python
from django.db import models
from django_outbox_pattern.decorators import Config
from django_outbox_pattern.decorators import publish


@publish([
    Config(destination='/topic/my_route_key_1', serializer="my_serializer_1"),
    Config(destination='/topic/my_route_key_2', serializer="my_serializer_2"),
])
class MyModel(models.Model):
    field_one = models.CharField(max_length=100)
    field_two = models.CharField(max_length=100)

    def my_serializer_1(self):
        return {
            "id": self.id,
            "one": self.field_one,
        }

    def my_serializer_2(self):
        return {
            "id": self.id,
            "two": self.field_two
        }
```

This generates the following data to be sent.

```text
Published(destination='/topic/my_route_key_1', body='{"id": 1, "one": "Field One"}')
Published(destination='/topic/my_route_key_2', body='{"id": 1, "two": "Field Two"}')
```

## Publish/Subscribe commands

##### Publish command

To send the messages added to the Published model it is necessary to start the producer with the following command.

```shell
python manage.py publish
```

##### Publish message via outbox

It is possible to use the outbox pattern with a custom logic before sending the message to the outbox table.
```python
from django.db import transaction
from django_outbox_pattern.models import Published

def custom_business_logic() -> None:

    # run your custom business logic

    with transaction.atomic():
        YourBusinessModel.objects.create()
        Published.objects.create(destination="your_destination", body={"some": "data"})

```
With this you can ensure that the messages can be published in the same database transaction of your business logic.

##### Publish message directly

It is possible to send messages directly without using the outbox table

```python
# send.py
from django_outbox_pattern.factories import factory_producer

def send_event(destination, body, headers):
    with factory_producer() as producer:
        producer.send_event(destination=destination, body=body, headers=headers)
```

##### Subscribe command

Consumers created through the library implement the idempotency pattern using the header attribute `message-id`. The library configures it as unique in the database. This ensures a given message is only processed once, no matter what.
To correctly implement this, you must open a transaction with the database to persist the data from your logic and execute the `save` method of the `payload` object. Once the code is performed correctly, the library guarantees the message is removed from the broker.

If you need to discard the message due to a business rule, use the `nack` method of the Payload object. This call removes the message from the broker. This method performs no persistence in the database and can be called outside your database transaction. If it fails for any reason, the message is resent to the consumer.

**Alert:**

**You need to use either `save` or `nack` to process of your message. The library cannot make the decision for the developer, and it is up to the developer to determine whether to use the `save` or `nack` method. However, in case of an exception during the operation, the `nack` method will be triggered automatically**

**The same service (code + database) cannot consume the same message even with different consumers.**

Create a function that receives an instance of `django_outbox_pattern.payloads.Payload`

```python
# callbacks.py
from django.db import transaction
from django_outbox_pattern.payloads import Payload

def callback(payload: Payload):

    if message_is_invalid(payload.body):
        payload.nack()
        return

    with transaction.atomic():
        persist_your_data()
        payload.save()

```

To start the consumer, after creating the callback, it is necessary to execute the following command.

```shell
python manage.py subscribe 'dotted.path.to.callback` 'destination' 'queue_name'
```
The command takes three parameters:

`callback` : the path to the callback function.

`destination` : the destination where messages will be consumed following one of the [stomp](https://www.rabbitmq.com/stomp.html) patterns

`queue_name`(optional): the name of the queue that will be consumed. If not provided, the routing_key of the destination will be used.

## Settings

**DEFAULT_CONNECTION_CLASS**

The stomp.py class responsible for connecting to the broker. Default: `stomp.StompConnection12`

**DEFAULT_CONSUMER_LISTENER_CLASS**

The consumer listener class. Default: `django_outbox_pattern.listeners.ConsumerListener`

**DEFAULT_GENERATE_HEADERS**

A function to add headers to the message. Default: `django_outbox_pattern.headers.generate_headers`

**DEFAULT_MAXIMUM_BACKOFF**:

Maximum wait time for connection attempts in seconds. Default: `3600` (1 hour)

**DEFAULT_MAXIMUM_RETRY_ATTEMPTS**

Maximum number of message resend attempts. Default: `50`

**DEFAULT_PAUSE_FOR_RETRY**

Pausing for attempts to resend messages in seconds. Defualt: `240` (4 minutes)

**DEFAULT_WAIT_RETRY**

Time between attempts to send messages after the pause. Default: `60` (1 minute)

**DEFAULT_PRODUCER_LISTENER_CLASS**:

The producer listener class. Default: `django_outbox_pattern.listeners.ProducerListener`

**DEFAULT_STOMP_HOST_AND_PORTS**

List of host and port tuples to try to connect to the broker. Default `[("127.0.0.1", 61613)]`

**DEFAULT_STOMP_QUEUE_HEADERS**

Headers for queues. Default: `{"durable": "true", "auto-delete": "false", "prefetch-count": "1"}`

**DEFAULT_STOMP_HEARTBEATS**

Time tuples for input and output heartbeats. Default:  `(10000, 10000)`

**DEFAULT_STOMP_VHOST**

Virtual host. Default: "/"

**DEFAULT_STOMP_USERNAME**

Username for connection. Default: `"guest"`

**DEFAULT_STOMP_PASSCODE**

Password for connection. Default: `"guest"`

**DEFAULT_STOMP_USE_SSL**

For ssl connections. Default: False

**DEFAULT_STOMP_KEY_FILE**

The path to a X509 key file. Default: None

**DEFAULT_STOMP_CERT_FILE**

The path to a X509 certificate. Default: None


**DEFAULT_STOMP_CA_CERTS**

The path to the a file containing CA certificates to validate the server against.
If this is not set, server side certificate validation is not done. Default: None

**DEFAULT_STOMP_CERT_VALIDATOR**

Function which performs extra validation on the client certificate, for example
checking the returned certificate has a commonName attribute equal to the
hostname (to avoid man in the middle attacks).
The signature is: (OK, err_msg) = validation_function(cert, hostname)
where OK is a boolean, and cert is a certificate structure
as returned by ssl.SSLSocket.getpeercert(). Default: None

**DEFAULT_STOMP_SSL_VERSION**

SSL protocol to use for the connection. This should be one of the PROTOCOL_x
constants provided by the ssl module. The default is ssl.PROTOCOL_TLSv1.

**DEFAULT_STOMP_SSL_PASSWORD**

SSL password

**DAYS_TO_KEEP_DATA**

The total number of days that the system will keep a message in the database history. Default: 30

**REMOVE_DATA_CACHE_TTL**

This variable defines the time-to-live (TTL) value in seconds for the cache used by the `_remove_old_messages` method in the `django_outbox_pattern` application. The cache is used to prevent the method from deleting old data every time it is run, and the TTL value determines how long the cache entry should remain valid before being automatically deleted. It can be customized by setting the REMOVE_DATA_CACHE_TTL variable. Default: 86400 seconds (1 day)

**OUTBOX_PATTERN_PUBLISHER_CACHE_KEY**

The `OUTBOX_PATTERN_PUBLISHER_CACHE_KEY` variable controls the key name of the cache used to store the outbox pattern publisher. Default: `remove_old_messages_django_outbox_pattern_publisher`.

**OUTBOX_PATTERN_CONSUMER_CACHE_KEY**

The `OUTBOX_PATTERN_CONSUMER_CACHE_KEY` variable controls the key name of the cache used to store the outbox pattern publisher. Default: `remove_old_messages_django_outbox_pattern_consumer`.
