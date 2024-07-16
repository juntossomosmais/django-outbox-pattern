#!/usr/bin/env bash

git config --global --add safe.directory /app
pre-commit run --all-files
