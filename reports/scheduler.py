import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django_apscheduler.jobstores import DjangoJobStore

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
scheduler.add_jobstore(DjangoJobStore(), "default")


def genera_verbale_mensile_job():
    from django.core.management import call_command

    call_command("genera_verbale_mensile")


def start():
    if scheduler.running:
        return
    scheduler.add_job(
        genera_verbale_mensile_job,
        trigger=CronTrigger(day="last", hour=23, minute=0),
        id="genera_verbale_mensile",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info(
        "Scheduler avviato: genera_verbale_mensile programmato per l'ultimo giorno del mese."
    )
