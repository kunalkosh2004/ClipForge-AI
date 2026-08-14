#!/bin/sh
# Starts the Dramatiq worker in the background and the API in the
# foreground within a single container. This is the pattern for
# single-service deploys (e.g. Render free tier): the API's HTTP
# health check keeps the instance awake, and the worker consumes the
# same Redis queues alongside it.
set -e

dramatiq clipforge.worker.tasks clipforge.intelligence.tasks \
  --processes 1 --threads 2 &

exec uvicorn clipforge.api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
