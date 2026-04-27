import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from anagrafica.email_utils import invia_email_iscrizione
from anagrafica.forms import IscrizioneForm
from anagrafica.models import Quota, Socio, TIPO_DOCUMENTO_CHOICES


def verifica_socio(request, token):
    socio = get_object_or_404(Socio, token=token)
    return render(
        request,
        "anagrafica/verifica_socio.html",
        {
            "socio": socio,
            "quota": socio.quota_attiva,
            "ultima_quota": socio.ultima_quota,
            "in_regola": socio.is_in_regola,
        },
    )


@staff_member_required
def bulk_renew(request):
    from django.contrib.admin import site as admin_site

    from anagrafica.models import get_data_scadenza_default

    today = timezone.now().date()
    anno_corrente = today.year

    # Only soci WITHOUT a quota for the current year are eligible
    soci_ids = request.GET.getlist("ids") or request.POST.getlist("selected_ids")
    soci = Socio.objects.filter(pk__in=soci_ids).prefetch_related("quote")

    eligibili = [s for s in soci if not s.quote.filter(anno=anno_corrente).exists()]
    non_eligibili = [s for s in soci if s.quote.filter(anno=anno_corrente).exists()]

    data_scadenza = get_data_scadenza_default(anno_corrente)

    if request.method == "POST":
        try:
            importo = Decimal(request.POST.get("importo", "5"))
            if importo <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            messages.error(request, "Importo non valido.")
            return redirect("/admin/anagrafica/socio/")
        stato = request.POST.get("stato", "in_attesa")
        creati = 0

        for socio in eligibili:
            Quota.objects.create(
                socio=socio,
                anno=anno_corrente,
                importo=importo,
                stato=stato,
                data_inizio=today,
                data_scadenza=data_scadenza,
            )
            creati += 1

        messages.success(request, f"✅ Rinnovo completato per {creati} soci.")
        if non_eligibili:
            nomi = ", ".join(str(s) for s in non_eligibili)
            messages.warning(request, f"⚠️ Già rinnovati per {anno_corrente}: {nomi}")

        return redirect("/admin/anagrafica/socio/")

    admin_context = admin_site.each_context(request)
    context = {
        **admin_context,
        "title": f"Rinnovo quote {anno_corrente}",
        "eligibili": eligibili,
        "non_eligibili": non_eligibili,
        "anno_corrente": anno_corrente,
        "data_scadenza": data_scadenza,
        "data_inizio": today,
        "opts": Socio._meta,
    }
    return render(request, "admin/anagrafica/bulk_renew.html", context)


@staff_member_required
def dashboard(request):
    from django.contrib.admin import site as admin_site
    from django.db.models import Exists, Max, OuterRef

    today = timezone.now().date()
    in_30_days = today + datetime.timedelta(days=30)

    all_soci = Socio.objects.all()
    totale = all_soci.count()

    # Subquery: socio has an active paid quota covering today
    active_quota = Quota.objects.filter(
        socio=OuterRef("pk"),
        stato="pagata",
        data_inizio__lte=today,
        data_scadenza__gte=today,
    )
    has_any_quota = Quota.objects.filter(socio=OuterRef("pk"))

    annotated = all_soci.annotate(
        _in_regola=Exists(active_quota),
        _has_quota=Exists(has_any_quota),
        _ultima_scadenza=Max("quote__data_scadenza"),
    )

    in_regola_count = annotated.filter(_in_regola=True).count()

    # Pending quota: in_attesa payment
    pending_quota = Quota.objects.filter(
        socio=OuterRef("pk"),
        stato="in_attesa",
    )
    annotated = annotated.annotate(_has_pending=Exists(pending_quota))

    # Scaduti: not in regola, has quota, has a real scadenza date, NO pending
    soci_scaduti = list(
        annotated.filter(
            _in_regola=False,
            _has_quota=True,
            _has_pending=False,
            _ultima_scadenza__isnull=False,
        )
        .prefetch_related("quote")
        .order_by("_ultima_scadenza")
    )

    # Incomplete: has a pending (in_attesa) quota
    soci_incomplete = list(
        annotated.filter(_has_pending=True, _in_regola=False)
        .prefetch_related("quote")
        .order_by("cognome", "nome")
    )

    # Senza quota: no quota at all
    soci_senza_quota = list(annotated.filter(_has_quota=False))

    quote_in_scadenza = (
        Quota.objects.filter(
            stato="pagata",
            data_scadenza__isnull=False,
            data_scadenza__gte=today,
            data_scadenza__lte=in_30_days,
        )
        .select_related("socio")
        .order_by("data_scadenza")
    )
    for q in quote_in_scadenza:
        q.giorni_rimasti = (q.data_scadenza - today).days

    context = {
        **admin_site.each_context(request),
        "title": "Dashboard completa",
        "totale": totale,
        "in_regola": in_regola_count,
        "scaduti": len(soci_scaduti),
        "incomplete": len(soci_incomplete),
        "nessuna_quota": len(soci_senza_quota),
        "soci_senza_quota": soci_senza_quota,
        "in_scadenza": quote_in_scadenza.count(),
        "quote_in_scadenza": quote_in_scadenza,
        "soci_scaduti": soci_scaduti,
        "soci_incomplete": soci_incomplete,
    }
    return render(request, "admin/anagrafica/dashboard.html", context)


