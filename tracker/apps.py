from django.apps import AppConfig
from django.conf import settings
from django.db.models.signals import post_save


def ensure_profile(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        from .models import Profile
        Profile.objects.get_or_create(user=instance)


class TrackerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tracker'
    def ready(self):
        post_save.connect(ensure_profile, sender=settings.AUTH_USER_MODEL, dispatch_uid='tracker_ensure_profile')
