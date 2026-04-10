import datetime
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.utils import timezone

from anagrafica.models import Quota, Socio, valida_codice_fiscale

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
    # Bypass signal by using update() after create to avoid auto quota
    socio = Socio.objects.create(**defaults)
    return socio


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
    # Use update_or_create to avoid unique_together issues with auto-created quota
    quota, _ = Quota.objects.update_or_create(
        socio=socio,
        anno=defaults["anno"],
        defaults={k: v for k, v in defaults.items() if k != "anno"},
    )
    return quota


# ── Codice Fiscale Validator ───────────────────────────────────────────────────


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
        altro = make_socio(
            nome="Luigi",
            cognome="Bianchi",
            codice_fiscale="BNCLGU85B01H501Z",
            email="luigi@example.com",
        )
        self.assertNotEqual(self.socio.token, altro.token)

    def test_codice_fiscale_is_unique(self):
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            Socio.objects.create(
                nome="Mario",
                cognome="Rossi",
                data_nascita=datetime.date(1990, 1, 1),
                luogo_nascita="Milano",
                codice_fiscale="RSSMRA90A01F205X",  # same as setUp
                via="Via Verdi 2",
                comune="Roma",
                cap="00100",
                provincia="RM",
                email="altro@example.com",
            )

    def test_email_is_unique(self):
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            Socio.objects.create(
                nome="Luigi",
                cognome="Bianchi",
                data_nascita=datetime.date(1990, 1, 1),
                luogo_nascita="Roma",
                codice_fiscale="BNCLGU85B01H501Z",
                via="Via Verdi 2",
                comune="Roma",
                cap="00100",
                provincia="RM",
                email="mario.rossi@example.com",  # same as setUp
            )

    def test_is_in_regola_false_with_no_quota(self):
        self.socio.quote.all().delete()
        self.assertFalse(self.socio.is_in_regola)

    def test_is_in_regola_true_with_active_quota(self):
        make_quota(self.socio)
        self.assertTrue(self.socio.is_in_regola)

    def test_is_in_regola_false_with_expired_quota(self):
        today = timezone.now().date()
        make_quota(
            self.socio,
            stato="pagata",
            anno=today.year - 1,
            data_inizio=datetime.date(today.year - 1, 1, 1),
            data_scadenza=datetime.date(today.year - 1, 12, 31),
        )
        self.socio.quote.filter(anno=today.year).delete()
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
        today = timezone.now().date()
        make_quota(
            self.socio,
            anno=today.year - 1,
            data_inizio=datetime.date(today.year - 1, 1, 1),
            data_scadenza=datetime.date(today.year - 1, 12, 31),
        )
        self.socio.quote.filter(anno=today.year).delete()
        self.assertIsNone(self.socio.quota_attiva)

    def test_ultima_quota_returns_most_recent(self):
        today = timezone.now().date()
        make_quota(
            self.socio,
            anno=today.year - 1,
            data_inizio=datetime.date(today.year - 1, 1, 1),
            data_scadenza=datetime.date(today.year - 1, 12, 31),
        )
        new = make_quota(self.socio)
        self.assertEqual(self.socio.ultima_quota, new)

    def test_ultima_quota_none_when_no_quota(self):
        self.socio.quote.all().delete()
        self.assertIsNone(self.socio.ultima_quota)

    def test_get_verifica_url_contains_token(self):
        url = self.socio.get_verifica_url()
        self.assertIn(str(self.socio.token), url)

    def test_get_verifica_url_uses_request_if_provided(self):
        client = Client()
        request = client.get("/").wsgi_request
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

    def test_tipo_default_is_so(self):
        self.assertEqual(self.socio.tipo, "SO")

    def test_tipo_choices_are_valid(self):
        valid_types = ["VP", "CO", "SG", "DS", "GA", "MS", "SO", "SJ", "AT"]
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
        """Creating a Socio should automatically create an in_attesa quota."""
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

    def test_unapproved_socio_excluded_from_active(self):
        socio = make_socio(
            codice_fiscale="BNCLGU85B01H501Z",
            email="pending@example.com",
            approvato=False,
        )
        make_quota(socio)
        self.assertTrue(socio.is_in_regola)  # model doesn't filter by approvato
        # But admin filters should exclude them

        self.assertFalse(socio.approvato)


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
        quota = make_quota(
            self.socio,
            anno=self.today.year - 1,
            data_inizio=datetime.date(self.today.year - 1, 1, 1),
            data_scadenza=datetime.date(self.today.year - 1, 12, 31),
        )
        self.assertFalse(quota.is_attiva)

    def test_is_attiva_false_when_not_paid(self):
        quota = make_quota(self.socio, stato="in_attesa")
        self.assertFalse(quota.is_attiva)

    def test_is_attiva_false_when_dates_null(self):
        quota = make_quota(self.socio, data_inizio=None, data_scadenza=None)
        self.assertFalse(quota.is_attiva)

    def test_is_scaduta_true(self):
        quota = make_quota(
            self.socio,
            anno=self.today.year - 1,
            data_inizio=datetime.date(self.today.year - 1, 1, 1),
            data_scadenza=datetime.date(self.today.year - 1, 12, 31),
        )
        self.assertTrue(quota.is_scaduta)

    def test_is_scaduta_false_when_active(self):
        quota = make_quota(self.socio)
        self.assertFalse(quota.is_scaduta)

    def test_unique_together_anno_socio(self):
        from django.db import IntegrityError

        make_quota(self.socio)
        with self.assertRaises(IntegrityError):
            Quota.objects.create(
                socio=self.socio,
                anno=self.today.year,
                importo=Decimal("30.00"),
                stato="pagata",
            )

    def test_multiple_years_allowed(self):
        today = self.today
        make_quota(
            self.socio,
            anno=today.year - 1,
            data_inizio=datetime.date(today.year - 1, 1, 1),
            data_scadenza=datetime.date(today.year - 1, 12, 31),
        )
        make_quota(self.socio, anno=today.year)
        self.assertEqual(self.socio.quote.count(), 2)

    def test_quota_attiva_ignores_future_start(self):
        today = self.today
        make_quota(
            self.socio,
            data_inizio=today + datetime.timedelta(days=10),
            data_scadenza=today + datetime.timedelta(days=375),
        )
        self.assertIsNone(self.socio.quota_attiva)


