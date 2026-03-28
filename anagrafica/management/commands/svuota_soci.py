from django.core.management.base import BaseCommand
from anagrafica.models import Socio, Quota


class Command(BaseCommand):
    help = "Elimina tutti i soci e le relative quote"

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Conferma l'eliminazione senza prompt interattivo",
        )

    def handle(self, *args, **options):
        totale_quote = Quota.objects.count()
        totale_soci = Socio.objects.count()

        if not options["confirm"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Stai per eliminare {totale_soci} soci e {totale_quote} quote. Sei sicuro? [s/N] "
                ),
                ending="",
            )
            risposta = input()
            if risposta.lower() != "s":
                self.stdout.write(self.style.ERROR("Operazione annullata."))
                return

        Quota.objects.all().delete()
        Socio.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"✅ Eliminati {totale_soci} soci e {totale_quote} quote."
            )
        )
