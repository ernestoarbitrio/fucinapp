"""Step 3: Remove old per-year fields from Configurazione."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("configurazione", "0011_copy_data_to_annuale"),
    ]

    operations = [
        migrations.RemoveField(model_name="configurazione", name="consiglio_direttivo"),
        migrations.RemoveField(
            model_name="configurazione", name="delta_giorni_iscrizione"
        ),
        migrations.RemoveField(
            model_name="configurazione", name="delta_giorni_registro"
        ),
        migrations.RemoveField(model_name="configurazione", name="firma_presidente"),
        migrations.RemoveField(
            model_name="configurazione", name="scadenza_quota_giorno"
        ),
        migrations.RemoveField(model_name="configurazione", name="scadenza_quota_mese"),
    ]
