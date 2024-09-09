#!/usr/bin/env bash
set -e
git config --global --add safe.directory /app
pre-commit run --all-files
