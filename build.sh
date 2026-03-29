#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
mkdir -p /var/data
python manage.py collectstatic --no-input
python manage.py migrate

echo "from django.contrib.auth import get_user_model; U = get_user_model(); U.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists() or U.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD')" | python manage.py shell
