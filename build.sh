python manage.py migrate && python manage.py shell -c "
from django.contrib.auth import get_user_model
U = get_user_model()
import os
if not U.objects.filter(username=os.environ['DJANGO_SUPERUSER_USERNAME']).exists():
    U.objects.create_superuser(
        os.environ['DJANGO_SUPERUSER_USERNAME'],
        os.environ['DJANGO_SUPERUSER_EMAIL'],
        os.environ['DJANGO_SUPERUSER_PASSWORD']
    )
" && gunicorn registro_soci.wsgi:application --bind 0.0.0.0:$PORT
