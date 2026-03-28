import datetime

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from anagrafica.forms import IscrizioneForm
from anagrafica.models import Quota, Socio


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
    today = timezone.now().date()
    anno = today.year

    if request.method == "POST":
        selected_ids = request.POST.getlist("selected_ids")
        anno = int(request.POST.get("anno", anno))
        importo = request.POST.get("importo", 0)
        data_inizio = request.POST.get("data_inizio")
        data_scadenza = request.POST.get("data_scadenza")
        stato = request.POST.get("stato", "in_attesa")

        soci = Socio.objects.filter(pk__in=selected_ids)
        created = 0
        skipped = 0

        for socio in soci:
            _, was_created = Quota.objects.get_or_create(
                socio=socio,
                anno=anno,
                defaults={
                    "importo": importo,
                    "stato": stato,
                    "data_inizio": data_inizio,
                    "data_scadenza": data_scadenza,
                    "data_pagamento": today if stato == "pagata" else None,
                },
            )
            if was_created:
                created += 1
            else:
                skipped += 1

        messages.success(
            request,
            f"✅ {created} quote create per {anno}."
            + (f" {skipped} soci saltati (quota già presente)." if skipped else ""),
        )
        return redirect("/admin/anagrafica/socio/")

    # GET — show confirmation page
    selected_ids = request.GET.getlist("ids")
    soci = Socio.objects.filter(pk__in=selected_ids)

    già_presenti = Quota.objects.filter(
        socio__in=soci,
        anno=anno,
    ).count()

    return render(
        request,
        "admin/anagrafica/bulk_renew.html",
        {
            "soci": soci,
            "selected_ids": selected_ids,
            "anno": anno,
            "importo_default": "30.00",
            "data_inizio": today.strftime("%Y-%m-%d"),
            "data_scadenza": today.replace(year=anno + 1).strftime("%Y-%m-%d"),
            "già_presenti": già_presenti,
        },
    )


@staff_member_required
def dashboard(request):
    from django.contrib.admin import site as admin_site

    today = timezone.now().date()
    in_30_days = today + datetime.timedelta(days=30)
    all_soci = Socio.objects.prefetch_related("quote").all()

    in_regola, scaduti, senza_quota = [], [], []
    for s in all_soci:
        if s.is_in_regola:
            in_regola.append(s)
        elif s.ultima_quota and s.ultima_quota.data_scadenza is not None:
            # Only count as scaduto if has a quota with a real expiry date
            scaduti.append(s)
        elif not s.ultima_quota:
            senza_quota.append(s)
        # else: has quota but data_scadenza is null — excluded from all counts

    scaduti.sort(key=lambda s: s.ultima_quota.data_scadenza)

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
        "totale": all_soci.count(),
        "in_regola": len(in_regola),
        "scaduti": len(scaduti),
        "nessuna_quota": len(senza_quota),
        "soci_senza_quota": senza_quota,
        "in_scadenza": quote_in_scadenza.count(),
        "quote_in_scadenza": quote_in_scadenza,
        "soci_scaduti": scaduti,
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
            socio.approvato = False
            socio.firma = request.POST.get("firma")
            socio.save()
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
