"""Step 1: Create ConfigurazioneAnnuale model (keep old fields on Configurazione)."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("anagrafica", "0018_alter_socio_tipo"),
        ("configurazione", "0009_alter_configurazione_scadenza_quota_giorno"),
    ]

    operations = [
        migrations.CreateModel(
            name="ConfigurazioneAnnuale",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("anno", models.PositiveIntegerField(unique=True, verbose_name="Anno")),
                (
                    "firma_presidente",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="configurazione/firme/",
                        verbose_name="Firma del presidente",
                    ),
                ),
                (
                    "delta_giorni_iscrizione",
                    models.PositiveIntegerField(
                        default=365,
                        help_text="Numero di giorni di validità dell'iscrizione.",
                        verbose_name="Delta giorni iscrizione",
                    ),
                ),
                (
                    "delta_giorni_registro",
                    models.PositiveIntegerField(
                        default=30,
                        help_text="Numero di giorni per il registro.",
                        verbose_name="Delta giorni registro",
                    ),
                ),
                (
                    "scadenza_quota_giorno",
                    models.PositiveSmallIntegerField(
                        default=31,
                        help_text="Giorno di scadenza della quota associativa.",
                        verbose_name="Giorno scadenza quota",
                    ),
                ),
                (
                    "scadenza_quota_mese",
                    models.PositiveSmallIntegerField(
                        default=3,
                        help_text="Mese di scadenza della quota associativa.",
                        verbose_name="Mese scadenza quota",
                    ),
                ),
                (
                    "configurazione",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="annuali",
                        to="configurazione.configurazione",
                    ),
                ),
                (
                    "consiglio_direttivo",
                    models.ManyToManyField(
                        blank=True,
                        related_name="consiglieri",
                        to="anagrafica.socio",
                        verbose_name="Membri del consiglio direttivo",
                    ),
                ),
            ],
            options={
                "verbose_name": "Configurazione annuale",
                "verbose_name_plural": "Configurazioni annuali",
                "ordering": ["-anno"],
            },
        ),
    ]
