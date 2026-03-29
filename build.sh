#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
mkdir -p /var/data
chmod +x start.sh
python manage.py collectstatic --no-input
