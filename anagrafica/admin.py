from django import forms
from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.forms import HiddenInput
from django.http import FileResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from import_export import fields, resources
from import_export.admin import ExportMixin
from import_export.formats.base_formats import XLSX

from anagrafica.forms import PROVINCE_ITALIANE
from anagrafica.models import Quota, Socio, valida_codice_fiscale
from anagrafica.pdf_utils import genera_pdf_elenco_soci, genera_pdf_iscrizione

MODAL_HTML = """
<div id="qr-modal-overlay" style="
    display:none; position:fixed; inset:0;
    background:rgba(0,0,0,0.55); z-index:9999;
    align-items:center; justify-content:center;
    backdrop-filter:blur(3px);
" onclick="if(event.target===this)this.style.display='none';">
    <div style="
        background:white; border-radius:16px; padding:32px;
        box-shadow:0 16px 48px rgba(0,0,0,0.3);
        position:relative; display:flex; flex-direction:column;
        align-items:center; gap:12px; animation: qrpop 0.2s ease;
    ">
        <button onclick="document.getElementById('qr-modal-overlay').style.display='none'" style="
            position:absolute; top:10px; right:10px;
            background:#f1f1f1; border:none; border-radius:50%;
            width:32px; height:32px; font-size:16px;
            cursor:pointer; line-height:1;
        ">✕</button>
        <img id="qr-modal-img" src="" style="width:260px; height:260px; display:block;" />
        <div id="qr-modal-name" style="font-weight:600; color:#333; font-size:1rem;"></div>
    </div>
</div>
<style>
    @keyframes qrpop {
        from { transform:scale(0.85); opacity:0; }
        to   { transform:scale(1);   opacity:1; }
    }
</style>
<script>
    document.addEventListener("keydown", function(e) {
        if (e.key === "Escape") document.getElementById("qr-modal-overlay").style.display = "none";
    });
</script>
"""


class StatoQuotaFilter(SimpleListFilter):
    title = "Stato quota"
    parameter_name = "stato_quota"

    def lookups(self, request, model_admin):
        return [
            ("in_regola", "✅ In regola"),
            ("in_attesa", "⏳ In attesa di pagamento"),
            ("scaduta", "❌ Quota scaduta"),
            ("incompleta", "❗️ Quota incompleta"),
            ("nessuna", "⚠️ Nessuna quota"),
        ]

    def queryset(self, request, queryset):
        today = timezone.now().date()

        if self.value() == "in_regola":
            return queryset.filter(
                quote__stato="pagata",
                quote__data_inizio__lte=today,
                quote__data_scadenza__gte=today,
            ).distinct()

        if self.value() == "in_attesa":
            attivi = queryset.filter(
                quote__stato="pagata",
                quote__data_inizio__lte=today,
                quote__data_scadenza__gte=today,
            )
            return (
                queryset.filter(quote__stato="in_attesa")
                .exclude(pk__in=attivi)
                .distinct()
            )

        if self.value() == "incompleta":
            # Has a quota but data_scadenza is null
            attivi = queryset.filter(
                quote__stato="pagata",
                quote__data_inizio__lte=today,
                quote__data_scadenza__gte=today,
            )
            in_attesa = queryset.filter(quote__stato="in_attesa")
            return (
                queryset.filter(
                    quote__isnull=False,
                    quote__data_scadenza__isnull=True,
                )
                .exclude(pk__in=attivi)
                .exclude(pk__in=in_attesa)
                .distinct()
            )

        if self.value() == "scaduta":
            attivi = queryset.filter(
                quote__stato="pagata",
                quote__data_inizio__lte=today,
                quote__data_scadenza__gte=today,
            )
            in_attesa = queryset.filter(quote__stato="in_attesa")
            incompleta = queryset.filter(
                quote__isnull=False,
                quote__data_scadenza__isnull=True,
            )
            return (
                queryset.filter(
                    quote__isnull=False,
                    quote__data_scadenza__isnull=False,
                )
                .exclude(pk__in=attivi)
                .exclude(pk__in=in_attesa)
                .exclude(pk__in=incompleta)
                .distinct()
            )

        if self.value() == "nessuna":
            return queryset.filter(quote__isnull=True)

        return queryset


