FROM python:3.7-slim

WORKDIR /app

RUN pip install poetry

COPY . .

RUN poetry config virtualenvs.create false && \
    poetry install --no-dev --no-root

RUN poetry install --no-root --with dev
