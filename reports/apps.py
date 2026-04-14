from django.apps import AppConfig


class ReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reports"

    def ready(self):
        import os

        # Only start scheduler in the main process (not in manage.py commands)
        if os.environ.get("RUN_MAIN") or os.environ.get("GUNICORN_RUNNING"):
            from reports.scheduler import start

            start()
