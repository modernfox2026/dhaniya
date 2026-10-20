from django.conf import settings
from django.db import models

class ProjectArea(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    class Meta: ordering = ['name']
    def __str__(self): return self.name

class Ticket(models.Model):
    class Status(models.TextChoices):
        BACKLOG = 'BACKLOG', 'Backlog'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        READY_TO_TEST = 'READY_TO_TEST', 'Ready to Test'
        COMPLETED = 'COMPLETED', 'Completed'
    class Priority(models.TextChoices):
        CRITICAL = 'Critical', 'Critical'
        HIGH = 'High', 'High'
        MEDIUM = 'Medium', 'Medium'
        LOW = 'Low', 'Low'
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.BACKLOG, db_index=True)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM, db_index=True)
    area = models.ForeignKey(ProjectArea, null=True, blank=True, on_delete=models.SET_NULL, related_name='tickets')
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='submitted_tickets')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_tickets')
    submitted_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-updated_at', '-id']
        indexes = [models.Index(fields=['status','priority']), models.Index(fields=['assigned_to','status'])]
    @property
    def ticket_number(self): return f'ACMI-{self.pk:06d}' if self.pk else 'ACMI-NEW'
    def __str__(self): return f'{self.ticket_number} - {self.title}'

class TicketComment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comments')
    text = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    class Meta: ordering = ['-created_at']

class TicketHistory(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='history')
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    change_type = models.CharField(max_length=50)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-changed_at']
