from django.db import models


class StatusChoice(models.IntegerChoices):
    FAILED = -1
    SCHEDULE = 1
    SUCCEEDED = 2
