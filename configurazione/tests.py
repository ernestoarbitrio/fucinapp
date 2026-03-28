from django.test import TestCase, Client
from django.contrib.auth.models import User

from configurazione.models import Configurazione
from anagrafica.tests import make_socio


class ConfigurazioneModelTests(TestCase):
    def test_get_creates_default_instance(self):
        config = Configurazione.get()
        self.assertIsNotNone(config)
        self.assertEqual(config.pk, 1)

    def test_get_returns_same_instance(self):
        c1 = Configurazione.get()
        c2 = Configurazione.get()
        self.assertEqual(c1.pk, c2.pk)

    def test_save_always_forces_pk_1(self):
        config = Configurazione(nome_associazione="Test APS")
        config.save()
        self.assertEqual(config.pk, 1)
        self.assertEqual(Configurazione.objects.count(), 1)

    def test_second_save_overwrites_first(self):
        Configurazione.objects.create(pk=1, nome_associazione="Prima")
        config = Configurazione(nome_associazione="Seconda")
        config.save()
        self.assertEqual(Configurazione.objects.count(), 1)
        self.assertEqual(Configurazione.objects.get(pk=1).nome_associazione, "Seconda")

    def test_str_returns_nome_associazione(self):
        config = Configurazione.get()
        self.assertEqual(str(config), config.nome_associazione)

    def test_default_nome_is_fucina_salentina(self):
        config = Configurazione.get()
        self.assertEqual(config.nome_associazione, "Fucina Salentina APS")

    def test_default_delta_giorni_iscrizione(self):
        config = Configurazione.get()
        self.assertEqual(config.delta_giorni_iscrizione, 365)

    def test_default_delta_giorni_registro(self):
        config = Configurazione.get()
        self.assertEqual(config.delta_giorni_registro, 30)

    def test_consiglio_direttivo_many_to_many(self):
        config = Configurazione.get()
        s1 = make_socio()
        s2 = make_socio(
            nome="Luigi",
            cognome="Bianchi",
            codice_fiscale="BNCLGU85B01H501Z",
            email="luigi@example.com",
        )
        config.consiglio_direttivo.add(s1, s2)
        self.assertEqual(config.consiglio_direttivo.count(), 2)

    def test_consiglio_direttivo_remove(self):
        config = Configurazione.get()
        s1 = make_socio()
        config.consiglio_direttivo.add(s1)
        config.consiglio_direttivo.remove(s1)
        self.assertEqual(config.consiglio_direttivo.count(), 0)


class ConfigurazioneAdminTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )
        self.client.login(username="admin", password="password")

    def test_changelist_redirects_to_change_form(self):
        Configurazione.get()
        response = self.client.get("/admin/configurazione/configurazione/")
        self.assertRedirects(
            response,
            "/admin/configurazione/configurazione/1/change/",
            fetch_redirect_response=False,
        )

    def test_change_form_returns_200(self):
        Configurazione.get()
        response = self.client.get("/admin/configurazione/configurazione/1/change/")
        self.assertEqual(response.status_code, 200)

    def test_cannot_add_second_instance(self):
        Configurazione.get()
        response = self.client.get("/admin/configurazione/configurazione/add/")
        self.assertEqual(response.status_code, 403)

    def test_cannot_delete_instance(self):
        Configurazione.get()
        response = self.client.post(
            "/admin/configurazione/configurazione/1/delete/", {"post": "yes"}
        )
        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(Configurazione.objects.count(), 1)
