import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from tracker.models import Category, Profile, Team

# Default roles with a color and starter categories. Members can add more categories later.
TEAMS = {
    'Developer': ('#4c662b', ['Feature', 'Bug fix', 'Code review', 'Testing', 'Deployment', 'Research']),
    'Toxicologist': ('#8e4a8c', ['Study review', 'Risk assessment', 'Report writing', 'Literature search', 'Regulatory submission']),
    'Technical': ('#2c638b', ['Support request', 'Infrastructure', 'Maintenance', 'Equipment', 'Documentation']),
    'Administration': ('#9a6b00', ['Scheduling', 'Procurement', 'Meetings', 'Records', 'Onboarding']),
}
SHARED = ['General', 'Training']


class Command(BaseCommand):
    help='Creates the default roles, their starter categories, and the initial administrator.'
    def handle(self,*args,**options):
        for name, (color, categories) in TEAMS.items():
            team, _ = Team.objects.get_or_create(name=name, defaults={'color': color})
            for category in categories: Category.objects.get_or_create(team=team, name=category)
        for category in SHARED: Category.objects.get_or_create(team=None, name=category)
        User=get_user_model(); username=os.getenv('ADMIN_USERNAME','admin'); password=os.getenv('ADMIN_PASSWORD','ChangeMe123!'); display=os.getenv('ADMIN_DISPLAY_NAME','Project Admin')
        user,created=User.objects.get_or_create(username=username,defaults={'first_name':display,'is_staff':True})
        user.first_name=display; user.is_staff=True; user.is_active=True
        if created: user.set_password(password)
        user.save()
        profile, _ = Profile.objects.get_or_create(user=user)
        if profile.team is None:
            profile.team = Team.objects.get(name='Administration'); profile.save()
        self.stdout.write(self.style.SUCCESS(f'Tracker initialized with {len(TEAMS)} roles. Admin: {username}'))
