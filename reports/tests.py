import datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError
from django.test import Client, TestCase

from anagrafica.models import Quota
from anagrafica.tests import LUIGI, make_socio
from reports.models import Newsletter, Verbale


def _make_quota(socio, anno, mese):
    Quota.objects.filter(socio=socio, anno=anno).delete()
    return Quota.objects.create(
        socio=socio,
        anno=anno,
        importo=Decimal("10.00"),
        stato="pagata",
        data_inizio=datetime.date(anno, mese, 1),
        data_scadenza=datetime.date(anno, 12, 31),
        data_pagamento=datetime.date(anno, mese, 1),
    )


class VerbaleModelTests(TestCase):
    def test_auto_assigns_numero_progressivo(self):
        v = Verbale(data=datetime.date(2026, 3, 15))
        v.save()
        self.assertEqual(v.numero_progressivo, 1)

    def test_increments_within_same_year(self):
        Verbale.objects.create(data=datetime.date(2026, 1, 10))
        v2 = Verbale.objects.create(data=datetime.date(2026, 6, 20))
        self.assertEqual(v2.numero_progressivo, 2)

    def test_resets_for_new_year(self):
        Verbale.objects.create(data=datetime.date(2025, 5, 1))
        v = Verbale.objects.create(data=datetime.date(2026, 1, 1))
        self.assertEqual(v.numero_progressivo, 1)

    def test_unique_constraint_per_year(self):
        Verbale.objects.create(data=datetime.date(2026, 1, 1))
        with self.assertRaises(IntegrityError):
            Verbale(data=datetime.date(2026, 6, 1), numero_progressivo=1).save()

    def test_same_numero_different_years_allowed(self):
        v1 = Verbale.objects.create(data=datetime.date(2025, 1, 1))
        v2 = Verbale.objects.create(data=datetime.date(2026, 1, 1))
        self.assertEqual(v1.numero_progressivo, 1)
        self.assertEqual(v2.numero_progressivo, 1)

    def test_str(self):
        v = Verbale.objects.create(data=datetime.date(2026, 4, 14))
        self.assertEqual(str(v), "Verbale n.1/2026 del 14/04/2026")

    def test_ordering(self):
        v1 = Verbale.objects.create(data=datetime.date(2026, 1, 1))
        v2 = Verbale.objects.create(data=datetime.date(2026, 6, 1))
        self.assertEqual(list(Verbale.objects.all()), [v2, v1])

    def test_popola_consiglio_direttivo(self):
        from configurazione.models import ConfigurazioneAnnuale

        s1 = make_socio()
        s2 = make_socio(**LUIGI)
        ca = ConfigurazioneAnnuale.get(2026)
        ca.consiglio_direttivo.set([s1, s2])

        v = Verbale.objects.create(data=datetime.date(2026, 1, 1))
        for name in ["Mario Rossi", "Luigi Bianchi"]:
            self.assertIn(name, v.consiglio_direttivo)


class AssegnaSociTests(TestCase):
    def setUp(self):
        self.s1 = make_socio()
        self.s2 = make_socio(**LUIGI)
        Quota.objects.all().delete()

    def test_assigns_soci_with_data_inizio_before_date(self):
        _make_quota(self.s1, 2026, 1)  # data_inizio Jan
        _make_quota(self.s2, 2026, 5)  # data_inizio May
        v = Verbale.objects.create(data=datetime.date(2026, 4, 30))
        v.assegna_soci()
        self.assertIn(self.s1, v.soci.all())  # Jan <= Apr
        self.assertNotIn(self.s2, v.soci.all())  # May > Apr

    def test_includes_data_inizio_on_same_day(self):
        _make_quota(self.s1, 2026, 4)  # data_inizio Apr 1
        v = Verbale.objects.create(data=datetime.date(2026, 4, 1))
        v.assegna_soci()
        self.assertIn(self.s1, v.soci.all())

    def test_excludes_socio_already_in_another_verbale(self):
        _make_quota(self.s1, 2026, 1)
        v1 = Verbale.objects.create(data=datetime.date(2026, 1, 31))
        v1.assegna_soci()
        self.assertIn(self.s1, v1.soci.all())

        _make_quota(self.s2, 2026, 2)
        v2 = Verbale.objects.create(data=datetime.date(2026, 2, 28))
        v2.assegna_soci()
        self.assertNotIn(self.s1, v2.soci.all())  # already in v1
        self.assertIn(self.s2, v2.soci.all())

    def test_socio_can_appear_in_different_years(self):
        _make_quota(self.s1, 2025, 1)
        _make_quota(self.s1, 2026, 1)
        v1 = Verbale.objects.create(data=datetime.date(2025, 1, 31))
        v1.assegna_soci()
        v2 = Verbale.objects.create(data=datetime.date(2026, 1, 31))
        v2.assegna_soci()
        self.assertIn(self.s1, v1.soci.all())
        self.assertIn(self.s1, v2.soci.all())

    def test_clean_rejects_when_no_eligible_soci(self):
        from django.core.exceptions import ValidationError

        v = Verbale(data=datetime.date(2026, 4, 30))
        with self.assertRaises(ValidationError):
            v.clean()


