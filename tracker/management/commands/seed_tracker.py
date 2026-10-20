import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from tracker.models import ProjectArea

AREAS=['Analyze','Labeling','Required Tests','Products','Certification','Transfers','Reports','UI/UX','Database','Operations','Other']
class Command(BaseCommand):
    help='Creates standard project areas and the initial administrator.'
    def handle(self,*args,**options):
        for name in AREAS: ProjectArea.objects.get_or_create(name=name)
        User=get_user_model(); username=os.getenv('ADMIN_USERNAME','admin'); password=os.getenv('ADMIN_PASSWORD','ChangeMe123!'); display=os.getenv('ADMIN_DISPLAY_NAME','Project Admin')
        user,created=User.objects.get_or_create(username=username,defaults={'first_name':display,'is_staff':True})
        user.first_name=display; user.is_staff=True; user.is_active=True; user.set_password(password); user.save()
        self.stdout.write(self.style.SUCCESS(f'Tracker initialized. Admin: {username}'))
