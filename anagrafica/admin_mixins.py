import io

from django.contrib import admin, messages
from django.http import FileResponse, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils import timezone
from pypdf import PdfReader, PdfWriter

from anagrafica.email_utils import invia_tessera
from anagrafica.models import Quota, Socio
from anagrafica.pdf_utils import (
    genera_pdf_elenco_soci,
    genera_pdf_iscrizione,
    genera_pdf_tessera,
)


class SocioPdfMixin:
    """Mixin that adds PDF generation/email URLs and views to SocioAdmin."""

    def get_urls(self):
        custom = [
            path(
                "<int:socio_id>/quota/<int:quota_id>/genera-pdf/",
                self.admin_site.admin_view(self.genera_pdf_view),
                name="anagrafica_socio_genera_pdf",
            ),
            path(
                "<int:socio_id>/quota/<int:quota_id>/genera-tessera/",
                self.admin_site.admin_view(self.genera_pdf_tessera_view),
                name="anagrafica_socio_genera_tessera_pdf",
            ),
            path(
                "registro-soci-pdf/",
                self.admin_site.admin_view(self.registro_soci_pdf_view),
                name="anagrafica_socio_registro_pdf",
            ),
            path(
                "<int:socio_id>/quota/<int:quota_id>/invia-tessera-email/",
                self.admin_site.admin_view(self.invia_tessera_email_view),
                name="anagrafica_socio_invia_tessera_email",
            ),
            path(
                "moduli-iscrizione-pdf/",
                self.admin_site.admin_view(self.moduli_iscrizione_pdf_view),
                name="anagrafica_socio_moduli_iscrizione_pdf",
            ),
        ]
        return custom + super().get_urls()

    def genera_pdf_view(self, request, socio_id, quota_id):
        socio = get_object_or_404(Socio, pk=socio_id)
        quota = get_object_or_404(Quota, pk=quota_id, socio=socio)
        try:
            buffer = genera_pdf_iscrizione(socio, quota)
            return FileResponse(
                buffer,
                as_attachment=False,
                filename=f"iscrizione_{socio.codice_fiscale or socio.pk}_{quota.anno}.pdf",
                content_type="application/pdf",
            )
        except Exception as e:
            messages.error(request, f"Errore nella generazione del PDF: {e}")
            return HttpResponseRedirect(
                reverse("admin:anagrafica_socio_change", args=[socio_id])
            )

    def genera_pdf_tessera_view(self, request, socio_id, quota_id):
        socio = get_object_or_404(Socio, pk=socio_id)
        quota = get_object_or_404(Quota, pk=quota_id, socio=socio)
        try:
            buffer = genera_pdf_tessera(socio, quota)
            return FileResponse(
                buffer,
                as_attachment=False,
                filename=f"tessera_{socio.codice_fiscale or socio.pk}_{quota.anno}.pdf",
                content_type="application/pdf",
            )
        except Exception as e:
            messages.error(request, f"Errore nella generazione del PDF: {e}")
            return HttpResponseRedirect(
                reverse("admin:anagrafica_socio_change", args=[socio_id])
            )

    def invia_tessera_email_view(self, request, socio_id, quota_id):
        socio = get_object_or_404(Socio, pk=socio_id)
        quota = get_object_or_404(Quota, pk=quota_id, socio=socio)
        try:
            invia_tessera(socio, quota)
            messages.success(request, f"✅ Tessera inviata via email a {socio.email}.")
        except Exception as e:
            messages.error(request, f"Errore invio email: {e}")
        return HttpResponseRedirect(
            reverse("admin:anagrafica_socio_change", args=[socio_id])
        )

    @admin.action(description="📋 Esporta registro soci PDF")
    def export_registro_soci_pdf(self, request, queryset):
        soci = (
            queryset.filter(approvato=True)
            .prefetch_related("quote")
            .order_by("cognome", "nome")
        )
        buffer = genera_pdf_elenco_soci(soci)
        today = timezone.now().date()
        return FileResponse(
            buffer,
            as_attachment=True,
            filename=f"elenco_soci_{today.strftime('%Y%m%d')}.pdf",
            content_type="application/pdf",
        )

    def registro_soci_pdf_view(self, request):
        anno_corrente = timezone.now().year
        anni = Quota.objects.values_list("anno", flat=True).distinct().order_by("-anno")

        if request.method == "POST":
            anno = int(request.POST.get("anno", anno_corrente))
            soci = (
                Socio.objects.filter(
                    approvato=True,
                    quote__stato="pagata",
                    quote__anno=anno,
                )
                .prefetch_related("quote")
                .distinct()
                .order_by("cognome", "nome")
            )
            buffer = genera_pdf_elenco_soci(soci, anno=anno)
            return FileResponse(
                buffer,
                as_attachment=True,
                filename=f"registro_soci_{anno}.pdf",
                content_type="application/pdf",
            )

        context = {
            **self.admin_site.each_context(request),
            "title": "Genera registro soci",
            "anni": anni,
            "anno_corrente": anno_corrente,
            "opts": self.model._meta,
        }
        return render(request, "admin/anagrafica/registro_soci_select.html", context)

    def moduli_iscrizione_pdf_view(self, request):
        anno_corrente = timezone.now().year
        anni = Quota.objects.values_list("anno", flat=True).distinct().order_by("-anno")

        if request.method == "POST":
            anno = int(request.POST.get("anno", anno_corrente))
            soci = (
                Socio.objects.filter(approvato=True, quote__anno=anno)
                .prefetch_related("quote")
                .distinct()
                .order_by("cognome", "nome")
            )
            writer = PdfWriter()
            errors = []
            for socio in soci:
                quota = socio.quote.filter(anno=anno).first()
                if not quota:
                    continue
                try:
                    buffer = genera_pdf_iscrizione(socio, quota)
                    reader = PdfReader(buffer)
                    for page in reader.pages:
                        writer.add_page(page)
                except Exception as e:
                    errors.append(f"{socio}: {e}")
            if errors:
                for err in errors:
                    messages.warning(request, err)
            output = io.BytesIO()
            writer.write(output)
            output.seek(0)
            response = HttpResponse(output, content_type="application/pdf")
            response["Content-Disposition"] = (
                f'attachment; filename="moduli_iscrizione_{anno}.pdf"'
            )
            return response

        context = {
            **self.admin_site.each_context(request),
            "title": "Genera moduli iscrizione",
            "anni": anni,
            "anno_corrente": anno_corrente,
            "opts": self.model._meta,
        }
        return render(request, "admin/anagrafica/moduli_iscrizione.html", context)