class GeneraVerbaleMensileTests(TestCase):
    def setUp(self):
        self.s1 = make_socio()
        Quota.objects.all().delete()

    def test_creates_verbale_when_soci_available(self):
        _make_quota(self.s1, 2026, 1)
        out = StringIO()
        call_command("genera_verbale_mensile", stdout=out)
        self.assertEqual(Verbale.objects.count(), 1)
        self.assertIn("1 soci", out.getvalue())

    def test_skips_when_no_soci(self):
        out = StringIO()
        call_command("genera_verbale_mensile", stdout=out)
        self.assertEqual(Verbale.objects.count(), 0)
        self.assertIn("Nessun socio", out.getvalue())


class NewsletterModelTests(TestCase):
    def test_str(self):
        nl = Newsletter.objects.create(oggetto="Test", corpo="<p>Hi</p>")
        self.assertIn("Test", str(nl))
        self.assertIn("Bozza", str(nl))

    def test_default_stato_is_bozza(self):
        nl = Newsletter.objects.create(oggetto="Test", corpo="<p>Hi</p>")
        self.assertEqual(nl.stato, "bozza")

    def test_get_destinatari_tutti(self):
        s1 = make_socio(consenso_marketing=True)
        make_socio(**LUIGI, consenso_marketing=False)
        nl = Newsletter(destinatari="tutti")
        qs = nl.get_destinatari_queryset()
        self.assertIn(s1, qs)
        self.assertEqual(qs.count(), 1)

    def test_get_destinatari_in_regola(self):
        s1 = make_socio(consenso_marketing=True)
        _make_quota(s1, 2026, 1)
        s2 = make_socio(**LUIGI, consenso_marketing=True)
        Quota.objects.filter(socio=s2).delete()
        nl = Newsletter(destinatari="in_regola")
        qs = nl.get_destinatari_queryset()
        self.assertIn(s1, qs)
        self.assertNotIn(s2, qs)

    def test_get_destinatari_scaduti(self):
        s1 = make_socio(consenso_marketing=True)
        Quota.objects.filter(socio=s1).delete()
        _make_quota(s1, 2024, 1)  # old expired quota
        s2 = make_socio(**LUIGI, consenso_marketing=True)
        _make_quota(s2, 2026, 1)  # active quota
        nl = Newsletter(destinatari="scaduti")
        qs = nl.get_destinatari_queryset()
        self.assertIn(s1, qs)
        self.assertNotIn(s2, qs)

    def test_excludes_non_approvati(self):
        make_socio(consenso_marketing=True, approvato=False)
        nl = Newsletter(destinatari="tutti")
        self.assertEqual(nl.get_destinatari_queryset().count(), 0)

    @patch("resend.Emails.send")
    def test_invia_sends_and_updates_stato(self, mock_send):
        make_socio(consenso_marketing=True)
        nl = Newsletter.objects.create(
            oggetto="Test", corpo="<p>Ciao</p>", destinatari="tutti"
        )
        sent = nl.invia()
        self.assertEqual(sent, 1)
        nl.refresh_from_db()
        self.assertEqual(nl.stato, "inviata")
        self.assertEqual(nl.num_destinatari, 1)
        self.assertIsNotNone(nl.data_invio)
        mock_send.assert_called_once()

    @patch("resend.Emails.send")
    def test_invia_returns_zero_when_no_recipients(self, mock_send):
        nl = Newsletter.objects.create(
            oggetto="Test", corpo="<p>Ciao</p>", destinatari="tutti"
        )
        sent = nl.invia()
        self.assertEqual(sent, 0)
        mock_send.assert_not_called()


class NewsletterAdminTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_superuser("admin", "admin@example.com", "password")
        self.client.login(username="admin", password="password")

    def test_add_page_loads(self):
        response = self.client.get("/admin/reports/newsletter/add/")
        self.assertEqual(response.status_code, 200)

    def test_preview_page(self):
        nl = Newsletter.objects.create(oggetto="Test", corpo="<p>Hi</p>")
        response = self.client.get(f"/admin/reports/newsletter/{nl.pk}/preview/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test")

    def test_sent_newsletter_cannot_be_edited(self):
        nl = Newsletter.objects.create(
            oggetto="Test", corpo="<p>Hi</p>", stato="inviata"
        )
        response = self.client.post(
            f"/admin/reports/newsletter/{nl.pk}/change/",
            {"oggetto": "Changed", "corpo": "<p>X</p>", "destinatari": "tutti"},
        )
        nl.refresh_from_db()
        assert response.status_code == 403
        self.assertEqual(nl.oggetto, "Test")  # unchanged
