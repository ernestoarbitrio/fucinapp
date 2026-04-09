from django.urls import path

from anagrafica import views

app_name = "anagrafica"

urlpatterns = [
    path("verifica/<uuid:token>/", views.verifica_socio, name="verifica_socio"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("budget/", views.budget, name="budget"),
    path("iscrizione/", views.iscrizione, name="iscrizione"),
    path("bulk-renew/", views.bulk_renew, name="bulk_renew"),
    # path("elenco-soci-pdf/", views.elenco_soci_pdf, name="elenco_soci_pdf"),
    path(
        "iscrizione/riepilogo/", views.iscrizione_riepilogo, name="iscrizione_riepilogo"
    ),
    path(
        "iscrizione/completata/",
        views.iscrizione_completata,
        name="iscrizione_completata",
    ),
]
