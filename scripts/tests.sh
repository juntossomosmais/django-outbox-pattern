#!/usr/bin/env bash
set -e


coverage erase
coverage run --source=. -m django test
coverage report
coverage html
coverage xml -o coverage.xml
