import urllib.error

from django.core.management.base import BaseCommand, CommandError

from clients.services import sync_clients


class Command(BaseCommand):
    help = (
        'Copies the active ERP clients (invoiced in the last year or registered in the last three '
        'months) to the Notion clients database: creates new ones, updates changed ones and unticks '
        'Activo for the rest. Never deletes. Safe to re-run.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only count what would change')

    def handle(self, *args, **options):
        try:
            sync_clients(self.stdout.write, dry_run=options['dry_run'])
        except urllib.error.HTTPError as error:
            raise CommandError(f'Notion: {error.code} {error.read().decode()}')
        except ValueError as error:
            raise CommandError(str(error))
