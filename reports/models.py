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