class SocioResource(resources.ModelResource):
    stato_quota = fields.Field(column_name="Stato quota")
    anno_quota = fields.Field(column_name="Anno quota")
    importo_quota = fields.Field(column_name="Importo quota (€)")
    data_pagamento = fields.Field(column_name="Data pagamento")
    inizio_validita = fields.Field(column_name="Inizio validità")
    scadenza_quota = fields.Field(column_name="Scadenza quota")

    class Meta:
        model = Socio
        fields = (
            "cognome",
            "nome",
            "codice_fiscale",
            "email",
            "data_nascita",
            "luogo_nascita",
            "via",
            "comune",
            "cap",
            "provincia",
            "stato_quota",
            "anno_quota",
            "importo_quota",
            "data_pagamento",
            "inizio_validita",
            "scadenza_quota",
        )
        export_order = (
            "cognome",
            "nome",
            "codice_fiscale",
            "email",
            "data_nascita",
            "luogo_nascita",
            "via",
            "comune",
            "cap",
            "provincia",
            "stato_quota",
            "anno_quota",
            "importo_quota",
            "data_pagamento",
            "inizio_validita",
            "scadenza_quota",
        )

    def dehydrate_stato_quota(self, socio):
        if socio.is_in_regola:
            return "In regola"
        return "Scaduta" if socio.ultima_quota else "Nessuna quota"

    def dehydrate_anno_quota(self, socio):
        q = socio.quota_attiva or socio.ultima_quota
        return q.anno if q else ""

    def dehydrate_importo_quota(self, socio):
        q = socio.quota_attiva or socio.ultima_quota
        return str(q.importo) if q else ""

    def dehydrate_data_pagamento(self, socio):
        q = socio.quota_attiva or socio.ultima_quota
        return q.data_pagamento.strftime("%d/%m/%Y") if q and q.data_pagamento else ""

    def dehydrate_inizio_validita(self, socio):
        q = socio.quota_attiva or socio.ultima_quota
        return q.data_inizio.strftime("%d/%m/%Y") if q else ""

    def dehydrate_scadenza_quota(self, socio):
        q = socio.quota_attiva or socio.ultima_quota
        return q.data_scadenza.strftime("%d/%m/%Y") if q else ""


class SocioAdminForm(forms.ModelForm):
    provincia = forms.ChoiceField(
        choices=[("", "— Seleziona —")] + PROVINCE_ITALIANE,
        widget=forms.Select(attrs={"id": "id_provincia"}),
    )

    class Meta:
        model = Socio
        fields = "__all__"
        widgets = {
            "firma": HiddenInput(),
        }

    class Media:
        js = ("anagrafica/comune_select.js",)

    def clean_codice_fiscale(self):
        cf = self.cleaned_data.get("codice_fiscale", "").upper().strip()

        # run the base format validator
        try:
            valida_codice_fiscale(cf)
        except forms.ValidationError as e:
            raise forms.ValidationError(e.message)

        # verify the control character (last letter)
        odd_values = {
            "0": 1,
            "1": 0,
            "2": 5,
            "3": 7,
            "4": 9,
            "5": 13,
            "6": 15,
            "7": 17,
            "8": 19,
            "9": 21,
            "A": 1,
            "B": 0,
            "C": 5,
            "D": 7,
            "E": 9,
            "F": 13,
            "G": 15,
            "H": 17,
            "I": 19,
            "J": 21,
            "K": 2,
            "L": 4,
            "M": 18,
            "N": 20,
            "O": 11,
            "P": 3,
            "Q": 6,
            "R": 8,
            "S": 12,
            "T": 14,
            "U": 16,
            "V": 10,
            "W": 22,
            "X": 25,
            "Y": 24,
            "Z": 23,
        }
        even_values = {
            "0": 0,
            "1": 1,
            "2": 2,
            "3": 3,
            "4": 4,
            "5": 5,
            "6": 6,
            "7": 7,
            "8": 8,
            "9": 9,
            "A": 0,
            "B": 1,
            "C": 2,
            "D": 3,
            "E": 4,
            "F": 5,
            "G": 6,
            "H": 7,
            "I": 8,
            "J": 9,
            "K": 10,
            "L": 11,
            "M": 12,
            "N": 13,
            "O": 14,
            "P": 15,
            "Q": 16,
            "R": 17,
            "S": 18,
            "T": 19,
            "U": 20,
            "V": 21,
            "W": 22,
            "X": 23,
            "Y": 24,
            "Z": 25,
        }
        total = 0
        for i, char in enumerate(cf[:15]):
            if (i + 1) % 2 == 0:
                total += even_values[char]
            else:
                total += odd_values[char]

        expected = chr(total % 26 + ord("A"))
        if cf[15] != expected:
            raise forms.ValidationError(
                f"Il carattere di controllo del codice fiscale non è corretto (atteso: {expected})."
            )

        return cf


