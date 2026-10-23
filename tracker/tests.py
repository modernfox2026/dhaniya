from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import ProjectArea, Ticket, TicketHistory

User = get_user_model()


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class TrackerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user('boss', password='pw-123456789', first_name='Boss Person', is_staff=True)
        cls.member = User.objects.create_user('dev', password='pw-123456789', first_name='Dev Person')
        cls.area = ProjectArea.objects.create(name='Reports')
        cls.ticket = Ticket.objects.create(title='Port report', description='Legacy', submitted_by=cls.admin, area=cls.area)

    def setUp(self):
        self.client.force_login(self.member)

    def test_pages_render(self):
        for name in ['board', 'backlog', 'my_work', 'insights', 'ticket_create']:
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
                               'area': self.area.pk, 'assigned_to': self.member.pk, 'due_date': ''})
        changes = set(TicketHistory.objects.filter(ticket=self.ticket, change_type='Updated').values_list('new_value', flat=True))
        self.assertEqual(changes, {'Priority: High', 'Assigned to: Dev Person'})

    def test_completed_at_kept_when_editing_completed_ticket(self):
        done = timezone.now() - timedelta(days=5)
        Ticket.objects.filter(pk=self.ticket.pk).update(status='COMPLETED', completed_at=done)
        self.client.post(reverse('ticket_edit', args=[self.ticket.pk]), {'title': 'New title', 'description': 'Legacy',
                         'status': 'COMPLETED', 'priority': 'Medium', 'area': self.area.pk, 'assigned_to': '', 'due_date': ''})
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
                                                               'area': self.area.pk, 'add_another': '1'})
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
