import random
from datetime import date

from django.core.management.base import BaseCommand

from anagrafica.models import Quota, Socio, get_data_scadenza_default

NOMI = [
    "Marco",
    "Luigi",
    "Anna",
    "Sofia",
    "Giulia",
    "Paolo",
    "Elena",
    "Luca",
    "Sara",
    "Matteo",
    "Chiara",
    "Davide",
    "Francesca",
    "Andrea",
    "Valentina",
    "Roberto",
    "Alessia",
    "Giovanni",
    "Martina",
    "Francesco",
]
COGNOMI = [
    "Rossi",
    "Ferrari",
    "Esposito",
    "Bianchi",
    "Romano",
    "Colombo",
    "Ricci",
    "Marino",
    "Greco",
    "Bruno",
    "Gallo",
    "Conti",
    "De Luca",
    "Mancini",
    "Costa",
    "Giordano",
    "Rizzo",
    "Lombardi",
    "Moretti",
    "Barbieri",
]
VIE = [
    "Via Roma",
    "Via Garibaldi",
    "Via Mazzini",
    "Corso Vittorio Emanuele",
    "Via Dante",
    "Piazza della Repubblica",
    "Via Cavour",
    "Via Verdi",
    "Via Nazionale",
    "Via del Corso",
]
COMUNI = [
    "Lecce",
    "Bari",
    "Brindisi",
    "Taranto",
    "Gallipoli",
    "Otranto",
    "Maglie",
    "Casarano",
]
PROVINCE = ["LE", "BA", "BR", "TA"]
CAPS = ["73100", "70100", "72100", "74100", "73014", "73028", "73024", "73042"]
TIPI = ["SS", "SS", "SS", "SS", "SV", "SV", "VP", "PS", "CO", "SG", "TE"]

CF_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"


def genera_cf_casuale(nome, cognome, i):
    """Generate a plausible but fake codice fiscale."""
    consonanti = lambda s: [c for c in s.upper() if c not in "AEIOU"]  # noqa: E731
    vocali = lambda s: [c for c in s.upper() if c in "AEIOU"]  # noqa: E731

    def parte(s):
        s = s.upper().replace(" ", "")  # ← strip spaces
        c = consonanti(s)
        v = vocali(s)
        chars = (c + v + ["X", "X", "X"])[:3]
        return "".join(chars).upper()

    cf = parte(cognome) + parte(nome)
    cf += str(random.randint(60, 99))
    mesi = "ABCDEHLMPRST"
    cf += random.choice(mesi)
    cf += f"{random.randint(1, 28):02d}"
    cf += random.choice(CF_CHARS)
    cf += f"{random.randint(100, 999)}"

    # Control character
    from anagrafica.cf_utils import calcola_carattere_controllo

    cf += calcola_carattere_controllo(cf)
    return cf


class Command(BaseCommand):
    help = "Popola il database con dati demo"

    def add_arguments(self, parser):
        parser.add_argument("--soci", type=int, default=20)
        parser.add_argument("--svuota", action="store_true")

    def handle(self, *args, **options):
        if options["svuota"]:
            Quota.objects.all().delete()
            Socio.objects.all().delete()
            self.stdout.write(self.style.WARNING("Database svuotato."))

        n = options["soci"]
        created = 0

        for i in range(n):
            nome = random.choice(NOMI)
            cognome = random.choice(COGNOMI)
            cf = genera_cf_casuale(nome, cognome, i)

            # Ensure uniqueness — regenerate entirely to keep valid checksum
            while Socio.objects.filter(codice_fiscale=cf).exists():
                cf = genera_cf_casuale(nome, cognome, i + random.randint(100, 9999))

            email = f"{nome.lower()}.{cognome.lower().replace(' ', '')}{i}@example.com"
            while Socio.objects.filter(email=email).exists():
                email = f"{nome.lower()}.{cognome.lower().replace(' ', '')}{i}{random.randint(1, 99)}@example.com"

            comune_idx = random.randint(0, len(COMUNI) - 1)

            socio = Socio.objects.create(
                nome=nome,
                cognome=cognome,
                data_nascita=date(
                    random.randint(1950, 2000),
                    random.randint(1, 12),
                    random.randint(1, 28),
                ),
                luogo_nascita=random.choice(COMUNI),
                codice_fiscale=cf,
                via=f"{random.choice(VIE)} {random.randint(1, 99)}",
                comune=COMUNI[comune_idx],
                provincia=PROVINCE[min(comune_idx, len(PROVINCE) - 1)],
                cap=CAPS[min(comune_idx, len(CAPS) - 1)],
                email=email,
                telefono=f"33{random.randint(1000000, 9999999)}",
                approvato=True,
                tipo=random.choice(TIPI),
                consenso_marketing=random.choice([True, False]),
                consenso_immagini=random.choice([True, False]),
            )

            socio.genera_qr_code()
            socio.save(update_fields=["qr_code"])

            # Delete auto-created quota, we'll create our own
            Quota.objects.filter(socio=socio).delete()

            for anno in [2025, 2026]:
                scadenza = get_data_scadenza_default(anno)
                data_inizio = date(anno, 1, 1)

                # Vary scenarios
                if anno == 2025:
                    stato = "pagata"
                    data_pagamento = date(2025, 1, random.randint(1, 28))
                elif i % 4 == 3:
                    # Some 2026 quotas still pending
                    stato = "in_attesa"
                    data_pagamento = None
                else:
                    stato = "pagata"
                    data_pagamento = date(2026, 1, random.randint(1, 28))

                Quota.objects.create(
                    socio=socio,
                    anno=anno,
                    stato=stato,
                    importo=random.choice([5, 10, 20]),
                    data_inizio=data_inizio,
                    data_scadenza=scadenza,
                    data_pagamento=data_pagamento,
                )

            created += 1

        self.stdout.write(self.style.SUCCESS(f"✅ Creati {created} soci demo."))
