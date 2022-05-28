import os
import sys
from time import sleep

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    count = 0
    running = True

    def handle(self, *args, **options):
        """Should be implemented"""

    def _exit(self):
        self.stdout.write("\nI'm not waiting for messages anymore 🥲!")
        sys.exit(0)

    def _waiting(self, msg):
        self.stdout.write(f"{msg}{'.' * self.count}\nQuit with CONTROL-C")
        self.count += 1 if self.count < 3 else -3
        sleep(1)
        os.system("clear")
