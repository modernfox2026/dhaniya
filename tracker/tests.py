from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Category, Profile, Sprint, Team, Ticket, TicketHistory

User = get_user_model()


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class TrackerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user('boss', password='pw-123456789', first_name='Boss Person', is_staff=True)
        cls.member = User.objects.create_user('dev', password='pw-123456789', first_name='Dev Person')
        cls.area = Category.objects.create(name='Reports')
        cls.ticket = Ticket.objects.create(title='Port report', description='Legacy', submitted_by=cls.admin, category=cls.area)

    def setUp(self):
        self.client.force_login(self.member)

    def test_pages_render(self):
        for name in ['board', 'backlog', 'my_work', 'insights', 'ticket_create', 'sprints', 'categories', 'category_create']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        for name in ['ticket_detail', 'ticket_edit']:
            self.assertEqual(self.client.get(reverse(name, args=[self.ticket.pk])).status_code, 200, name)

    def test_search_by_ticket_number(self):
        other = Ticket.objects.create(title='Unrelated', description='x', submitted_by=self.admin)
        response = self.client.get(reverse('backlog'), {'q': self.ticket.ticket_number})
        self.assertContains(response, 'Port report')
        self.assertNotContains(response, other.title)

    def test_quick_filters(self):
        Ticket.objects.create(title='Late one', description='x', submitted_by=self.admin, assigned_to=self.member,
                              due_date=timezone.localdate() - timedelta(days=2))
        response = self.client.get(reverse('backlog'), {'assignee': 'me', 'due': 'overdue'})
        self.assertContains(response, 'Late one')
        self.assertNotContains(response, 'Port report')
        response = self.client.get(reverse('backlog'), {'assignee': 'none'})
        self.assertContains(response, 'Port report')

    def test_move_json_records_history(self):
        url = reverse('ticket_move', args=[self.ticket.pk])
        response = self.client.post(url, {'status': 'COMPLETED'}, HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(response.json()['label'], 'Completed')
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.completed_at)
        self.assertTrue(TicketHistory.objects.filter(ticket=self.ticket, change_type='StatusChanged').exists())

    def test_move_rejects_external_next(self):
        url = reverse('ticket_move', args=[self.ticket.pk])
        response = self.client.post(url, {'status': 'IN_PROGRESS', 'next': 'https://evil.example/'})
        self.assertRedirects(response, reverse('board'), fetch_redirect_response=False)

    def test_edit_records_field_changes(self):
        url = reverse('ticket_edit', args=[self.ticket.pk])
        self.client.post(url, {'title': 'Port report', 'description': 'Legacy', 'status': 'BACKLOG', 'priority': 'High',
                               'category': self.area.pk, 'assigned_to': self.member.pk, 'due_date': ''})
        changes = set(TicketHistory.objects.filter(ticket=self.ticket, change_type='Updated').values_list('new_value', flat=True))
        self.assertEqual(changes, {'Priority: High', 'Assigned to: Dev Person'})

    def test_completed_at_kept_when_editing_completed_ticket(self):
        done = timezone.now() - timedelta(days=5)
        Ticket.objects.filter(pk=self.ticket.pk).update(status='COMPLETED', completed_at=done)
        self.client.post(reverse('ticket_edit', args=[self.ticket.pk]), {'title': 'New title', 'description': 'Legacy',
                         'status': 'COMPLETED', 'priority': 'Medium', 'category': self.area.pk, 'assigned_to': '', 'due_date': ''})
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.completed_at, done)

    def test_bulk_update(self):
        second = Ticket.objects.create(title='Second', description='x', submitted_by=self.admin)
        response = self.client.post(reverse('ticket_bulk'), {'tickets': [self.ticket.pk, second.pk], 'status': 'IN_PROGRESS',
                                                             'assigned_to': self.member.pk})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Ticket.objects.filter(status='IN_PROGRESS', assigned_to=self.member).count(), 2)

    def test_assign_to_me(self):
        self.client.post(reverse('ticket_assign_me', args=[self.ticket.pk]))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.assigned_to, self.member)

    def test_csv_export(self):
        response = self.client.get(reverse('backlog_export'))
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('Port report', response.content.decode())

    def test_create_and_add_another(self):
        response = self.client.post(reverse('ticket_create'), {'title': 'New', 'description': 'd', 'priority': 'Low',
                                                               'category': self.area.pk, 'add_another': '1'})
        self.assertTrue(response['Location'].startswith(reverse('ticket_create')))

    def test_duplicate_prefills_form(self):
        response = self.client.get(reverse('ticket_create'), {'from': self.ticket.pk})
        self.assertContains(response, 'Copy of Port report')

    def test_user_admin_requires_staff_and_toggles(self):
        self.assertEqual(self.client.get(reverse('users')).status_code, 302)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('users')).status_code, 200)
        self.client.post(reverse('user_toggle_active', args=[self.member.pk]))
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)
        self.assertEqual(self.client.post(reverse('user_toggle_admin', args=[self.admin.pk])).status_code, 403)


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class TeamSprintTimeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dev_team = Team.objects.create(name='Developer')
        cls.tox_team = Team.objects.create(name='Toxicologist')
        cls.admin = User.objects.create_user('boss', password='pw-123456789', is_staff=True)
        cls.dev = User.objects.create_user('dev', password='pw-123456789', first_name='Dev')
        Profile.objects.filter(user=cls.dev).update(team=cls.dev_team)
        cls.bug = Category.objects.create(name='Bug fix', team=cls.dev_team)
        cls.study = Category.objects.create(name='Study review', team=cls.tox_team)

    def setUp(self):
        self.client.force_login(self.dev)

    def test_profile_created_for_new_users(self):
        self.assertTrue(Profile.objects.filter(user=self.admin).exists())

    def test_new_task_defaults_to_users_team(self):
        response = self.client.get(reverse('ticket_create'))
        self.assertEqual(response.context['form'].initial['team'], self.dev_team.pk)

    def test_category_must_match_team(self):
        response = self.client.post(reverse('ticket_create'), {'title': 'x', 'priority': 'Low', 'team': self.dev_team.pk, 'category': self.study.pk})
        self.assertEqual(response.status_code, 200)
        self.assertIn('category', response.context['form'].errors)
        self.client.post(reverse('ticket_create'), {'title': 'y', 'priority': 'Low', 'category': self.bug.pk})
        self.assertEqual(Ticket.objects.get(title='y').team, self.dev_team)

    def test_member_adds_category_only_for_own_team(self):
        self.client.post(reverse('category_create'), {'name': 'Refactor', 'team': self.tox_team.pk, 'is_active': 'on'})
        self.assertEqual(Category.objects.get(name='Refactor').team, self.dev_team)
        self.assertEqual(self.client.get(reverse('category_edit', args=[self.study.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('category_edit', args=[self.bug.pk])).status_code, 200)

    def test_duplicate_category_rejected(self):
        response = self.client.post(reverse('category_create'), {'name': 'bug FIX', 'is_active': 'on'})
        self.assertIn('name', response.context['form'].errors)

    def test_clock_runs_from_in_progress_to_completed(self):
        ticket = Ticket.objects.create(title='t', submitted_by=self.dev)
        move = lambda status: self.client.post(reverse('ticket_move', args=[ticket.pk]), {'status': status}, HTTP_X_REQUESTED_WITH='fetch')
        move('READY_TO_TEST')  # straight to test also starts the clock
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.timer_started_at)
        Ticket.objects.filter(pk=ticket.pk).update(timer_started_at=timezone.now() - timedelta(hours=2), started_at=timezone.now() - timedelta(hours=2))
        move('IN_PROGRESS')
        ticket.refresh_from_db()
        self.assertEqual(ticket.time_spent_seconds, 0, 'moving between timed stages keeps one interval')
        data = move('COMPLETED').json()
        ticket.refresh_from_db()
        self.assertFalse(data['running'])
        self.assertIsNone(ticket.timer_started_at)
        self.assertAlmostEqual(ticket.time_spent_seconds, 7200, delta=5)

    def test_backlog_pauses_clock(self):
        ticket = Ticket.objects.create(title='t', submitted_by=self.dev)
        ticket.apply_status('IN_PROGRESS'); ticket.timer_started_at -= timedelta(minutes=30); ticket.save()
        ticket.apply_status('BACKLOG'); ticket.save()
        self.assertIsNone(ticket.timer_started_at)
        self.assertAlmostEqual(ticket.time_spent_seconds, 1800, delta=5)
        self.assertIsNone(ticket.completed_at)

    def test_board_defaults_to_active_sprint(self):
        sprint = Sprint.objects.create(name='S1', start_date=timezone.localdate(), end_date=timezone.localdate() + timedelta(days=13), state='ACTIVE')
        Ticket.objects.create(title='In sprint', submitted_by=self.dev, sprint=sprint)
        Ticket.objects.create(title='Not planned', submitted_by=self.dev)
        response = self.client.get(reverse('board'))
        self.assertContains(response, 'In sprint')
        self.assertNotContains(response, 'Not planned')
        self.assertContains(self.client.get(reverse('board'), {'sprint': ''}), 'Not planned')

    def test_close_sprint_moves_unfinished(self):
        s1 = Sprint.objects.create(name='S1', start_date=timezone.localdate(), end_date=timezone.localdate(), state='ACTIVE')
        s2 = Sprint.objects.create(name='S2', start_date=timezone.localdate(), end_date=timezone.localdate())
        open_task = Ticket.objects.create(title='open', submitted_by=self.dev, sprint=s1)
        done_task = Ticket.objects.create(title='done', submitted_by=self.dev, sprint=s1, status='COMPLETED')
        self.assertEqual(self.client.post(reverse('sprint_state', args=[s1.pk]), {'action': 'close'}).status_code, 302)
        self.assertEqual(Sprint.objects.get(pk=s1.pk).state, 'ACTIVE', 'members cannot close sprints')
        self.client.force_login(self.admin)
        self.client.post(reverse('sprint_state', args=[s1.pk]), {'action': 'close', 'move_to': s2.pk})
        open_task.refresh_from_db(); done_task.refresh_from_db()
        self.assertEqual((open_task.sprint, done_task.sprint), (s2, s1))
        self.assertEqual(Sprint.objects.get(pk=s1.pk).state, 'CLOSED')

    def test_admin_sets_role_and_creates_login(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('user_edit', args=[self.dev.pk]), {'display_name': 'Dev', 'team': self.tox_team.pk, 'role': 'Member', 'is_active': 'on'})
        self.assertEqual(Profile.objects.get(user=self.dev).team, self.tox_team)
        self.client.post(reverse('user_create'), {'username': 'newbie', 'display_name': 'New', 'team': self.dev_team.pk, 'role': 'Member',
                                                  'password1': 'Str0ng-pass-123', 'password2': 'Str0ng-pass-123'})
        self.assertEqual(Profile.objects.get(user__username='newbie').team, self.dev_team)
        for name in ['teams', 'team_create', 'users', 'sprint_create']:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_admin_cannot_demote_self(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('user_edit', args=[self.admin.pk]), {'display_name': 'Boss', 'role': 'Member'})
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_staff and self.admin.is_active)


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class AdminDeleteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user('boss', password='pw-123456789', is_staff=True)
        cls.member = User.objects.create_user('dev', password='pw-123456789')

    def setUp(self):
        self.sprint = Sprint.objects.create(name='S1', start_date=timezone.localdate(), end_date=timezone.localdate())
        self.category = Category.objects.create(name='Reports')
        self.ticket = Ticket.objects.create(title='keep me', submitted_by=self.member, sprint=self.sprint, category=self.category)
        TicketHistory.objects.create(ticket=self.ticket, changed_by=self.member, change_type='Created')

    def test_members_cannot_delete(self):
        self.client.force_login(self.member)
        for name, obj in [('ticket_delete', self.ticket), ('sprint_delete', self.sprint), ('category_delete', self.category)]:
            self.client.post(reverse(name, args=[obj.pk]))
        self.client.post(reverse('ticket_bulk_delete'), {'tickets': [self.ticket.pk]})
        self.assertTrue(Ticket.objects.filter(pk=self.ticket.pk).exists())
        self.assertTrue(Sprint.objects.filter(pk=self.sprint.pk).exists())
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())

    def test_delete_sprint_keeps_tasks(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('sprint_delete', args=[self.sprint.pk]))
        self.assertFalse(Sprint.objects.exists())
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.sprint)

    def test_delete_category_keeps_tasks(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('category_delete', args=[self.category.pk]))
        self.assertFalse(Category.objects.exists())
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.category)

    def test_delete_task_removes_its_history(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('ticket_delete', args=[self.ticket.pk])).status_code, 405)
        self.client.post(reverse('ticket_delete', args=[self.ticket.pk]))
        self.assertFalse(Ticket.objects.exists())
        self.assertFalse(TicketHistory.objects.exists())

    def test_bulk_delete(self):
        other = Ticket.objects.create(title='other', submitted_by=self.member)
        spare = Ticket.objects.create(title='spare', submitted_by=self.member)
        self.client.force_login(self.admin)
        self.client.post(reverse('ticket_bulk_delete'), {'tickets': [self.ticket.pk, other.pk]})
        self.assertEqual(list(Ticket.objects.values_list('title', flat=True)), ['spare'])
