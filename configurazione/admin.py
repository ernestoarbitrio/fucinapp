from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse

from configurazione.models import Configurazione


@admin.register(Configurazione)
class ConfigurazioneAdmin(admin.ModelAdmin):
    filter_horizontal = ("consiglio_direttivo",)

    fieldsets = (
        (
            "Anagrafica",
            {
                "fields": (
                    "nome_associazione",
                    "logo",
                    "logo_secondario",
                    "email",
                    "pec",
                    "cf",
                ),
            },
        ),
        (
            "Firma del presidente",
            {
                "fields": ("firma_presidente",),
            },
        ),
        (
            "Indirizzo",
            {
                "fields": ("via", "comune", "provincia", "cap"),
            },
        ),
        (
            "Consiglio direttivo",
            {
                "fields": ("consiglio_direttivo",),
            },
        ),
        (
            "Impostazioni",
            {
                "fields": (
                    "delta_giorni_iscrizione",
                    "delta_giorni_registro",
                    "scadenza_quota_giorno",
                    "scadenza_quota_mese",
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        # Only allow one instance
        return not Configurazione.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        config = Configurazione.get()
        return redirect(
            reverse("admin:configurazione_configurazione_change", args=[config.pk])
        )
