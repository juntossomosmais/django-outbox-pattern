
# Django outbox pattern

Making Transactional Outbox easy

[![Build Status](https://dev.azure.com/juntos-somos-mais-loyalty/python/_apis/build/status/juntossomosmais.django-outbox-pattern?branchName=azure-pipelines)](https://dev.azure.com/juntos-somos-mais-loyalty/python/_build/latest?definitionId=307&branchName=azure-pipelines)

## Installation

Install django-outbox-pattern with pip

```bash
  pip install django-outbox-pattern
```

Add to settings

```python
# settings.py

INSTALLED_APPS = [
    ...
    "django_outbox_pattern",
    ...
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

__Only destination__

```python
from django_outbox_pattern.decorators import publish


@publish(destination='/topic/my_route_key')
class MyModel(models.Model):
    field_one = models.CharField(max_length=100)
    field_two = models.CharField(max_length=100)
```

This generates the following data to be sent.

```python
producer.send(destination='/topic/my_route_key.v1', body='{"id": 1, "field_one": "Field One", "field_two": "Field Two"}')
```

__With fields__

```python
from django_outbox_pattern.decorators import publish


@publish(destination='/topic/my_route_key', fields=["field_one"])
class MyModel(models.Model):
    field_one = models.CharField(max_length=100)
    field_two = models.CharField(max_length=100)
```

This generates the following data to be sent.

```python
producer.send(destination='/topic/my_route_key.v1', body='{"id": 1, "field_one": "Field One"}')
```

__With serializer__

```python
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

```python
producer.send(destination='/topic/my_route_key.v1', body='{"id": 1, "one": "Field One", "two": "Field Two"}')
```
## Publish/Subscribe commands

To send the messages added to the outbox table it is necessary to start the producer.

```python
python manage.py publish
```

Django outbox pattern also provides a consumer that can be used to receive outgoing messages.


```python
# callbacks.py

# Create a function that receives an instance of django_outbox_pattern.payloads.Payload

def callback(payload):
    payload.ack()
```

```python
python manage.py subscribe 'dotted.path.to.callbacks` '/topic/my_route_key.v1'
```