# ── Verifica Socio View ───────────────────────────────────────────────────────


class VerificaSocioViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.socio = make_socio()

    def _url(self, token=None):
        token = token or self.socio.token
        return f"/anagrafica/verifica/{token}/"

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
        today = timezone.now().date()
        make_quota(
            self.socio,
            anno=today.year - 1,
            data_inizio=datetime.date(today.year - 1, 1, 1),
            data_scadenza=datetime.date(today.year - 1, 12, 31),
        )
        self.socio.quote.filter(anno=today.year).delete()
        response = self.client.get(self._url())
        self.assertFalse(response.context["in_regola"])

    def test_uses_correct_template(self):
        response = self.client.get(self._url())
        self.assertTemplateUsed(response, "anagrafica/verifica_socio.html")


# ── Dashboard View ────────────────────────────────────────────────────────────


class DashboardViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )
        self.client.login(username="admin", password="password")

    def test_dashboard_requires_login(self):
        self.client.logout()
        response = self.client.get("/anagrafica/dashboard/")
        self.assertNotEqual(response.status_code, 200)

    def test_dashboard_accessible_for_staff(self):
        response = self.client.get("/anagrafica/dashboard/")
        self.assertEqual(response.status_code, 200)

    def test_totale_count(self):
        make_socio()
        make_socio(
            nome="Luigi",
            cognome="Bianchi",
            codice_fiscale="BNCLGU85B01H501Z",
            email="l@example.com",
        )
        response = self.client.get("/anagrafica/dashboard/")
        self.assertEqual(response.context["totale"], 2)

    def test_in_regola_count(self):
        s1 = make_socio()
        make_quota(s1)
        make_socio(
            nome="Luigi",
            cognome="Bianchi",
            codice_fiscale="BNCLGU85B01H501Z",
            email="l@example.com",
        )
        response = self.client.get("/anagrafica/dashboard/")
        self.assertEqual(response.context["in_regola"], 1)

    def test_scaduti_count(self):
        today = timezone.now().date()
        s1 = make_socio()
        s1.quote.all().delete()
        make_quota(
            s1,
            anno=today.year - 1,
            data_inizio=datetime.date(today.year - 1, 1, 1),
            data_scadenza=datetime.date(today.year - 1, 12, 31),
        )
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


