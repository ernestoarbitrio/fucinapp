import io
import logging
import re
import uuid
from datetime import date

import qrcode
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

TIPO_CHOICES = [
    ("SS", "Socio Sostenitore"),
    ("SV", "Socio Volontario"),
    ("VP", "Vice Presidente"),
    ("PS", "Presidente"),
    ("CO", "Consigliere"),
    ("SG", "Segretario"),
    ("TE", "Tesoriere"),
]

TIPO_DOCUMENTO_CHOICES = [
    ("passaporto", "Passaporto"),
    ("carta_identita", "Carta di identità"),
    ("patente", "Patente di guida"),
]


def get_data_scadenza_default(anno):
    from configurazione.models import ConfigurazioneAnnuale

    config = ConfigurazioneAnnuale.get(anno)
    try:
        return date(anno + 1, config.scadenza_quota_mese, config.scadenza_quota_giorno)
    except ValueError:
        return date(anno + 1, 3, 31)


def valida_codice_fiscale(value):
    value = value.upper().strip()
    if not re.fullmatch(
        r"[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST]{1}[0-9LMNPQRSTUV]{2}[A-Z]{1}[0-9LMNPQRSTUV]{3}[A-Z]{1}",
        value,
    ):
        raise ValidationError("Il codice fiscale non è valido.")


