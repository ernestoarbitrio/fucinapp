import datetime
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase

from anagrafica.models import Quota
from anagrafica.tests import LUIGI, make_socio
from reports.models import Verbale


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
