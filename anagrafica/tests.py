import datetime
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client, TestCase
from django.utils import timezone

from anagrafica.models import (
    Quota,
    Socio,
    get_data_scadenza_default,
    valida_codice_fiscale,
)

# ── Constants ─────────────────────────────────────────────────────────────────

LUIGI = {
    "nome": "Luigi",
    "cognome": "Bianchi",
    "codice_fiscale": "BNCLGU85B01H501Z",
    "email": "luigi@example.com",
}

ANNA = {
    "nome": "Anna",
    "cognome": "Verdi",
    "codice_fiscale": "VRDNNA90A41H501X",
    "email": "anna@example.com",
}

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_socio(**kwargs):
    defaults = {
        "nome": "Mario",
        "cognome": "Rossi",
        "data_nascita": datetime.date(1990, 1, 1),
        "luogo_nascita": "Milano",
        "codice_fiscale": "RSSMRA90A01F205X",
        "via": "Via Roma 1",
        "comune": "Milano",
        "cap": "20100",
        "provincia": "MI",
        "email": "mario.rossi@example.com",
        "approvato": True,
        "tipo": "SO",
    }
    defaults.update(kwargs)
    return Socio.objects.create(**defaults)


def make_quota(socio, **kwargs):
    today = timezone.now().date()
    defaults = {
        "anno": today.year,
        "importo": Decimal("30.00"),
        "stato": "pagata",
        "data_pagamento": today,
        "data_inizio": today.replace(month=1, day=1),
        "data_scadenza": today.replace(month=12, day=31),
    }
    defaults.update(kwargs)
    quota, _ = Quota.objects.update_or_create(
        socio=socio,
        anno=defaults["anno"],
        defaults={k: v for k, v in defaults.items() if k != "anno"},
    )
    return quota


def make_expired_quota(socio, years_ago=1, **kwargs):
    today = timezone.now().date()
    year = today.year - years_ago
    return make_quota(
        socio,
        anno=year,
        data_inizio=datetime.date(year, 1, 1),
        data_scadenza=datetime.date(year, 12, 31),
        **kwargs,
    )


def _iscrizione_data(**overrides):
    data = {
        "nome": "Mario",
        "cognome": "Rossi",
        "data_nascita": "1990-01-01",
        "luogo_nascita": "Milano",
        "codice_fiscale": "RBTRST82T13F839G",
        "via": "Via Roma 1",
        "comune": "Milano",
        "cap": "20100",
        "provincia": "MI",
        "email": "mario.test@example.com",
        "consenso_marketing": False,
        "consenso_immagini": False,
    }
    data.update(overrides)
    return data