class Socio(models.Model):
    nome = models.CharField(verbose_name="Nome", max_length=100)
    cognome = models.CharField(verbose_name="Cognome", max_length=100)
    data_nascita = models.DateField(verbose_name="Data di nascita")
    luogo_nascita = models.CharField(verbose_name="Luogo di nascita", max_length=100)
    codice_fiscale = models.CharField(
        verbose_name="Codice Fiscale",
        max_length=16,
        unique=True,
        blank=True,
        null=True,
        validators=[valida_codice_fiscale],
    )
    tipo_documento = models.CharField(
        verbose_name="Tipo documento",
        max_length=20,
        choices=TIPO_DOCUMENTO_CHOICES,
        blank=True,
        null=True,
    )
    numero_documento = models.CharField(
        verbose_name="Numero documento",
        max_length=30,
        blank=True,
        null=True,
    )
    via = models.CharField(verbose_name="Via/Piazza", max_length=200)
    comune = models.CharField(verbose_name="Comune", max_length=100)
    provincia = models.CharField(verbose_name="Provincia", max_length=2)
    cap = models.CharField(verbose_name="CAP", max_length=5)
    email = models.EmailField(verbose_name="Email", unique=True)
    telefono = models.CharField(
        verbose_name="Telefono", max_length=20, blank=True, null=True
    )
    tipo = models.CharField(
        verbose_name="Tipo socio", max_length=2, choices=TIPO_CHOICES, default="SS"
    )
    tutore_nome = models.CharField(
        verbose_name="Nome tutore", max_length=100, blank=True, null=True
    )
    tutore_cognome = models.CharField(
        verbose_name="Cognome tutore", max_length=100, blank=True, null=True
    )
    tutore_codice_fiscale = models.CharField(
        verbose_name="Codice Fiscale tutore", max_length=16, blank=True, null=True
    )
    tutore_email = models.EmailField(verbose_name="Email tutore", blank=True, null=True)
    tutore_telefono = models.CharField(
        verbose_name="Telefono tutore", max_length=20, blank=True, null=True
    )
    tutore_residenza = models.CharField(
        verbose_name="Residenza tutore",
        max_length=200,
        blank=True,
        null=True,
    )
    qr_code = models.ImageField(
        verbose_name="QR Code", upload_to="soci/qrcodes/", blank=True, null=True
    )
    approvato = models.BooleanField(
        verbose_name="Approvato",
        default=True,
        help_text="Se deselezionato, il socio è in attesa di approvazione.",
    )
    consenso_marketing = models.BooleanField(
        verbose_name="Consenso newsletter e comunicazioni", default=False
    )
    consenso_immagini = models.BooleanField(
        verbose_name="Consenso uso immagini", default=False
    )
    firma = models.TextField(verbose_name="Firma", blank=True, null=True)
    token = models.UUIDField(
        verbose_name="Token di verifica",
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    created_at = models.DateTimeField(
        verbose_name="Data di registrazione", auto_now_add=True
    )
    updated_at = models.DateTimeField(
        verbose_name="Ultimo aggiornamento", auto_now=True
    )

    class Meta:
        verbose_name = "Socio"
        verbose_name_plural = "Soci"
        ordering = ["cognome", "nome"]

    def __str__(self):
        return f"{self.cognome} {self.nome}"

    @property
    def nome_completo(self):
        return f"{self.nome} {self.cognome}"

    @property
    def quota_attiva(self):
        """Returns the current active subscription, or None if expired/missing."""
        today = timezone.now().date()
        # Use prefetched cache if available
        if "quote" in getattr(self, "_prefetched_objects_cache", {}):
            active = [
                q
                for q in self.quote.all()
                if q.stato == "pagata"
                and q.data_inizio
                and q.data_scadenza
                and q.data_inizio <= today <= q.data_scadenza
            ]
            return max(active, key=lambda q: q.data_scadenza) if active else None
        return (
            self.quote.filter(
                stato="pagata",
                data_inizio__lte=today,
                data_scadenza__gte=today,
            )
            .order_by("-data_scadenza")
            .first()
        )

    @property
    def is_in_regola(self):
        return self.quota_attiva is not None

    @property
    def ultima_quota(self):
        if "quote" in getattr(self, "_prefetched_objects_cache", {}):
            quote = list(self.quote.all())
            return (
                max(quote, key=lambda q: q.data_scadenza or date.min) if quote else None
            )
        return self.quote.order_by("-data_scadenza").first()

    def get_verifica_url(self, request=None):
        from django.conf import settings

        path = f"/anagrafica/verifica/{self.token}/"
        if request:
            return request.build_absolute_uri(path)
        base_url = getattr(settings, "SITE_URL", "http://localhost:8000")
        return f"{base_url}{path}"

    def genera_qr_code(self, request=None):
        url = self.get_verifica_url(request)

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        filename = f"qr_{self.codice_fiscale or self.pk}.png"
        self.qr_code.save(filename, ContentFile(buffer.read()), save=False)

    def save(self, *args, **kwargs):
        if self.nome:
            self.nome = self.nome.strip().title()
        if self.cognome:
            self.cognome = self.cognome.strip().title()
        super().save(*args, **kwargs)


@receiver(post_save, sender=Socio)
def crea_quota_iniziale(sender, instance, created, **kwargs):
    if not created:
        return
    today = timezone.now().date()
    anno = today.year
    data_scadenza = get_data_scadenza_default(anno)
    quota = Quota.objects.create(
        socio=instance,
        anno=anno,
        importo=5,
        stato="in_attesa",
        data_inizio=today.replace(day=1),
        data_scadenza=data_scadenza,
    )
    # Generate PDF
    try:
        from anagrafica.pdf_utils import genera_pdf_iscrizione

        genera_pdf_iscrizione(instance, quota)
    except Exception:
        logging.getLogger(__name__).exception(
            "Errore generazione PDF iscrizione per %s", instance
        )


class Quota(models.Model):
    STATO_CHOICES = [
        ("pagata", "Pagata"),
        ("in_attesa", "In attesa di pagamento"),
        ("annullata", "Annullata"),
    ]

    socio = models.ForeignKey(
        Socio, verbose_name="Socio", on_delete=models.CASCADE, related_name="quote"
    )
    anno = models.PositiveIntegerField(verbose_name="Anno")
    importo = models.DecimalField(
        verbose_name="Importo (€)", max_digits=8, decimal_places=2
    )
    stato = models.CharField(
        verbose_name="Stato", max_length=20, choices=STATO_CHOICES, default="in_attesa"
    )
    data_pagamento = models.DateField(
        verbose_name="Data pagamento", blank=True, null=True
    )
    data_inizio = models.DateField(
        verbose_name="Inizio validità", null=True, blank=True
    )
    data_scadenza = models.DateField(verbose_name="Scadenza", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Quota Associativa"
        verbose_name_plural = "Quote Associative"
        ordering = ["-anno"]
        unique_together = ("socio", "anno")

    def __str__(self):
        return f"{self.socio} — {self.anno} ({self.get_stato_display()})"

    @property
    def is_attiva(self):
        if self.data_inizio is None or self.data_scadenza is None:
            return False
        today = timezone.now().date()
        return (
            self.stato == "pagata" and self.data_inizio <= today <= self.data_scadenza
        )

    @property
    def is_scaduta(self):
        if not self.data_scadenza:
            return False
        return self.data_scadenza < timezone.now().date()

    def clean(self):
        if self.pk is None:  # only on creation
            if Quota.objects.filter(socio=self.socio, anno=self.anno).exists():
                raise ValidationError(
                    f"Esiste già una quota per {self.socio} per l'anno {self.anno}."
                )
        created = self.socio.created_at.date() if self.socio_id else None
        if created:
            created_ym = (created.year, created.month)
            if self.data_pagamento:
                dp_ym = (self.data_pagamento.year, self.data_pagamento.month)
                if dp_ym < created_ym:
                    raise ValidationError(
                        {
                            "data_pagamento": "Il mese/anno di pagamento non può essere anteriore al mese/anno di registrazione del socio."
                        }
                    )
            if self.data_inizio:
                di_ym = (self.data_inizio.year, self.data_inizio.month)
                if di_ym < created_ym:
                    raise ValidationError(
                        {
                            "data_inizio": "Il mese/anno di inizio validità non può essere anteriore al mese/anno di registrazione del socio."
                        }
                    )
