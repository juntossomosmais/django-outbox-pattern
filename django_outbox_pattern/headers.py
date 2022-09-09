from django.utils import timezone


def generate_headers(message):
    return {
        "dop-msg-id": str(message.id),
        "dop-msg-destination": message.destination,
        "dop-msg-type": message.__class__.__name__,
        "dop-msg-sent-time": timezone.now(),
    }
