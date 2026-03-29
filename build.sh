#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
mkdir -p /var/data
python manage.py collectstatic --no-input
