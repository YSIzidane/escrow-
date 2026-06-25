from django.core.management.base import BaseCommand

from main.services.deal_deadline_service import process_deal_deadlines


class Command(BaseCommand):
    help = "Process deal deadline reminders, expirations, and admin escalations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Calculate pending deadline actions without writing notifications or status changes.",
        )

    def handle(self, *args, **options):
        result = process_deal_deadlines(dry_run=options["dry_run"])
        payload = result.as_dict()
        self.stdout.write(
            self.style.SUCCESS(
                "Processed deal deadlines: "
                f"reminders={payload['reminders_sent']}, "
                f"escalations={payload['escalations_sent']}, "
                f"expired={payload['expired']}, "
                f"completed={payload['completed']}"
            )
        )
