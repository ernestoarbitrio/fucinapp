from django import forms as django_forms
from django.contrib import admin, messages
from django.http import FileResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from tinymce.widgets import TinyMCE

from anagrafica.pdf_utils import genera_pdf_verbale
from reports.models import Newsletter, Verbale


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


class NewsletterForm(django_forms.ModelForm):
    class Meta:
        model = Newsletter
        fields = ("oggetto", "corpo", "destinatari")
        widgets = {
            "corpo": TinyMCE(attrs={"cols": 80, "rows": 30}),
        }


@admin.register(Newsletter)
class NewsletterAdmin(admin.ModelAdmin):
    form = NewsletterForm
    list_display = (
        "oggetto",
        "destinatari",
        "stato",
        "conteggio_destinatari",
        "data_invio",
    )
    list_filter = ("stato", "destinatari")
    readonly_fields = ("stato", "data_invio", "conteggio_destinatari")
    actions = ["invia_newsletter"]

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/preview/",
                self.admin_site.admin_view(self.preview_view),
                name="reports_newsletter_preview",
            ),
            path(
                "<int:pk>/send-test/",
                self.admin_site.admin_view(self.send_test_view),
                name="reports_newsletter_send_test",
            ),
        ]
        return custom + urls

    def preview_view(self, request, pk):
        newsletter = get_object_or_404(Newsletter, pk=pk)
        destinatari = newsletter.get_destinatari_queryset()
        context = {
            **self.admin_site.each_context(request),
            "newsletter": newsletter,
            "destinatari": destinatari,
            "num_destinatari": destinatari.count(),
            "opts": self.model._meta,
            "title": f"Anteprima: {newsletter.oggetto}",
        }
        return TemplateResponse(
            request, "admin/reports/newsletter_preview.html", context
        )

    def send_test_view(self, request, pk):
        import resend as resend_lib
        from django.conf import settings

        newsletter = get_object_or_404(Newsletter, pk=pk)
        email = request.user.email
        if not email:
            messages.error(
                request, "Il tuo utente non ha un indirizzo email configurato."
            )
        else:
            try:
                resend_lib.api_key = settings.RESEND_API_KEY
                resend_lib.Emails.send(
                    {
                        "from": settings.DEFAULT_FROM_EMAIL,
                        "to": [email],
                        "subject": f"[TEST] {newsletter.oggetto}",
                        "html": newsletter.corpo,
                    }
                )
                messages.success(request, f"✅ Email di test inviata a {email}.")
            except Exception as e:
                messages.error(request, f"Errore invio test: {e}")
        return HttpResponseRedirect(
            reverse("admin:reports_newsletter_change", args=[pk])
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["preview_url"] = reverse(
            "admin:reports_newsletter_preview", args=[object_id]
        )
        extra_context["send_test_url"] = reverse(
            "admin:reports_newsletter_send_test", args=[object_id]
        )
        return super().change_view(request, object_id, form_url, extra_context)

    @admin.action(description="📧 Invia newsletter selezionate")
    def invia_newsletter(self, request, queryset):
        sent_total = 0
        for nl in queryset.filter(stato="bozza"):
            sent = nl.invia()
            sent_total += sent
        if sent_total:
            messages.success(
                request, f"✅ Newsletter inviate a {sent_total} destinatari."
            )
        else:
            messages.warning(
                request,
                "Nessuna newsletter da inviare (già inviate o nessun destinatario).",
            )

    def has_change_permission(self, request, obj=None):
        if obj and obj.stato == "inviata":
            return False
        return super().has_change_permission(request, obj)

    @admin.display(description="N° destinatari")
    def conteggio_destinatari(self, obj):
        if not obj.pk:
            return "-"
        if obj.stato == "inviata":
            return obj.num_destinatari
        return obj.get_destinatari_queryset().count()
