from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse

from configurazione.models import Configurazione, ConfigurazioneAnnuale


class ConfigurazioneAnnualeInline(admin.StackedInline):
    model = ConfigurazioneAnnuale
    extra = 0
    filter_horizontal = ("consiglio_direttivo",)


@admin.register(Configurazione)
class ConfigurazioneAdmin(admin.ModelAdmin):
    inlines = [ConfigurazioneAnnualeInline]

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
            "Indirizzo",
            {
                "fields": ("via", "comune", "provincia", "cap"),
            },
        ),
    )

    def has_add_permission(self, request):
        return not Configurazione.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        config = Configurazione.get()
        return redirect(
            reverse("admin:configurazione_configurazione_change", args=[config.pk])
        )
