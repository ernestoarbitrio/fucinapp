from django import template
from django.utils import timezone
from anagrafica.models import Socio, Quota
import datetime

register = template.Library()


@register.filter
def currency_it(value):
    try:
        value = float(value)
        formatted = (
            f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        return f"€ {formatted}"
    except (ValueError, TypeError):
        return "€ 0,00"


@register.simple_tag
def get_dashboard_stats():
    today = timezone.now().date()
    in_30_days = today + datetime.timedelta(days=30)
    all_soci = Socio.objects.prefetch_related("quote").all()

    in_regola, scaduti, senza_quota = [], [], []
    for s in all_soci:
        if s.is_in_regola:
            in_regola.append(s)
        elif s.ultima_quota:
            scaduti.append(s)
        else:
            senza_quota.append(s)

    scaduti = [
        s
        for s in scaduti
        if s.ultima_quota and s.ultima_quota.data_scadenza is not None
    ]
    scaduti.sort(key=lambda s: s.ultima_quota.data_scadenza or datetime.date.min)

    quote_in_scadenza = (
        Quota.objects.filter(
            stato="pagata",
            data_scadenza__gte=today,
            data_scadenza__lte=in_30_days,
        )
        .select_related("socio")
        .order_by("data_scadenza")[:10]
    )

    for q in quote_in_scadenza:
        q.giorni_rimasti = (q.data_scadenza - today).days

    return {
        "totale": all_soci.count(),
        "in_regola": len(in_regola),
        "scaduti": len(scaduti),
        "nessuna_quota": len(senza_quota),
        "in_scadenza": quote_in_scadenza.count(),
        "quote_in_scadenza": quote_in_scadenza,
        "soci_scaduti": scaduti[:10],
    }
