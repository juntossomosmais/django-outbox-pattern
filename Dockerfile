FROM python:3.9-slim

WORKDIR /app

# Git is required for pre-commit
RUN apt update
RUN apt install -y git

RUN pip install poetry

COPY . .

RUN poetry config virtualenvs.create false && \
    poetry install --no-dev --no-root

RUN poetry install --no-root --with dev
