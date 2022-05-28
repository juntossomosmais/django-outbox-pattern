from django.utils import timezone


def generate_headers(message):
    return {
        "msg-id": str(message.id),
        "msg-destination": message.destination,
        "msg-type": message.__class__.__name__,
        "msg-sent-time": timezone.now(),
    }
