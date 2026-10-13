"""Renames product photos and GEA drawings to random names, so their URLs don't
give away the part number (owner, 2026-10-13: codes are private). Safe to run
again: files that already have a random name are left alone.

Photos: the file is renamed and ProductImage.file updated. Drawings have no
table, so DRAWING_NAMES (backend/exports/gea, gitignored like the drawings)
maps GEA's name to ours; api.services._local_drawing reads it.
"""
import json
import os
import re
import secrets

from django.core.management.base import BaseCommand

from api.services import DRAWING_NAMES_FILE, DRAWINGS_DIR
from catalog.models import ProductImage
from catalog.services import PRODUCTS_DIR

RANDOM_NAME_RE = re.compile(r'^[0-9a-f]{16}\.\w+$')


def random_name(old):
    return secrets.token_hex(8) + os.path.splitext(old)[1].lower()


class Command(BaseCommand):
    help = 'Gives product photos and drawings random file names.'

    def handle(self, *args, **options):
        renamed = {}
        # Row by row, right after each rename, so disk and table never disagree.
        for img in ProductImage.objects.all():
            if RANDOM_NAME_RE.match(img.file):
                continue
            if img.file not in renamed:
                new = random_name(img.file)
                os.rename(PRODUCTS_DIR / img.file, PRODUCTS_DIR / new)
                renamed[img.file] = new
            img.file = renamed[img.file]
            img.save(update_fields=['file'])
        self.stdout.write(f'{len(renamed)} fotos renombradas.')

        names = json.loads(DRAWING_NAMES_FILE.read_text()) if DRAWING_NAMES_FILE.exists() else {}
        count = 0
        for name in sorted(os.listdir(DRAWINGS_DIR)):
            if RANDOM_NAME_RE.match(name):
                continue
            names[name] = random_name(name)
            os.rename(DRAWINGS_DIR / name, DRAWINGS_DIR / names[name])
            count += 1
            # Saved after every file, so an interruption can't orphan one.
            DRAWING_NAMES_FILE.write_text(json.dumps(names, indent=1))
        self.stdout.write(f'{count} dibujos renombrados.')
