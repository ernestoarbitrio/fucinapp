"""Step 2: Copy data from Configurazione to ConfigurazioneAnnuale for current year."""

from django.db import migrations
from django.utils import timezone


def copy_to_annuale(apps, schema_editor):
    Configurazione = apps.get_model("configurazione", "Configurazione")
    ConfigurazioneAnnuale = apps.get_model("configurazione", "ConfigurazioneAnnuale")

    try:
        config = Configurazione.objects.get(pk=1)
    except Configurazione.DoesNotExist:
        return

    anno = timezone.now().year
    annuale, _ = ConfigurazioneAnnuale.objects.get_or_create(
        anno=anno,
        defaults={
            "configurazione": config,
            "firma_presidente": config.firma_presidente,
            "delta_giorni_iscrizione": config.delta_giorni_iscrizione,
            "delta_giorni_registro": config.delta_giorni_registro,
            "scadenza_quota_giorno": config.scadenza_quota_giorno,
            "scadenza_quota_mese": config.scadenza_quota_mese,
        },
    )
    # Copy M2M
    annuale.consiglio_direttivo.set(config.consiglio_direttivo.all())


class Migration(migrations.Migration):
    dependencies = [
        ("configurazione", "0010_create_configurazione_annuale"),
    ]

    operations = [
        migrations.RunPython(copy_to_annuale, migrations.RunPython.noop),
    ]