class AdminTestMixin:
    """Sets up an authenticated admin client."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.admin = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )
        self.client.login(username="admin", password="password")


# ── Codice Fiscale Validator ──────────────────────────────────────────────────


class ValidaCodiceFiscaleTests(TestCase):
    def test_valid_cf_passes(self):
        try:
            valida_codice_fiscale("RSSMRA90A01F205X")
        except ValidationError:
            self.fail("valida_codice_fiscale raised ValidationError on a valid CF")

    def test_too_short_is_rejected(self):
        with self.assertRaises(ValidationError):
            valida_codice_fiscale("RSSMRA90A01")

    def test_too_long_is_rejected(self):
        with self.assertRaises(ValidationError):
            valida_codice_fiscale("RSSMRA90A01F205XX")

    def test_wrong_format_is_rejected(self):
        with self.assertRaises(ValidationError):
            valida_codice_fiscale("123456789012345A")

    def test_empty_string_is_rejected(self):
        with self.assertRaises(ValidationError):
            valida_codice_fiscale("")


# ── Socio Model ───────────────────────────────────────────────────────────────


class SocioModelTests(TestCase):
    def setUp(self):
        self.socio = make_socio()

    def test_str_returns_cognome_nome(self):
        self.assertEqual(str(self.socio), "Rossi Mario")

    def test_nome_completo_property(self):
        self.assertEqual(self.socio.nome_completo, "Mario Rossi")

    def test_token_is_auto_generated(self):
        self.assertIsNotNone(self.socio.token)
        self.assertIsInstance(self.socio.token, uuid.UUID)

    def test_token_is_unique_per_socio(self):
        altro = make_socio(**LUIGI)
        self.assertNotEqual(self.socio.token, altro.token)

    def test_codice_fiscale_is_unique(self):
        with self.assertRaises(IntegrityError):
            make_socio(email="altro@example.com")

    def test_email_is_unique(self):
        with self.assertRaises(IntegrityError):
            make_socio(
                codice_fiscale="BNCLGU85B01H501Z",
                email="mario.rossi@example.com",
            )

    def test_is_in_regola_false_with_no_quota(self):
        self.socio.quote.all().delete()
        self.assertFalse(self.socio.is_in_regola)

    def test_is_in_regola_true_with_active_quota(self):
        make_quota(self.socio)
        self.assertTrue(self.socio.is_in_regola)

    def test_is_in_regola_false_with_expired_quota(self):
        make_expired_quota(self.socio)
        self.socio.quote.filter(anno=timezone.now().year).delete()
        self.assertFalse(self.socio.is_in_regola)

    def test_is_in_regola_false_with_pending_quota(self):
        make_quota(self.socio, stato="in_attesa")
        self.assertFalse(self.socio.is_in_regola)

    def test_is_in_regola_false_with_cancelled_quota(self):
        make_quota(self.socio, stato="annullata")
        self.assertFalse(self.socio.is_in_regola)

    def test_quota_attiva_returns_correct_quota(self):
        quota = make_quota(self.socio)
        self.assertEqual(self.socio.quota_attiva, quota)

    def test_quota_attiva_returns_none_when_expired(self):
        make_expired_quota(self.socio)
        self.socio.quote.filter(anno=timezone.now().year).delete()
        self.assertIsNone(self.socio.quota_attiva)

    def test_ultima_quota_returns_most_recent(self):
        make_expired_quota(self.socio)
        new = make_quota(self.socio)
        self.assertEqual(self.socio.ultima_quota, new)

    def test_ultima_quota_none_when_no_quota(self):
        self.socio.quote.all().delete()
        self.assertIsNone(self.socio.ultima_quota)

    def test_get_verifica_url_contains_token(self):
        url = self.socio.get_verifica_url()
        self.assertIn(str(self.socio.token), url)

    def test_get_verifica_url_uses_request_if_provided(self):
        request = Client().get("/").wsgi_request
        url = self.socio.get_verifica_url(request=request)
        self.assertIn(str(self.socio.token), url)
        self.assertTrue(url.startswith("http"))

    def test_genera_qr_code_creates_image(self):
        self.socio.genera_qr_code()
        self.assertTrue(bool(self.socio.qr_code))

    def test_ordering_is_cognome_nome(self):
        Socio.objects.all().delete()
        make_socio(
            nome="Zara",
            cognome="Verdi",
            codice_fiscale="VRDZRA90A01H501X",
            email="z@example.com",
        )
        make_socio(
            nome="Anna",
            cognome="Bianchi",
            codice_fiscale="BNCNNA90A41H501X",
            email="a@example.com",
        )
        make_socio(
            nome="Carlo",
            cognome="Bianchi",
            codice_fiscale="BNCCRL90A01H501X",
            email="c@example.com",
        )
        soci = list(Socio.objects.all())
        self.assertEqual(soci[0].cognome, "Bianchi")
        self.assertEqual(soci[0].nome, "Anna")
        self.assertEqual(soci[1].nome, "Carlo")
        self.assertEqual(soci[2].cognome, "Verdi")

    def test_approvato_default_is_true(self):
        self.assertTrue(self.socio.approvato)

    def test_consenso_marketing_default_is_false(self):
        self.assertFalse(self.socio.consenso_marketing)

    def test_consenso_immagini_default_is_false(self):
        self.assertFalse(self.socio.consenso_immagini)

    def test_tipo_default_is_ss(self):
        socio = Socio.objects.create(
            nome="Test",
            cognome="Default",
            data_nascita=datetime.date(1990, 1, 1),
            luogo_nascita="Roma",
            codice_fiscale="DFLTST90A01H501X",
            via="Via Test 1",
            comune="Roma",
            cap="00100",
            provincia="RM",
            email="default@example.com",
        )
        self.assertEqual(socio.tipo, "SS")

    def test_tipo_choices_are_valid(self):
        valid_types = ["SS", "SV", "VP", "PS", "CO", "SG", "TE"]
        for tipo in valid_types:
            self.socio.tipo = tipo
            self.socio.save()
            self.socio.refresh_from_db()
            self.assertEqual(self.socio.tipo, tipo)

    def test_via_comune_cap_provincia_stored(self):
        self.assertEqual(self.socio.via, "Via Roma 1")
        self.assertEqual(self.socio.comune, "Milano")
        self.assertEqual(self.socio.cap, "20100")
        self.assertEqual(self.socio.provincia, "MI")

    def test_signal_creates_initial_quota(self):
        socio = Socio.objects.create(
            nome="Test",
            cognome="Signal",
            data_nascita=datetime.date(1990, 1, 1),
            luogo_nascita="Roma",
            codice_fiscale="SGNLTS90A01H501X",
            via="Via Test 1",
            comune="Roma",
            cap="00100",
            provincia="RM",
            email="signal@example.com",
        )
        self.assertEqual(socio.quote.count(), 1)
        quota = socio.quote.first()
        self.assertEqual(quota.stato, "in_attesa")
        self.assertEqual(quota.importo, Decimal("5"))
        self.assertEqual(quota.anno, timezone.now().year)
        self.assertEqual(quota.data_inizio, timezone.now().date().replace(day=1))
        self.assertEqual(
            quota.data_scadenza, get_data_scadenza_default(timezone.now().year)
        )

    def test_signal_does_not_create_quota_on_update(self):
        self.socio.quote.all().delete()
        self.socio.nome = "Updated"
        self.socio.save()
        self.assertEqual(self.socio.quote.count(), 0)

    def test_unapproved_socio_excluded_from_active(self):
        socio = make_socio(**LUIGI, approvato=False)
        make_quota(socio)
        self.assertTrue(socio.is_in_regola)
        self.assertFalse(socio.approvato)

    def test_save_normalizes_nome_cognome(self):
        socio = make_socio(
            nome="  mario ",
            cognome="  rossi ",
            codice_fiscale="NRMLZZ90A01H501X",
            email="norm@example.com",
        )
        self.assertEqual(socio.nome, "Mario")
        self.assertEqual(socio.cognome, "Rossi")


# ── Quota Model ───────────────────────────────────────────────────────────────


class QuotaModelTests(TestCase):
    def setUp(self):
        self.socio = make_socio()
        self.today = timezone.now().date()

    def test_str(self):
        quota = make_quota(self.socio)
        self.assertIn("Rossi Mario", str(quota))
        self.assertIn(str(self.today.year), str(quota))

    def test_is_attiva_true(self):
        quota = make_quota(self.socio)
        self.assertTrue(quota.is_attiva)

    def test_is_attiva_false_when_expired(self):
        quota = make_expired_quota(self.socio)
        self.assertFalse(quota.is_attiva)

    def test_is_attiva_false_when_not_paid(self):
        quota = make_quota(self.socio, stato="in_attesa")
        self.assertFalse(quota.is_attiva)

    def test_is_attiva_false_when_dates_null(self):
        quota = make_quota(self.socio, data_inizio=None, data_scadenza=None)
        self.assertFalse(quota.is_attiva)

    def test_is_scaduta_true(self):
        quota = make_expired_quota(self.socio)
        self.assertTrue(quota.is_scaduta)

    def test_is_scaduta_false_when_active(self):
        quota = make_quota(self.socio)
        self.assertFalse(quota.is_scaduta)

    def test_unique_together_anno_socio(self):
        make_quota(self.socio)
        with self.assertRaises(IntegrityError):
            Quota.objects.create(
                socio=self.socio,
                anno=self.today.year,
                importo=Decimal("30.00"),
                stato="pagata",
            )

    def test_multiple_years_allowed(self):
        make_expired_quota(self.socio)
        make_quota(self.socio, anno=self.today.year)
        self.assertEqual(self.socio.quote.count(), 2)

    def test_quota_attiva_ignores_future_start(self):
        today = self.today
        make_quota(
            self.socio,
            data_inizio=today + datetime.timedelta(days=10),
            data_scadenza=today + datetime.timedelta(days=375),
        )
        self.assertIsNone(self.socio.quota_attiva)

    def test_is_scaduta_false_when_data_scadenza_null(self):
        quota = make_quota(self.socio, data_scadenza=None)
        self.assertFalse(quota.is_scaduta)

    def test_str_includes_stato_display(self):
        quota = make_quota(self.socio, stato="in_attesa")
        self.assertIn("In attesa", str(quota))

    def test_ordering_is_descending_anno(self):
        make_expired_quota(self.socio)
        make_quota(self.socio, anno=self.today.year)
        quote = list(self.socio.quote.all())
        self.assertGreater(quote[0].anno, quote[1].anno)

    def test_clean_rejects_duplicate_anno_socio(self):
        make_quota(self.socio)
        duplicate = Quota(
            socio=self.socio,
            anno=self.today.year,
            importo=Decimal("30.00"),
            stato="pagata",
        )
        with self.assertRaises(ValidationError):
            duplicate.clean()

    def test_clean_rejects_data_pagamento_before_created_month(self):
        created = self.socio.created_at.date()
        # Previous month is always invalid
        earlier = (created.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
        quota = make_quota(self.socio, data_pagamento=earlier)
        with self.assertRaises(ValidationError) as ctx:
            quota.clean()
        self.assertIn("data_pagamento", ctx.exception.message_dict)

    def test_clean_rejects_data_inizio_before_created_month(self):
        created = self.socio.created_at.date()
        earlier = (created.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
        quota = make_quota(self.socio, data_inizio=earlier)
        with self.assertRaises(ValidationError) as ctx:
            quota.clean()
        self.assertIn("data_inizio", ctx.exception.message_dict)

    def test_clean_accepts_same_month_different_day(self):
        created = self.socio.created_at.date()
        # First day of same month — always valid even if before created day
        first = created.replace(day=1)
        quota = make_quota(self.socio, data_pagamento=first, data_inizio=first)
        try:
            quota.clean()
        except ValidationError:
            self.fail(
                "clean() raised ValidationError for same month/year as created_at"
            )


# ── Verifica Socio View ──────────────────────────────────────────────────────


class VerificaSocioViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.socio = make_socio()

    def _url(self, token=None):
        return f"/anagrafica/verifica/{token or self.socio.token}/"

    def test_valid_token_returns_200(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200)

    def test_invalid_token_returns_404(self):
        response = self.client.get(self._url(token=uuid.uuid4()))
        self.assertEqual(response.status_code, 404)

    def test_context_contains_socio(self):
        response = self.client.get(self._url())
        self.assertEqual(response.context["socio"], self.socio)

    def test_context_in_regola_false_without_active_quota(self):
        self.socio.quote.all().delete()
        response = self.client.get(self._url())
        self.assertFalse(response.context["in_regola"])

    def test_context_in_regola_true_with_active_quota(self):
        make_quota(self.socio)
        response = self.client.get(self._url())
        self.assertTrue(response.context["in_regola"])

    def test_context_quota_is_none_without_active_quota(self):
        self.socio.quote.all().delete()
        response = self.client.get(self._url())
        self.assertIsNone(response.context["quota"])

    def test_context_ultima_quota_present(self):
        quota = make_quota(self.socio)
        response = self.client.get(self._url())
        self.assertEqual(response.context["ultima_quota"], quota)

    def test_expired_quota_shows_not_in_regola(self):
        make_expired_quota(self.socio)
        self.socio.quote.filter(anno=timezone.now().year).delete()
        response = self.client.get(self._url())
        self.assertFalse(response.context["in_regola"])

    def test_uses_correct_template(self):
        response = self.client.get(self._url())
        self.assertTemplateUsed(response, "anagrafica/verifica_socio.html")

    def test_in_attesa_quota_shows_correct_state(self):
        self.socio.quote.all().delete()
        make_quota(self.socio, stato="in_attesa", data_pagamento=None)
        response = self.client.get(self._url())
        self.assertFalse(response.context["in_regola"])
        self.assertContains(response, "In attesa di pagamento")
        self.assertNotContains(response, "Quota scaduta")


# ── Dashboard View ────────────────────────────────────────────────────────────


class DashboardViewTests(AdminTestMixin, TestCase):
    def test_dashboard_requires_login(self):
        self.client.logout()
        response = self.client.get("/anagrafica/dashboard/")
        self.assertNotEqual(response.status_code, 200)

    def test_dashboard_denied_for_non_staff(self):
        self.client.logout()
        User.objects.create_user("user", "user@example.com", "password")
        self.client.login(username="user", password="password")
        response = self.client.get("/anagrafica/dashboard/")
        self.assertNotEqual(response.status_code, 200)

    def test_dashboard_accessible_for_staff(self):
        response = self.client.get("/anagrafica/dashboard/")
        self.assertEqual(response.status_code, 200)

    def test_totale_count(self):
        make_socio()
        make_socio(**LUIGI)
        response = self.client.get("/anagrafica/dashboard/")
        self.assertEqual(response.context["totale"], 2)

    def test_in_regola_count(self):
        s1 = make_socio()
        make_quota(s1)
        make_socio(**LUIGI)
        response = self.client.get("/anagrafica/dashboard/")
        self.assertEqual(response.context["in_regola"], 1)

    def test_scaduti_count(self):
        s1 = make_socio()
        s1.quote.all().delete()
        make_expired_quota(s1)
        response = self.client.get("/anagrafica/dashboard/")
        self.assertEqual(response.context["scaduti"], 1)

    def test_senza_quota_count(self):
        s = make_socio()
        s.quote.all().delete()
        response = self.client.get("/anagrafica/dashboard/")
        self.assertEqual(response.context["nessuna_quota"], 1)

    def test_in_scadenza_count(self):
        today = timezone.now().date()
        s = make_socio()
        make_quota(
            s,
            data_inizio=today - datetime.timedelta(days=340),
            data_scadenza=today + datetime.timedelta(days=15),
        )
        response = self.client.get("/anagrafica/dashboard/")
        self.assertEqual(response.context["in_scadenza"], 1)

    def test_quota_expiring_after_30_days_not_in_in_scadenza(self):
        today = timezone.now().date()
        s = make_socio()
        make_quota(
            s,
            data_inizio=today - datetime.timedelta(days=300),
            data_scadenza=today + datetime.timedelta(days=60),
        )
        response = self.client.get("/anagrafica/dashboard/")
        self.assertEqual(response.context["in_scadenza"], 0)

    def test_socio_with_null_scadenza_excluded_from_all_counts(self):
        s = make_socio()
        s.quote.all().delete()
        make_quota(s, stato="pagata", data_scadenza=None, data_inizio=None)
        response = self.client.get("/anagrafica/dashboard/")
        # Has a quota but data_scadenza is null → not in_regola, not scaduti, not senza_quota
        self.assertEqual(response.context["in_regola"], 0)
        self.assertEqual(response.context["scaduti"], 0)
        self.assertEqual(response.context["nessuna_quota"], 0)

    def test_empty_dashboard(self):
        response = self.client.get("/anagrafica/dashboard/")
        self.assertEqual(response.context["totale"], 0)
        self.assertEqual(response.context["in_regola"], 0)
        self.assertEqual(response.context["scaduti"], 0)
        self.assertEqual(response.context["nessuna_quota"], 0)
        self.assertEqual(response.context["in_scadenza"], 0)


# ── Budget View ───────────────────────────────────────────────────────────────


class BudgetViewTests(AdminTestMixin, TestCase):
    def test_budget_requires_login(self):
        self.client.logout()
        response = self.client.get("/anagrafica/budget/")
        self.assertNotEqual(response.status_code, 200)

    def test_budget_denied_for_non_staff(self):
        self.client.logout()
        User.objects.create_user("user", "user@example.com", "password")
        self.client.login(username="user", password="password")
        response = self.client.get("/anagrafica/budget/")
        self.assertNotEqual(response.status_code, 200)

    def test_budget_accessible_for_staff(self):
        response = self.client.get("/anagrafica/budget/")
        self.assertEqual(response.status_code, 200)

    def test_totale_incassato(self):
        s = make_socio()
        make_quota(s, importo=Decimal("20.00"))
        response = self.client.get("/anagrafica/budget/")
        self.assertEqual(response.context["totale_incassato"], Decimal("20.00"))

    def test_totale_attesa(self):
        s = make_socio()
        make_quota(s, stato="in_attesa", importo=Decimal("10.00"))
        response = self.client.get("/anagrafica/budget/")
        self.assertEqual(response.context["totale_attesa"], Decimal("10.00"))

    def test_totale_anno_only_current_year(self):
        today = timezone.now().date()
        s = make_socio()
        make_quota(s, importo=Decimal("20.00"), anno=today.year)
        s2 = make_socio(**LUIGI)
        make_expired_quota(s2, importo=Decimal("15.00"))
        response = self.client.get("/anagrafica/budget/")
        self.assertEqual(response.context["totale_anno"], Decimal("20.00"))

    def test_empty_budget_returns_zeros(self):
        response = self.client.get("/anagrafica/budget/")
        self.assertEqual(response.context["totale_incassato"], 0)
        self.assertEqual(response.context["totale_anno"], 0)
        self.assertEqual(response.context["totale_attesa"], 0)
        self.assertEqual(response.context["media_quota"], 0)

    def test_media_quota(self):
        s1 = make_socio()
        make_quota(s1, importo=Decimal("10.00"))
        s2 = make_socio(**LUIGI)
        make_quota(s2, importo=Decimal("30.00"))
        response = self.client.get("/anagrafica/budget/")
        self.assertEqual(response.context["media_quota"], Decimal("20.00"))


# ── Iscrizione View ──────────────────────────────────────────────────────────


class IscrizioneViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_get_returns_200(self):
        response = self.client.get("/anagrafica/iscrizione/")
        self.assertEqual(response.status_code, 200)

    def test_uses_correct_template(self):
        response = self.client.get("/anagrafica/iscrizione/")
        self.assertTemplateUsed(response, "anagrafica/iscrizione.html")

    def test_valid_post_redirects_to_riepilogo(self):
        response = self.client.post("/anagrafica/iscrizione/", _iscrizione_data())
        if response.status_code == 200:
            form = response.context.get("form")
            if form:
                print(form.errors)
        self.assertRedirects(response, "/anagrafica/iscrizione/riepilogo/")

    def test_invalid_cf_shows_error(self):
        response = self.client.post(
            "/anagrafica/iscrizione/",
            _iscrizione_data(codice_fiscale="INVALID"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Socio.objects.filter(email="mario.test@example.com").exists())

    def test_duplicate_cf_shows_error(self):
        make_socio()
        response = self.client.post(
            "/anagrafica/iscrizione/",
            _iscrizione_data(
                codice_fiscale="RSSMRA90A01F205X",
                email="altro@example.com",
            ),
        )
        self.assertEqual(response.status_code, 200)

    def test_duplicate_email_shows_error(self):
        make_socio()
        response = self.client.post(
            "/anagrafica/iscrizione/",
            _iscrizione_data(email="mario.rossi@example.com"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Socio.objects.filter(email="mario.rossi@example.com").count(), 1
        )

    def test_completata_returns_200(self):
        response = self.client.get("/anagrafica/iscrizione/completata/")
        self.assertEqual(response.status_code, 200)

    def test_minor_without_tutore_shows_errors(self):
        today = datetime.date.today()
        minor_dob = today.replace(year=today.year - 10)
        response = self.client.post(
            "/anagrafica/iscrizione/",
            _iscrizione_data(data_nascita=minor_dob.isoformat()),
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        for field in [
            "tutore_nome",
            "tutore_cognome",
            "tutore_codice_fiscale",
            "tutore_email",
            "tutore_residenza",
        ]:
            self.assertIn(field, form.errors)

    def test_cf_with_wrong_checksum_shows_error(self):
        # Valid format but wrong check digit (last char)
        response = self.client.post(
            "/anagrafica/iscrizione/",
            _iscrizione_data(codice_fiscale="RBTRST82T13F839A"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("codice_fiscale", response.context["form"].errors)


# ── Bulk Renew View ──────────────────────────────────────────────────────────


class BulkRenewViewTests(AdminTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.now().date()
        self.anno_corrente = self.today.year
        self.s1 = make_socio()
        self.s2 = make_socio(**LUIGI)
        self.s3 = make_socio(**ANNA)
        Quota.objects.all().delete()

    def _get(self, ids):
        qs = "&".join(f"ids={pk}" for pk in ids)
        return self.client.get(f"/anagrafica/bulk-renew/?{qs}")

    def _post(self, ids, follow=False, **kwargs):
        data = {"selected_ids": ids, "importo": "10.00", "stato": "in_attesa"}
        data.update(kwargs)
        return self.client.post("/anagrafica/bulk-renew/", data, follow=follow)

    def test_get_shows_confirmation_page(self):
        response = self._get([self.s1.pk, self.s2.pk])
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/anagrafica/bulk_renew.html")

    def test_get_shows_all_soci_as_eligibili_when_no_quotas(self):
        response = self._get([self.s1.pk, self.s2.pk])
        self.assertIn(self.s1, response.context["eligibili"])
        self.assertIn(self.s2, response.context["eligibili"])
        self.assertEqual(len(response.context["non_eligibili"]), 0)

    def test_socio_with_current_year_quota_is_not_eligibile(self):
        make_quota(self.s1, anno=self.anno_corrente)
        response = self._get([self.s1.pk, self.s2.pk])
        self.assertIn(self.s1, response.context["non_eligibili"])
        self.assertIn(self.s2, response.context["eligibili"])

    def test_socio_with_previous_year_quota_is_eligibile(self):
        make_expired_quota(self.s1)
        response = self._get([self.s1.pk])
        self.assertIn(self.s1, response.context["eligibili"])

    def test_post_creates_quota_for_eligibili(self):
        self._post([self.s1.pk, self.s2.pk])
        self.assertEqual(Quota.objects.filter(anno=self.anno_corrente).count(), 2)

    def test_post_sets_correct_anno(self):
        self._post([self.s1.pk])
        quota = Quota.objects.get(socio=self.s1, anno=self.anno_corrente)
        self.assertEqual(quota.anno, self.anno_corrente)

    def test_post_sets_data_inizio_to_today(self):
        self._post([self.s1.pk])
        quota = Quota.objects.get(socio=self.s1, anno=self.anno_corrente)
        self.assertEqual(quota.data_inizio, self.today)

    def test_post_sets_data_scadenza_from_config(self):
        self._post([self.s1.pk])
        quota = Quota.objects.get(socio=self.s1, anno=self.anno_corrente)
        self.assertEqual(
            quota.data_scadenza, get_data_scadenza_default(self.anno_corrente)
        )

    def test_post_sets_importo(self):
        self._post([self.s1.pk], importo="15.00")
        quota = Quota.objects.get(socio=self.s1, anno=self.anno_corrente)
        self.assertEqual(quota.importo, Decimal("15.00"))

    def test_post_sets_stato(self):
        self._post([self.s1.pk], stato="pagata")
        quota = Quota.objects.get(socio=self.s1, anno=self.anno_corrente)
        self.assertEqual(quota.stato, "pagata")

    def test_post_skips_non_eligibili(self):
        make_quota(self.s1, anno=self.anno_corrente)
        self._post([self.s1.pk, self.s2.pk])
        self.assertEqual(
            Quota.objects.filter(socio=self.s1, anno=self.anno_corrente).count(), 1
        )
        self.assertEqual(
            Quota.objects.filter(socio=self.s2, anno=self.anno_corrente).count(), 1
        )

    def test_post_redirects_to_changelist(self):
        response = self._post([self.s1.pk])
        self.assertRedirects(response, "/admin/anagrafica/socio/")

    def test_post_requires_login(self):
        self.client.logout()
        response = self._post([self.s1.pk])
        self.assertNotEqual(response.status_code, 200)

    def test_post_denied_for_non_staff(self):
        self.client.logout()
        User.objects.create_user("user", "user@example.com", "password")
        self.client.login(username="user", password="password")
        response = self._post([self.s1.pk])
        self.assertNotEqual(response.status_code, 200)

    def test_post_sets_success_message(self):
        response = self._post([self.s1.pk], follow=True)
        msgs = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("1 soci" in m for m in msgs))

    def test_post_sets_warning_for_non_eligibili(self):
        make_quota(self.s1, anno=self.anno_corrente)
        response = self._post([self.s1.pk, self.s2.pk], follow=True)
        msgs = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("Già rinnovati" in m for m in msgs))

    def test_all_non_eligibili_shows_empty_form(self):
        make_quota(self.s1, anno=self.anno_corrente)
        make_quota(self.s2, anno=self.anno_corrente)
        response = self._get([self.s1.pk, self.s2.pk])
        self.assertEqual(len(response.context["eligibili"]), 0)
        self.assertEqual(len(response.context["non_eligibili"]), 2)

    def test_context_contains_correct_anno(self):
        response = self._get([self.s1.pk])
        self.assertEqual(response.context["anno_corrente"], self.anno_corrente)

    def test_context_contains_data_scadenza(self):
        response = self._get([self.s1.pk])
        self.assertEqual(
            response.context["data_scadenza"],
            get_data_scadenza_default(self.anno_corrente),
        )

    def test_multiple_soci_partial_eligibili(self):
        make_quota(self.s1, anno=self.anno_corrente)
        response = self._get([self.s1.pk, self.s2.pk, self.s3.pk])
        self.assertEqual(len(response.context["eligibili"]), 2)
        self.assertEqual(len(response.context["non_eligibili"]), 1)
        self.assertIn(self.s2, response.context["eligibili"])
        self.assertIn(self.s3, response.context["eligibili"])
        self.assertIn(self.s1, response.context["non_eligibili"])

    def test_get_with_empty_ids(self):
        response = self._get([])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["eligibili"]), 0)

    def test_post_all_non_eligibili_creates_nothing(self):
        make_quota(self.s1, anno=self.anno_corrente)
        make_quota(self.s2, anno=self.anno_corrente)
        before = Quota.objects.count()
        self._post([self.s1.pk, self.s2.pk])
        self.assertEqual(Quota.objects.count(), before)


# ── get_data_scadenza_default ─────────────────────────────────────────────────


class GetDataScadenzaDefaultTests(TestCase):
    def test_returns_date_from_config(self):
        result = get_data_scadenza_default(2026)
        # Default config: month=3, day=31 → 2027-03-31
        self.assertEqual(result, datetime.date(2027, 3, 31))

    def test_fallback_on_invalid_date(self):
        from configurazione.models import ConfigurazioneAnnuale

        config_anno = ConfigurazioneAnnuale.get(2026)
        config_anno.scadenza_quota_giorno = 31
        config_anno.scadenza_quota_mese = 2  # Feb 31 doesn't exist
        config_anno.save()
        result = get_data_scadenza_default(2026)
        self.assertEqual(result, datetime.date(2027, 3, 31))


# ── Iscrizione Riepilogo View ─────────────────────────────────────────────────


class IscrizioneRiepilogoViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.session_data = {
            "nome": "Mario",
            "cognome": "Rossi",
            "data_nascita": "1990-01-01",
            "luogo_nascita": "Milano",
            "codice_fiscale": "RBTRST82T13F839G",
            "via": "Via Roma 1",
            "comune": "Milano",
            "cap": "20100",
            "provincia": "MI",
            "email": "riepilogo@example.com",
            "telefono": "",
            "consenso_marketing": False,
            "consenso_immagini": False,
            "tutore_nome": "",
            "tutore_cognome": "",
            "tutore_codice_fiscale": "",
            "tutore_email": "",
            "tutore_telefono": "",
            "tutore_residenza": "",
        }

    def _set_session(self):
        # Force session creation via a GET, then inject data
        self.client.get("/anagrafica/iscrizione/")
        session = self.client.session
        session["iscrizione_data"] = self.session_data
        session.save()

    def test_redirects_without_session_data(self):
        response = self.client.get("/anagrafica/iscrizione/riepilogo/")
        self.assertRedirects(response, "/anagrafica/iscrizione/")

    def test_get_renders_with_session_data(self):
        self._set_session()
        response = self.client.get("/anagrafica/iscrizione/riepilogo/")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "anagrafica/iscrizione_riepilogo.html")

    def test_post_missing_firma_shows_error(self):
        self._set_session()
        response = self.client.post(
            "/anagrafica/iscrizione/riepilogo/",
            {
                "consenso_trattamento": "True",
                "firma": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["error_firma"])

    def test_post_missing_consenso_shows_error(self):
        self._set_session()
        response = self.client.post(
            "/anagrafica/iscrizione/riepilogo/",
            {
                "consenso_trattamento": "False",
                "firma": "data:image/png;base64,abc",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["error_trattamento"])

    @patch("anagrafica.views.invia_email_iscrizione")
    def test_valid_post_creates_socio_and_redirects(self, mock_email):
        self._set_session()
        response = self.client.post(
            "/anagrafica/iscrizione/riepilogo/",
            {
                "consenso_trattamento": "True",
                "firma": "data:image/png;base64,abc",
                "consenso_marketing": "True",
                "consenso_immagini": "False",
            },
        )
        self.assertRedirects(response, "/anagrafica/iscrizione/completata/")
        socio = Socio.objects.get(email="riepilogo@example.com")
        self.assertTrue(socio.approvato)
        self.assertEqual(socio.firma, "data:image/png;base64,abc")
        self.assertTrue(socio.consenso_marketing)
        self.assertFalse(socio.consenso_immagini)
        self.assertTrue(bool(socio.qr_code))
        mock_email.assert_called_once()

    @patch("anagrafica.views.invia_email_iscrizione")
    def test_valid_post_creates_initial_quota(self, mock_email):
        self._set_session()
        self.client.post(
            "/anagrafica/iscrizione/riepilogo/",
            {
                "consenso_trattamento": "True",
                "firma": "data:image/png;base64,abc",
            },
        )
        socio = Socio.objects.get(email="riepilogo@example.com")
        self.assertEqual(socio.quote.count(), 1)
        quota = socio.quote.first()
        self.assertEqual(quota.stato, "in_attesa")

    @patch("anagrafica.views.invia_email_iscrizione")
    def test_valid_post_clears_session(self, mock_email):
        self._set_session()
        self.client.post(
            "/anagrafica/iscrizione/riepilogo/",
            {
                "consenso_trattamento": "True",
                "firma": "data:image/png;base64,abc",
            },
        )
        session = self.client.session
        self.assertNotIn("iscrizione_data", session)

    def test_post_missing_both_firma_and_consenso(self):
        self._set_session()
        response = self.client.post(
            "/anagrafica/iscrizione/riepilogo/",
            {"consenso_trattamento": "False", "firma": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["error_firma"])
        self.assertTrue(response.context["error_trattamento"])

    def test_post_without_session_redirects(self):
        response = self.client.post(
            "/anagrafica/iscrizione/riepilogo/",
            {"consenso_trattamento": "True", "firma": "data:image/png;base64,abc"},
        )
        self.assertRedirects(response, "/anagrafica/iscrizione/")


# ── Rigenera QR Codes Action ──────────────────────────────────────────────────


class RigeneraQrCodesActionTests(AdminTestMixin, TestCase):
    def test_rigenera_qr_codes(self):
        socio = make_socio()
        socio.genera_qr_code()
        socio.save(update_fields=["qr_code"])

        response = self.client.post(
            "/admin/anagrafica/socio/",
            {"action": "rigenera_qr_codes", "_selected_action": [socio.pk]},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        socio.refresh_from_db()
        self.assertTrue(socio.qr_code)
        msg = str(list(response.context["messages"])[0])
        self.assertIn("QR rigenerati: 1", msg)

    @patch("anagrafica.email_utils.invia_tessera")
    def test_rigenera_sends_tessera_email(self, mock_invia):
        socio = make_socio()
        make_quota(socio)
        socio.genera_qr_code()
        socio.save(update_fields=["qr_code"])

        response = self.client.post(
            "/admin/anagrafica/socio/",
            {"action": "rigenera_qr_codes", "_selected_action": [socio.pk]},
            follow=True,
        )
        mock_invia.assert_called_once()
        self.assertEqual(mock_invia.call_args.kwargs["motivo"], "aggiornamento_qr")
        msg = str(list(response.context["messages"])[0])
        self.assertIn("Tessere inviate: 1", msg)
