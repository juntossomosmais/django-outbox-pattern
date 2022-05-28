class Payload:
    def __init__(self, connection, body, headers):
        self.body = body
        self.connection = connection
        self.headers = headers

    def ack(self):
        self.connection.ack(self._message_id)

    def nack(self):
        self.connection.nack(self._message_id, requeue=False)

    @property
    def _message_id(self):
        return self.headers.get("message-id")
