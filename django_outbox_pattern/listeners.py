import logging

from stomp.listener import ConnectionListener

_logger = logging.getLogger("django_outbox_pattern")


class BaseListener(ConnectionListener):
    def __init__(self, instance):
        self.instance = instance

    def on_connecting(self, host_and_port):
        _logger.debug("%s attempting connection to host %s port %s", self.instance.__class__.__name__, *host_and_port)

    def on_connected(self, frame):
        _logger.debug("%s established connection", self.instance.__class__.__name__)

    def on_error(self, frame):
        _logger.debug("%s received an error %s [%s]", self.instance.__class__.__name__, frame.body, frame.headers)


class ConsumerListener(BaseListener):
    def on_disconnected(self):
        _logger.debug("Consumer disconnected")
        self.instance.start(self.instance.callback, self.instance.destination, self.instance.queue_name)

    def on_message(self, frame):
        if self.instance.subscribe_id in frame.headers["subscription"]:
            _logger.info("Message id received: %s", frame.headers["message-id"])
            _logger.debug("Message body received: %s", frame.body)
            _logger.debug("Message headers received: %s", frame.headers)
            self.instance.handle_incoming_message(frame.body, frame.headers)


class ProducerListener(BaseListener):
    def on_disconnected(self):
        _logger.debug("Producer disconnected")
        self.instance.start()

    def on_send(self, frame):
        if frame.cmd == "SEND":
            _logger.debug("Message body sent: %s", frame.body)
            _logger.debug("Message headers sent: %s", frame.headers)
