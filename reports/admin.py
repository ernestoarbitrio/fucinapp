from django.contrib import admin
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join

from anagrafica.pdf_utils import genera_pdf_verbale
from reports.models import Verbale


@admin.register(Verbale)
class VerbaleAdmin(admin.ModelAdmin):
    list_display = (
        "numero_progressivo",
        "data",
        "num_soci",
        "consiglio_direttivo",
        "pdf_link",
    )
    list_filter = ("data",)
    readonly_fields = ("numero_progressivo", "soci_list", "pdf_link")
    exclude = ("soci",)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/pdf/",
                self.admin_site.admin_view(self.pdf_view),
                name="reports_verbale_pdf",
            ),
        ]
        return custom + urls

    def pdf_view(self, request, pk):
        verbale = get_object_or_404(Verbale, pk=pk)
        buffer = genera_pdf_verbale(verbale)
        return FileResponse(
            buffer,
            as_attachment=True,
            filename=f"verbale_{verbale.numero_progressivo}_{verbale.data.year}.pdf",
            content_type="application/pdf",
        )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.assegna_soci()

    @admin.display(description="PDF")
    def pdf_link(self, obj):
        if not obj.pk:
            return "-"
        url = reverse("admin:reports_verbale_pdf", args=[obj.pk])
        return format_html('<a href="{}">📄 PDF</a>', url)

    @admin.display(description="Soci ammessi")
    def soci_list(self, obj):
        if not obj.pk:
            return "I soci verranno assegnati automaticamente al salvataggio."
        soci = obj.soci.all()
        if not soci:
            return "Nessun socio per questo anno."
        return format_html_join("", "<li>{}</li>", ((str(s),) for s in soci))

    @admin.display(description="N° soci")
    def num_soci(self, obj):
        return obj.soci.count()