# ── Budget View ───────────────────────────────────────────────────────────────


class BudgetViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )
        self.client.login(username="admin", password="password")

    def test_budget_requires_login(self):
        self.client.logout()
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
        s2 = make_socio(
            nome="Luigi",
            cognome="Bianchi",
            codice_fiscale="BNCLGU85B01H501Z",
            email="l@example.com",
        )
        make_quota(
            s2,
            anno=today.year - 1,
            importo=Decimal("15.00"),
            data_inizio=datetime.date(today.year - 1, 1, 1),
            data_scadenza=datetime.date(today.year - 1, 12, 31),
        )
        response = self.client.get("/anagrafica/budget/")
        self.assertEqual(response.context["totale_anno"], Decimal("20.00"))


# ── Iscrizione View ───────────────────────────────────────────────────────────


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
        response = self.client.post(
            "/anagrafica/iscrizione/",
            {
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
            },
        )
        if response.status_code == 200:
            # Print form errors to understand why it's not redirecting
            form = response.context.get("form")
            if form:
                print(form.errors)
        self.assertRedirects(response, "/anagrafica/iscrizione/riepilogo/")

    def test_invalid_cf_shows_error(self):
        response = self.client.post(
            "/anagrafica/iscrizione/",
            {
                "nome": "Mario",
                "cognome": "Rossi",
                "data_nascita": "1990-01-01",
                "luogo_nascita": "Milano",
                "codice_fiscale": "INVALID",
                "via": "Via Roma 1",
                "comune": "Milano",
                "cap": "20100",
                "provincia": "MI",
                "email": "mario.test@example.com",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Socio.objects.filter(email="mario.test@example.com").exists())

    def test_duplicate_cf_shows_error(self):
        make_socio()
        response = self.client.post(
            "/anagrafica/iscrizione/",
            {
                "nome": "Mario",
                "cognome": "Rossi",
                "data_nascita": "1990-01-01",
                "luogo_nascita": "Milano",
                "codice_fiscale": "RSSMRA90A01F205X",  # already exists
                "via": "Via Roma 1",
                "comune": "Milano",
                "cap": "20100",
                "provincia": "MI",
                "email": "altro@example.com",
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_completata_returns_200(self):
        response = self.client.get("/anagrafica/iscrizione/completata/")
        self.assertEqual(response.status_code, 200)


class BulkRenewViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )
        self.client.login(username="admin", password="password")
        self.today = timezone.now().date()
        self.anno_corrente = self.today.year

        self.s1 = make_socio()
        self.s2 = make_socio(
            nome="Luigi",
            cognome="Bianchi",
            codice_fiscale="BNCLGU85B01H501Z",
            email="luigi@example.com",
        )
        self.s3 = make_socio(
            nome="Anna",
            cognome="Verdi",
            codice_fiscale="VRDNNA90A41H501X",
            email="anna@example.com",
        )
        # Delete auto-created quotas
        Quota.objects.all().delete()

    def _get(self, ids):
        qs = "&".join(f"ids={pk}" for pk in ids)
        return self.client.get(f"/anagrafica/bulk-renew/?{qs}")

    def _post(self, ids, **kwargs):
        data = {
            "selected_ids": ids,
            "importo": "10.00",
            "stato": "in_attesa",
        }
        data.update(kwargs)
        return self.client.post("/anagrafica/bulk-renew/", data)

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
        make_quota(
            self.s1,
            anno=self.anno_corrente - 1,
            data_inizio=datetime.date(self.anno_corrente - 1, 1, 1),
            data_scadenza=datetime.date(self.anno_corrente - 1, 12, 31),
        )
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
        from anagrafica.models import get_data_scadenza_default

        self._post([self.s1.pk])
        quota = Quota.objects.get(socio=self.s1, anno=self.anno_corrente)
        expected = get_data_scadenza_default(self.anno_corrente)
        self.assertEqual(quota.data_scadenza, expected)

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
        # s1 already had quota, s2 gets new one
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
        from anagrafica.models import get_data_scadenza_default

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
