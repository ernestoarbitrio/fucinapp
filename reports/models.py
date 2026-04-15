from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.functions import ExtractYear

from anagrafica.models import Socio


class Verbale(models.Model):
    data = models.DateField(verbose_name="Data del verbale")
    numero_progressivo = models.PositiveIntegerField(
        verbose_name="Numero progressivo", editable=False
    )
    soci = models.ManyToManyField(
        Socio,
        verbose_name="Soci ammessi",
        related_name="verbali",
        blank=True,
    )
    consiglio_direttivo = models.TextField(
        verbose_name="Consiglio direttivo",
        help_text="Nomi e cognomi dei membri del consiglio direttivo.",
        blank=True,
    )

    class Meta:
        verbose_name = "Verbale"
        verbose_name_plural = "Verbali"
        ordering = ["-data", "-numero_progressivo"]
        constraints = [
            UniqueConstraint(
                ExtractYear("data"),
                "numero_progressivo",
                name="unique_progressivo_per_year",
            ),
        ]

    def __str__(self):
        return f"Verbale n.{self.numero_progressivo}/{self.data.year} del {self.data.strftime('%d/%m/%Y')}"

    def _soci_eligibili(self):
        from anagrafica.models import Quota

        anno = self.data.year
        gia_assegnati = Socio.objects.filter(verbali__data__year=anno)
        if self.pk:
            gia_assegnati = gia_assegnati.exclude(verbali=self)
        soci_ids = (
            Quota.objects.filter(
                anno=anno,
                stato="pagata",
                data_inizio__lte=self.data,
            )
            .exclude(socio__in=gia_assegnati)
            .values_list("socio", flat=True)
            .distinct()
        )
        return Socio.objects.filter(pk__in=soci_ids)

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.data and not self._soci_eligibili().exists():
            raise ValidationError(
                "Nessun socio con quota pagata disponibile per questa data."
            )

    def save(self, *args, **kwargs):
        if not self.numero_progressivo:
            last = (
                Verbale.objects.filter(data__year=self.data.year)
                .order_by("-numero_progressivo")
                .values_list("numero_progressivo", flat=True)
                .first()
            )
            self.numero_progressivo = (last or 0) + 1
        if not self.consiglio_direttivo:
            self.popola_consiglio_direttivo()
        super().save(*args, **kwargs)

    def popola_consiglio_direttivo(self):
        """Populate from the ConfigurazioneAnnuale for the verbale's year."""
        from configurazione.models import ConfigurazioneAnnuale

        config_anno = ConfigurazioneAnnuale.get(self.data.year)
        membri = config_anno.consiglio_direttivo.all()
        self.consiglio_direttivo = ", ".join(f"{s.nome} {s.cognome}" for s in membri)

    def assegna_soci(self):
        """Auto-assign soci with paid quota where data_inizio <= verbale date,
        not already in another verbale for the same year."""
        self.soci.set(self._soci_eligibili())


class Newsletter(models.Model):
    DESTINATARI_CHOICES = [
        ("tutti", "Tutti i soci (con consenso)"),
        ("in_regola", "Solo soci in regola"),
        ("scaduti", "Solo soci con quota scaduta"),
    ]
    STATO_CHOICES = [
        ("bozza", "Bozza"),
        ("inviata", "Inviata"),
    ]

    oggetto = models.CharField(verbose_name="Oggetto", max_length=200)
    corpo = models.TextField(verbose_name="Corpo email (HTML)")
    destinatari = models.CharField(
        verbose_name="Destinatari",
        max_length=20,
        choices=DESTINATARI_CHOICES,
        default="tutti",
    )
    stato = models.CharField(
        verbose_name="Stato",
        max_length=10,
        choices=STATO_CHOICES,
        default="bozza",
        editable=False,
    )
    data_invio = models.DateTimeField(
        verbose_name="Data invio", null=True, blank=True, editable=False
    )
    num_destinatari = models.PositiveIntegerField(
        verbose_name="N° destinatari", default=0, editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Newsletter"
        verbose_name_plural = "Newsletter"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.oggetto} ({self.get_stato_display()})"

    def get_destinatari_queryset(self):
        """Return soci queryset filtered by destinatari choice and consenso_marketing."""
        from django.utils import timezone

        qs = Socio.objects.filter(consenso_marketing=True, approvato=True)
        if self.destinatari == "in_regola":
            today = timezone.now().date()
            qs = qs.filter(
                quote__stato="pagata",
                quote__data_inizio__lte=today,
                quote__data_scadenza__gte=today,
            ).distinct()
        elif self.destinatari == "scaduti":
            today = timezone.now().date()
            qs = (
                qs.exclude(
                    quote__stato="pagata",
                    quote__data_inizio__lte=today,
                    quote__data_scadenza__gte=today,
                )
                .filter(quote__isnull=False)
                .distinct()
            )
        return qs

    def render_html(self):
        """Wrap corpo in the email template with logo header and association footer."""
        from django.conf import settings

        from configurazione.models import Configurazione

        config = Configurazione.get()
        logo_tag = ""
        if config.logo:
            logo_url = f"{settings.SITE_URL}{settings.MEDIA_URL}{config.logo.name}"
            logo_tag = f'<img src="{logo_url}" alt="Logo" style="max-height:60px;">'

        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:#f5f5f5; padding:20px; margin:0; }}
    .wrapper {{ max-width:600px; margin:0 auto; background:#fff; border-radius:12px; box-shadow:0 2px 12px rgba(0,0,0,0.08); }}
    .header {{ text-align:center; padding:24px 20px 12px; border-bottom:1px solid #eee; }}
    .header img {{ max-height:60px; }}
    .header h2 {{ color:#2c5364; margin:8px 0 0; font-size:1.1rem; }}
    .content {{ padding:24px 32px; color:#333; font-size:0.95rem; line-height:1.6; }}
    .footer {{ text-align:center; padding:16px 20px; border-top:1px solid #eee; font-size:0.78rem; color:#aaa; }}
</style></head>
<body><div class="wrapper">
    <div class="header">
        {logo_tag}
        <h2>{config.nome_associazione}</h2>
    </div>
    <div class="content">{self.corpo}</div>
    <div class="footer">
        {config.nome_associazione} &middot; {config.via}, {config.cap} {config.comune}<br>
        {config.email}
    </div>
</div></body></html>"""

    def invia(self):
        """Send the newsletter via Resend to all matching recipients."""
        import logging

        import resend
        from django.conf import settings
        from django.utils import timezone

        from configurazione.models import Configurazione

        logger = logging.getLogger(__name__)
        config = Configurazione.get()
        resend.api_key = settings.RESEND_API_KEY

        destinatari = self.get_destinatari_queryset()
        emails = list(destinatari.values_list("email", flat=True))

        if not emails:
            return 0

        html = self.render_html()
        sent = 0
        # Send in batches of 50
        for i in range(0, len(emails), 50):
            batch = emails[i : i + 50]
            try:
                resend.Emails.send(
                    {
                        "from": settings.DEFAULT_FROM_EMAIL,
                        "to": [config.email or settings.DEFAULT_FROM_EMAIL],
                        "bcc": batch,
                        "subject": self.oggetto,
                        "html": html,
                    }
                )
                sent += len(batch)
            except Exception:
                logger.exception(
                    "Errore invio newsletter batch %d-%d", i, i + len(batch)
                )

        self.stato = "inviata"
        self.data_invio = timezone.now()
        self.num_destinatari = sent
        self.save(update_fields=["stato", "data_invio", "num_destinatari"])
        return sent
