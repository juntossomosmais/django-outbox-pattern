def callback(payload):
    payload.ack()


def callback_exception(payload):
    raise KeyError()
