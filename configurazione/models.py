from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from anagrafica.models import Socio


class Configurazione(models.Model):
    nome_associazione = models.CharField(
        verbose_name="Nome associazione",
        max_length=200,
    )
    via = models.CharField(verbose_name="Via/Piazza", max_length=200, blank=True)
    comune = models.CharField(verbose_name="Comune", max_length=100, blank=True)
    provincia = models.CharField(verbose_name="Provincia", max_length=2, blank=True)
    cap = models.CharField(verbose_name="CAP", max_length=5, blank=True)
    cf = models.CharField(verbose_name="Codice Fiscale", max_length=20, blank=True)
    email = models.EmailField(verbose_name="Email", blank=True)
    pec = models.EmailField(verbose_name="PEC", blank=True)
    logo = models.ImageField(
        verbose_name="Logo", upload_to="configurazione/", blank=True, null=True
    )
    logo_secondario = models.ImageField(
        verbose_name="Logo secondario",
        upload_to="configurazione/",
        blank=True,
        null=True,
    )
    firma_presidente = models.ImageField(
        verbose_name="Firma del presidente",
        upload_to="configurazione/firme/",
        blank=True,
        null=True,
    )
    consiglio_direttivo = models.ManyToManyField(
        Socio,
        verbose_name="Membri del consiglio direttivo",
        blank=True,
        related_name="consiglieri",
    )
    delta_giorni_iscrizione = models.PositiveIntegerField(
        verbose_name="Delta giorni iscrizione",
        default=365,
        help_text="Numero di giorni di validità dell'iscrizione.",
    )
    delta_giorni_registro = models.PositiveIntegerField(
        verbose_name="Delta giorni registro",
        default=30,
        help_text="Numero di giorni per il registro.",
    )
    scadenza_quota_giorno = models.PositiveSmallIntegerField(
        verbose_name="Giorno scadenza quota",
        default=12,
        help_text="Giorno di scadenza della quota associativa.",
    )
    scadenza_quota_mese = models.PositiveSmallIntegerField(
        verbose_name="Mese scadenza quota",
        default=3,
        help_text="Mese di scadenza della quota associativa.",
    )

    class Meta:
        verbose_name = "Configurazione"
        verbose_name_plural = "Configurazione"

    def __str__(self):
        return self.nome_associazione

    @classmethod
    def get(cls):
        """Always return the single configuration instance."""
        obj, _ = cls.objects.get_or_create(
            pk=1, defaults={"nome_associazione": settings.DEFAILT_NAME_CONF}
        )
        return obj

    def clean(self):
        if not self.pk and Configurazione.objects.exists():
            raise ValidationError("Può esistere solo una configurazione.")

    def save(self, *args, **kwargs):
        self.pk = 1  # always force pk=1
        super().save(*args, **kwargs)
