from django.apps import AppConfig


class AnagraficaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "anagrafica"

    def ready(self):
        import anagrafica.models  # ensures signals are registered  # noqa: F401
