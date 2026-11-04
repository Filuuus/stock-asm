"""Saves the visits the plan proposes for two months ahead, so staff can schedule them and parts get
ordered in time. Run at the start of each month; running it again adds only what's new."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from maintenance.models import Visit
from maintenance.services import build_plan


class Command(BaseCommand):
    help = 'Saves the proposed service visits for two months ahead.'

    def handle(self, **options):
        proposed = build_plan(timezone.localdate())['proposed_visits']
        for p in proposed['parlors']:
            visit, created = Visit.objects.get_or_create(parlor_id=p['parlor'], month=proposed['month'],
                                                         defaults={'parts': p['parts']})
            if not created and visit.status == 'proposed':
                known = {x['code'] for x in visit.parts}
                visit.parts += [x for x in p['parts'] if x['code'] not in known]
                visit.save()
        self.stdout.write(f"{len(proposed['parlors'])} visits proposed for {proposed['month']:%Y-%m}")
