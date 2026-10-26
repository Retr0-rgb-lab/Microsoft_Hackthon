#!/bin/sh
# Azure App Service entry point. The dashboard is a stdlib HTTP server; wsgi.py
# exposes the same handler through WSGI so gunicorn can serve it.
exec gunicorn \
  --bind=0.0.0.0:"${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout 600 \
  --graceful-timeout 30 \
  --access-logfile - \
  --error-logfile - \
  wsgi:application