class QuotaInline(admin.StackedInline):
    model = Quota
    extra = 0
    fields = (
        "anno",
        "numero_tessera",
        "importo",
        "stato",
        "data_pagamento",
        "data_inizio",
        "data_scadenza",
        "pdf_link",
    )
    ordering = ("-anno",)
    readonly_fields = ("numero_tessera", "pdf_link")

    @admin.display(description="PDF")
    def pdf_link(self, obj):
        if not obj.pk:
            return "-"
        return format_html(
            '<a href="{}" target="_blank">📄 Genera PDF</a>',
            reverse("admin:anagrafica_socio_genera_pdf", args=[obj.socio_id, obj.pk]),
        )

    @admin.display(description="Numero tessera")
    def numero_tessera(self, obj):
        return obj.pk if obj.pk else "-"


@admin.register(Socio)
class SocioAdmin(ExportMixin, admin.ModelAdmin):
    form = SocioAdminForm
    list_display = (
        "cognome",
        "nome",
        "tipo",
        "codice_fiscale",
        "email",
        "stato_quota_badge",
        "approvato_badge",
        "qr_code_preview",
    )
    list_display_links = ("cognome", "nome")
    search_fields = ("cognome", "nome", "codice_fiscale", "email")
    list_filter = ("approvato", StatoQuotaFilter, "tipo")
    readonly_fields = ("created_at", "updated_at", "qr_code_preview", "firma_preview")
    ordering = ("cognome", "nome")
    inlines = [QuotaInline]
    actions = ["bulk_renew", "approva_soci", "rifiuta_soci"]
    resource_classes = [SocioResource]
    formats = [XLSX]

    fieldsets = (
        (
            "Dati Anagrafici",
            {
                "fields": (
                    "nome",
                    "cognome",
                    "data_nascita",
                    "luogo_nascita",
                    "codice_fiscale",
                )
            },
        ),
        (
            "Contatti",
            {"fields": ("email", "telefono", "via", "comune", "cap", "provincia")},
        ),
        (
            "QR Code e Stato",
            {
                "fields": (
                    "qr_code_preview",
                    "approvato",
                    "consenso_marketing",
                    "consenso_immagini",
                ),
            },
        ),
        ("Firma", {"fields": ("firma_preview", "firma")}),
        (
            "Informazioni di Sistema",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        is_new = obj.pk is None
        was_approvato = False
        if change:
            try:
                was_approvato = Socio.objects.get(pk=obj.pk).approvato
            except Socio.DoesNotExist:
                pass

        super().save_model(request, obj, form, change)

        # Generate QR if new and approved, or if just approved for the first time
        if (is_new and obj.approvato) or (
            change and not was_approvato and obj.approvato
        ):
            obj.genera_qr_code(request=request)
            obj.save(update_fields=["qr_code"])

    @admin.display(description="Quota")
    def stato_quota_badge(self, obj):
        if obj.is_in_regola:
            scadenza = obj.quota_attiva.data_scadenza.strftime("%d/%m/%Y")
            return format_html(
                '<span style="color:green; font-weight:bold;">✅ In regola</span><br><small>(scade: {})</small>',
                scadenza,
            )

        # Check for pending quota
        quota_in_attesa = obj.quote.filter(stato="in_attesa").order_by("-anno").first()
        if quota_in_attesa:
            return format_html(
                '<span style="color:#f0a500; font-weight:bold;">⏳ In attesa</span><br><small>(anno: {})</small>',
                quota_in_attesa.anno,
            )

        ultima = obj.ultima_quota
        if ultima:
            scadenza = (
                ultima.data_scadenza.strftime("%d/%m/%Y")
                if ultima.data_scadenza
                else None
            )
            if not scadenza:
                return format_html(
                    '<span style="color:red; font-weight:bold;">❗️ Incompleta</span>',
                    scadenza,
                )
            return format_html(
                '<span style="color:red; font-weight:bold;">❌ Scaduta</span><br><small>(il: {})</small>',
                scadenza,
            )

        return mark_safe(
            '<span style="color:orange; font-weight:bold;">⚠️ Nessuna quota</span>'
        )

    @admin.display(description="QR Code")
    def qr_code_preview(self, obj):
        if obj.qr_code:
            return format_html(
                """
                {}
                <img
                    src="{}"
                    width="40" height="40"
                    style="cursor:pointer; border-radius:4px;"
                    onclick="
                        document.getElementById('qr-modal-img').src='{}';
                        document.getElementById('qr-modal-name').textContent='{}';
                        document.getElementById('qr-modal-overlay').style.display='flex';
                    "
                />
                """,
                mark_safe(MODAL_HTML),
                obj.qr_code.url,
                obj.qr_code.url,
                obj.nome_completo,
            )
        return mark_safe('<span style="color:#aaa;">Non ancora generato</span>')

    @admin.display(description="Firma")
    def firma_preview(self, obj):
        if not obj.firma:
            return mark_safe(
                '<span style="color:var(--body-quiet-color)">Nessuna firma</span>'
            )
        return mark_safe(
            f'<img src="{obj.firma}" style="max-width:300px; border:1px solid #ddd; border-radius:8px;">'
        )

    @admin.action(description="♻️ Rinnova quota per i soci selezionati")
    def bulk_renew(self, request, queryset):
        ids = queryset.values_list("pk", flat=True)
        ids_str = "&".join(f"ids={pk}" for pk in ids)
        return redirect(f"/anagrafica/bulk-renew/?{ids_str}")

    @admin.display(description="Stato", boolean=False)
    def approvato_badge(self, obj):
        if obj.approvato:
            return mark_safe(
                '<span style="color:green; font-weight:bold;">✅ Approvato</span>'
            )
        return mark_safe(
            '<span style="color:orange; font-weight:bold;">⏳ In attesa</span>'
        )

    @admin.action(description="✅ Approva soci selezionati")
    def approva_soci(self, request, queryset):
        updated = 0
        for socio in queryset.filter(approvato=False):
            socio.approvato = True
            socio.genera_qr_code(request=request)
            socio.save(update_fields=["approvato", "qr_code"])
            updated += 1
        self.message_user(request, f"✅ {updated} soci approvati.")

    @admin.action(description="❌ Rifiuta soci selezionati")
    def rifiuta_soci(self, request, queryset):
        updated = queryset.update(approvato=False)
        self.message_user(request, f"❌ {updated} soci rifiutati.")

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:socio_id>/quota/<int:quota_id>/genera-pdf/",
                self.admin_site.admin_view(self.genera_pdf_view),
                name="anagrafica_socio_genera_pdf",
            ),
            path(
                "registro-soci-pdf/",
                self.admin_site.admin_view(self.registro_soci_pdf_view),
                name="anagrafica_socio_registro_pdf",
            ),
        ]
        return custom + urls

    def genera_pdf_view(self, request, socio_id, quota_id):
        socio = get_object_or_404(Socio, pk=socio_id)
        quota = get_object_or_404(Quota, pk=quota_id, socio=socio)
        try:
            buffer = genera_pdf_iscrizione(socio, quota)
            return FileResponse(
                buffer,
                as_attachment=False,
                filename=f"iscrizione_{socio.codice_fiscale}_{quota.anno}.pdf",
                content_type="application/pdf",
            )
        except Exception as e:
            messages.error(request, f"Errore nella generazione del PDF: {e}")
            return HttpResponseRedirect(
                reverse("admin:anagrafica_socio_change", args=[socio_id])
            )

    @admin.action(description="📋 Esporta registro soci PDF")
    def export_registro_soci_pdf(self, request, queryset):
        from django.http import FileResponse
        from django.utils import timezone

        from anagrafica.pdf_utils import genera_pdf_elenco_soci

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
        today = timezone.now().date()
        anno_corrente = today.year
        soci = (
            Socio.objects.filter(
                approvato=True,
                quote__stato="pagata",
                quote__anno=anno_corrente,
            )
            .prefetch_related("quote")
            .distinct()
            .order_by("cognome", "nome")
        )
        buffer = genera_pdf_elenco_soci(soci)
        return FileResponse(
            buffer,
            as_attachment=True,
            filename=f"registro_soci_{today.strftime('%Y%m%d')}.pdf",
            content_type="application/pdf",
        )


@admin.register(Quota)
class QuotaAdmin(admin.ModelAdmin):
    list_display = (
        "socio",
        "anno",
        "importo",
        "stato",
        "data_pagamento",
        "data_inizio",
        "data_scadenza",
        "is_attiva_badge",
    )
    list_filter = ("stato", "anno")
    search_fields = ("socio__cognome", "socio__nome", "socio__codice_fiscale")
    ordering = ("-anno", "socio__cognome")

    @admin.display(description="Attiva")
    def is_attiva_badge(self, obj):
        if obj.is_attiva:
            return mark_safe(
                '<span style="color:green; font-weight:bold;">✅ Sì</span>'
            )
        if obj.is_scaduta:
            return mark_safe(
                '<span style="color:red; font-weight:bold;">❌ Scaduta</span>'
            )
        return mark_safe(
            '<span style="color:orange; font-weight:bold;">⏳ Non pagata</span>'
        )

    def save_model(self, request, obj, form, change):
        if change and obj.pdf_iscrizione:
            obj.pdf_iscrizione.delete(save=False)
            obj.pdf_iscrizione = None
        super().save_model(request, obj, form, change)
