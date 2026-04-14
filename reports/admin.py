from django.contrib import admin

from reports.models import Verbale


@admin.register(Verbale)
class VerbaleAdmin(admin.ModelAdmin):
    list_display = ("numero_progressivo", "data", "num_soci", "consiglio_direttivo")
    list_filter = ("data",)
    readonly_fields = ("numero_progressivo", "soci_list")
    exclude = ("soci",)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.assegna_soci()

    @admin.display(description="Soci ammessi")
    def soci_list(self, obj):
        if not obj.pk:
            return "I soci verranno assegnati automaticamente al salvataggio."
        soci = obj.soci.all()
        if not soci:
            return "Nessun socio per questo anno."
        from django.utils.html import format_html_join

        return format_html_join(
            "",
            "<li>{}</li>",
            ((str(s),) for s in soci),
        )

    @admin.display(description="N° soci")
    def num_soci(self, obj):
        return obj.soci.count()
