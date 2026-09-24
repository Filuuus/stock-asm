from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile(sender, instance, created, **kwargs):
    if created:
        # A superuser (e.g. the bootstrap `createsuperuser` account) already
        # has full management access via is_management()'s is_superuser
        # check - defaulting their stored role to MANAGEMENT too keeps the
        # /usuarios panel honest about that instead of confusingly showing
        # "Vendedor" for the one account that actually has full access.
        role = Profile.ROLE_MANAGEMENT if instance.is_superuser else Profile.ROLE_SALESPERSON
        Profile.objects.create(user=instance, role=role)
