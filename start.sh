#!/bin/bash
set -e
mkdir -p /var/data
python manage.py migrate
exec gunicorn fucinapp.wsgi:application --bind 0.0.0.0:$PORT
