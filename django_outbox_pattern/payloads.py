from django_outbox_pattern.choices import StatusChoice


class Payload:
    def __init__(self, connection, body, headers, message=None):
        self.nacked = None
        self.acked = None
        self.saved = False
        self.body = body
        self.connection = connection
        self.headers = headers
        self.message = message

    def save(self):
        self.message.status = StatusChoice.SUCCEEDED
        self.message.save()
        self.saved = True

    def ack(self):
        if not self.acked and not self.nacked:
            self.connection.ack(self._message_id)
            self.acked = True

    def nack(self):
        if not self.acked and not self.nacked:
            self.connection.nack(self._message_id, requeue=False)
            self.nacked = True

    @property
    def _message_id(self):
        return self.headers.get("message-id")
