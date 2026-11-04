import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def forwards(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    Profile = apps.get_model('tracker', 'Profile')
    Ticket = apps.get_model('tracker', 'Ticket')
    for user in User.objects.all():
        Profile.objects.get_or_create(user=user)
    # Tasks already in flight start their work clock at upgrade time.
    Ticket.objects.filter(status__in=['IN_PROGRESS', 'READY_TO_TEST']).update(timer_started_at=timezone.now(), started_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tracker', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Team',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('color', models.CharField(default='#4c662b', help_text='Hex color used for chips, e.g. #4c662b', max_length=7)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('team', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='members', to='tracker.team')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Sprint',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('goal', models.CharField(blank=True, max_length=255)),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('state', models.CharField(choices=[('PLANNED', 'Planned'), ('ACTIVE', 'Active'), ('CLOSED', 'Closed')], db_index=True, default='PLANNED', max_length=20)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-start_date', '-id']},
        ),
        # Project areas become categories. Existing ones stay as shared categories (no team).
        migrations.RenameModel(old_name='ProjectArea', new_name='Category'),
        migrations.AlterModelOptions(name='category', options={'ordering': ['team__name', 'name'], 'verbose_name_plural': 'categories'}),
        migrations.AlterField(model_name='category', name='name', field=models.CharField(max_length=100)),
        migrations.AddField(model_name='category', name='team', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='categories', to='tracker.team')),
        migrations.AddField(model_name='category', name='created_by', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
        migrations.AddConstraint(model_name='category', constraint=models.UniqueConstraint(fields=('team', 'name'), name='tracker_category_team_name_uniq')),
        migrations.RenameField(model_name='ticket', old_name='area', new_name='category'),
        migrations.AddField(model_name='ticket', name='team', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tickets', to='tracker.team')),
        migrations.AddField(model_name='ticket', name='sprint', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tickets', to='tracker.sprint')),
        migrations.AddField(model_name='ticket', name='started_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='ticket', name='timer_started_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='ticket', name='time_spent_seconds', field=models.BigIntegerField(default=0)),
        migrations.AlterField(model_name='ticket', name='description', field=models.TextField(blank=True)),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