@staff_member_required
def budget(request):
    from django.contrib.admin import site as admin_site
    from django.db.models import Avg, Count, Sum

    today = timezone.now().date()
    anno_corrente = today.year

    # Overall totals
    totale_incassato = (
        Quota.objects.filter(stato="pagata").aggregate(t=Sum("importo"))["t"] or 0
    )
    totale_anno = (
        Quota.objects.filter(stato="pagata", anno=anno_corrente).aggregate(
            t=Sum("importo")
        )["t"]
        or 0
    )
    totale_attesa = (
        Quota.objects.filter(stato="in_attesa").aggregate(t=Sum("importo"))["t"] or 0
    )
    media_quota = (
        Quota.objects.filter(stato="pagata").aggregate(a=Avg("importo"))["a"] or 0
    )

    # Per year breakdown
    per_anno = (
        Quota.objects.filter(stato="pagata")
        .values("anno")
        .annotate(totale=Sum("importo"), numero=Count("id"))
        .order_by("-anno")
    )

    # Pending quotas
    quote_in_attesa = (
        Quota.objects.filter(stato="in_attesa")
        .select_related("socio")
        .order_by("data_scadenza")
    )

    # All paid quotas for the current year
    quote_pagate_anno = (
        Quota.objects.filter(
            stato="pagata",
            anno=anno_corrente,
        )
        .select_related("socio")
        .order_by("-data_pagamento")
    )

    admin_context = admin_site.each_context(request)

    context = {
        **admin_context,
        "title": "Budget",
        "totale_incassato": totale_incassato,
        "totale_anno": totale_anno,
        "totale_attesa": totale_attesa,
        "media_quota": round(media_quota, 2),
        "anno_corrente": anno_corrente,
        "per_anno": per_anno,
        "quote_in_attesa": quote_in_attesa,
        "quote_pagate_anno": quote_pagate_anno,
    }
    return render(request, "admin/anagrafica/budget.html", context)


# Public Views


def iscrizione(request):
    if request.method == "POST":
        form = IscrizioneForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data.copy()
            data["data_nascita"] = form.cleaned_data["data_nascita"].isoformat()
            data["tipo_documento_display"] = dict(TIPO_DOCUMENTO_CHOICES).get(
                data.get("tipo_documento", ""), ""
            )
            request.session["iscrizione_data"] = data
            return redirect("anagrafica:iscrizione_riepilogo")
    else:
        form = IscrizioneForm()
    return render(request, "anagrafica/iscrizione.html", {"form": form})


def iscrizione_riepilogo(request):
    data = request.session.get("iscrizione_data")
    if not data:
        return redirect("anagrafica:iscrizione")

    if request.method == "POST":
        firma = request.POST.get("firma")
        consenso_trattamento = request.POST.get("consenso_trattamento") == "True"

        errors = {
            "error_trattamento": not consenso_trattamento,
            "error_firma": not firma,
        }
        if any(errors.values()):
            return render(
                request,
                "anagrafica/iscrizione_riepilogo.html",
                {"data": data, **errors},
            )

        form_data = {
            **data,
            "consenso_marketing": request.POST.get("consenso_marketing") == "True",
            "consenso_immagini": request.POST.get("consenso_immagini") == "True",
        }
        form = IscrizioneForm(form_data)
        if form.is_valid():
            socio = form.save(commit=False)
            socio.approvato = True
            socio.firma = request.POST.get("firma")
            socio.save()
            socio.genera_qr_code()
            socio.save(update_fields=["qr_code"])
            # Get the auto-created quota
            quota = socio.quote.order_by("-anno").first()
            # Send confirmation email
            invia_email_iscrizione(socio, quota)
            del request.session["iscrizione_data"]
            return redirect("anagrafica:iscrizione_completata")

    return render(
        request,
        "anagrafica/iscrizione_riepilogo.html",
        {
            "data": data,
            "error_trattamento": False,
            "error_firma": False,
        },
    )


def iscrizione_completata(request):
    return render(request, "anagrafica/iscrizione_completata.html")
