"""The secret link for the Servicios view embedded in Notion (accounts.EmbedLink).

    manage.py embed_link notion            # creates the account (Vendedor, Servicios) if needed, prints a new link
    manage.py embed_link notion --revoke   # deletes the account's links: the embed stops working

Paste the printed path after the office address (https://interno.agrostma.com) into a Notion /embed block.
"""
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import EmbedLink, Profile


class Command(BaseCommand):
    help = 'Creates or revokes the secret link for the embedded Servicios view.'

    def add_arguments(self, parser):
        parser.add_argument('username')
        parser.add_argument('--revoke', action='store_true')

    def handle(self, username, revoke, **options):
        User = get_user_model()
        if revoke:
            n = EmbedLink.objects.filter(user__username=username).delete()[0]
            self.stdout.write(f'{n} link(s) revoked for {username}')
            return
        user, created = User.objects.get_or_create(username=username, defaults={'first_name': 'Notion'})
        if created:
            user.set_unusable_password()  # it only signs in through the link
            user.save()
            Profile.objects.filter(user=user).update(role=Profile.ROLE_SALESPERSON, zone='SERVICIOS')
        link = EmbedLink.objects.create(user=user, token=secrets.token_urlsafe(32))
        self.stdout.write(f'/embed/servicios?k={link.token}')
