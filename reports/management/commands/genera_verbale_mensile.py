from django.core.management.base import BaseCommand
from django.utils import timezone

from reports.models import Verbale


class Command(BaseCommand):
    help = "Genera automaticamente il verbale mensile con i soci non ancora assegnati"

    def handle(self, *args, **options):
        today = timezone.now().date()

        v = Verbale(data=today)
        # Check if there are eligible soci before creating
        eligibili = v._soci_eligibili()
        if not eligibili.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Nessun socio da aggiungere per {today.strftime('%d/%m/%Y')}. Verbale non creato."
                )
            )
            return

        v.save()
        v.assegna_soci()

        self.stdout.write(
            self.style.SUCCESS(f"✅ Creato {v} con {v.soci.count()} soci.")
        )
