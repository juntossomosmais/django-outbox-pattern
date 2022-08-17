FROM python:3.7

WORKDIR /app

COPY . .

RUN pip install tox=="4.0.0b2"
