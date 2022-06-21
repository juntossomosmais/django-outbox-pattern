
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

A django application to make it easier to use the [transactional outbox pattern](https://microservices.io/patterns/data/transactional-outbox.html)

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

## Usage/Examples

The `publish` decorator adds the outbox table to the model. `
publish` accepts three parameters, the `destination` which is required,
fields which the default are all the `fields` of the model and `serializer` which by default adds the id in the message to be sent.
`fields` and `serializer` are mutually exclusive.

_**Only destination**_

```python
from django.db import models
from django_outbox_pattern.decorators import publish


@publish(destination='/topic/my_route_key')
class MyModel(models.Model):
    field_one = models.CharField(max_length=100)
    field_two = models.CharField(max_length=100)
```

This generates the following data to be sent.

```text
producer.send(destination='/topic/my_route_key.v1', body='{"id": 1, "field_one": "Field One", "field_two": "Field Two"}')
```

_**With fields**_

```python
from django.db import models
from django_outbox_pattern.decorators import publish


@publish(destination='/topic/my_route_key', fields=["field_one"])
class MyModel(models.Model):
    field_one = models.CharField(max_length=100)
    field_two = models.CharField(max_length=100)
```

This generates the following data to be sent.

```text
producer.send(destination='/topic/my_route_key.v1', body='{"id": 1, "field_one": "Field One"}')
```

_**With serializer**_

```python
from django.db import models
from django_outbox_pattern.decorators import publish


@publish(destination='/topic/my_route_key', serializer='my_serializer')
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
producer.send(destination='/topic/my_route_key.v1', body='{"id": 1, "one": "Field One", "two": "Field Two"}')
```
## Publish/Subscribe commands

##### Publish command

To send the messages added to the outbox table it is necessary to start the producer.

```shell
python manage.py publish
```

##### Subscribe command

Django outbox pattern also provides a consumer that can be used to receive outgoing messages.

Create a function that receives an instance of `django_outbox_pattern.payloads.Payload`

```python
# callbacks.py

def callback(payload):
    try:
        # Do anything
        payload.ack()
    except Exception:
        # Nack is automatically called in case of errors, but you might want to handle the error in another way
        payload.nack()
```

```shell
python manage.py subscribe 'dotted.path.to.callback` 'destination'
```

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
