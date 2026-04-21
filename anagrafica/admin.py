from django import forms
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.forms import HiddenInput
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from import_export import fields, resources
from import_export.admin import ExportMixin
from import_export.formats.base_formats import XLSX

from anagrafica.admin_mixins import SocioPdfMixin
from anagrafica.forms import PROVINCE_ITALIANE
from anagrafica.models import (
    Quota,
    Socio,
    get_data_scadenza_default,
    valida_codice_fiscale,
)

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
            "tipo_documento",
            "numero_documento",
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
            "tipo_documento",
            "numero_documento",
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
        cf = (self.cleaned_data.get("codice_fiscale") or "").upper().strip()
        if not cf:
            return ""

        try:
            valida_codice_fiscale(cf)
        except forms.ValidationError as e:
            raise forms.ValidationError(e.message)

        from anagrafica.cf_utils import calcola_carattere_controllo

        expected = calcola_carattere_controllo(cf[:15])
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
        "tessera",
    )
    ordering = ("-anno",)
    readonly_fields = ("numero_tessera", "pdf_link", "tessera")

    @admin.display(description="Modulo registrazione")
    def pdf_link(self, obj):
        if not obj.pk:
            return "-"
        return format_html(
            '<a href="{}" target="_blank">📄 Genera PDF</a>',
            reverse("admin:anagrafica_socio_genera_pdf", args=[obj.socio_id, obj.pk]),
        )

    @admin.display(description="Tessera associativa")
    def tessera(self, obj):
        if not obj.pk:
            return "-"
        return format_html(
            '<a href="{}" target="_blank" style="margin-right:8px;">📄 Genera PDF</a>'
            '<a href="{}" style="color:#e65100;">📧 Invia email</a>',
            reverse(
                "admin:anagrafica_socio_genera_tessera_pdf", args=[obj.socio_id, obj.pk]
            ),
            reverse(
                "admin:anagrafica_socio_invia_tessera_email",
                args=[obj.socio_id, obj.pk],
            ),
        )

    @admin.display(description="Numero tessera")
    def numero_tessera(self, obj):
        return obj.pk if obj.pk else "-"

    def clean(self):
        super().clean()
        anno = self.cleaned_data.get("anno")
        socio = self.cleaned_data.get("socio")
        instance = self.instance
        if anno and socio:
            qs = Quota.objects.filter(socio=socio, anno=anno)
            if instance.pk:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise forms.ValidationError(f"Esiste già una quota per l'anno {anno}.")

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        today = timezone.now().date()
        formset.form.base_fields["data_inizio"].initial = today
        formset.form.base_fields["data_scadenza"].initial = get_data_scadenza_default(
            today.year
        )
        return formset


@admin.register(Socio)
class SocioAdmin(SocioPdfMixin, ExportMixin, admin.ModelAdmin):
    form = SocioAdminForm
    list_display = (
        "cognome",
        "nome",
        "tipo",
        "codice_fiscale",
        "email",
        "stato_quota_badge",
        "approvato_badge",
        "qr_code_stato",
        "qr_code_preview",
    )
    list_display_links = ("cognome", "nome")
    search_fields = ("cognome", "nome", "codice_fiscale", "email")
    list_filter = ("approvato", StatoQuotaFilter, "tipo")
    readonly_fields = ("created_at", "updated_at", "qr_code_preview", "firma_preview")
    ordering = ("cognome", "nome")
    inlines = [QuotaInline]
    actions = ["approva_soci", "rifiuta_soci", "bulk_renew", "rigenera_qr_codes"]
    resource_classes = [SocioResource]
    formats = [XLSX]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("quote")

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
                    "tipo_documento",
                    "numero_documento",
                    "tipo",
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

    @admin.display(description="Stato QR")
    def qr_code_stato(self, obj):
        if not obj.qr_code:
            return mark_safe('<span style="color:#aaa;">—</span>')
        try:
            expected = obj.get_verifica_url()
            stored = obj.qr_code.read()
            obj.qr_code.seek(0)
            # Generate expected QR in memory
            import io

            import qrcode

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=4,
            )
            qr.add_data(expected)
            qr.make(fit=True)
            buf = io.BytesIO()
            qr.make_image(fill_color="black", back_color="white").save(
                buf, format="PNG"
            )
            if stored == buf.getvalue():
                return mark_safe('<span style="color:green;">✅</span>')
            return mark_safe(
                '<span style="color:red; font-weight:bold;">❌ URL errato</span>'
            )
        except Exception:
            return mark_safe('<span style="color:orange;">⚠️</span>')

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

    @admin.display(description="Stato", boolean=False)
    def approvato_badge(self, obj):
        if obj.approvato:
            return mark_safe(
                '<span style="color:green; font-weight:bold;">✅ Approvato</span>'
            )
        return mark_safe(
            '<span style="color:orange; font-weight:bold;">⏳ In attesa</span>'
        )

    @admin.action(description="Rinnova quota per i soci selezionati")
    def bulk_renew(self, request, queryset):
        ids = queryset.values_list("pk", flat=True)
        ids_str = "&".join(f"ids={pk}" for pk in ids)
        return redirect(f"/anagrafica/bulk-renew/?{ids_str}")

    @admin.action(description="Approva soci selezionati")
    def approva_soci(self, request, queryset):
        updated = 0
        for socio in queryset.filter(approvato=False):
            socio.approvato = True
            socio.genera_qr_code(request=request)
            socio.save(update_fields=["approvato", "qr_code"])
            updated += 1
        self.message_user(request, f"✅ {updated} soci approvati.")

    @admin.action(description="Rifiuta soci selezionati")
    def rifiuta_soci(self, request, queryset):
        updated = queryset.update(approvato=False)
        self.message_user(request, f"❌ {updated} soci rifiutati.")

    @admin.action(
        description="🔄 Rigenera QR code e invia tessera per i soci selezionati"
    )
    def rigenera_qr_codes(self, request, queryset):
        from anagrafica.email_utils import invia_tessera

        rigenerati = 0
        email_inviate = 0
        errori = []
        for socio in queryset:
            socio.genera_qr_code(request=request)
            socio.save(update_fields=["qr_code"])
            rigenerati += 1
            quota = socio.quota_attiva or socio.ultima_quota
            if quota and socio.email:
                try:
                    invia_tessera(socio, quota, motivo="aggiornamento_qr")
                    email_inviate += 1
                except Exception:
                    errori.append(socio.nome_completo)
        msg = f"🔄 QR rigenerati: {rigenerati}. 📧 Tessere inviate: {email_inviate}."
        if errori:
            msg += f" ⚠️ Errori invio: {', '.join(errori)}."
        self.message_user(request, msg)


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
