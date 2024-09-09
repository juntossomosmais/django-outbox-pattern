class ExceededSendAttemptsException(Exception):
    """Raised when the limit of attempts to send messages to the broker is exceeded"""

    def __init__(self, attempts):
        self.attempts = attempts
