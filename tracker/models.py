from django.conf import settings
from django.db import models
from django.utils import timezone


class Team(models.Model):
    """A role or discipline such as Developer, Toxicologist, Technical, or Administration."""
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    color = models.CharField(max_length=7, default='#4c662b', help_text='Hex color used for chips, e.g. #4c662b')
    is_active = models.BooleanField(default=True)
    class Meta: ordering = ['name']
    def __str__(self): return self.name


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    team = models.ForeignKey(Team, null=True, blank=True, on_delete=models.SET_NULL, related_name='members')
    def __str__(self): return f'{self.user} ({self.team or "No team"})'


def team_of(user):
    """The user's team, or None. Safe for users created before profiles existed."""
    profile = getattr(user, 'profile', None) if user and user.is_authenticated else None
    return profile.team if profile else None


class Category(models.Model):
    """A kind of work. Categories with no team are shared by everyone."""
    name = models.CharField(max_length=100)
    team = models.ForeignKey(Team, null=True, blank=True, on_delete=models.CASCADE, related_name='categories')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    is_active = models.BooleanField(default=True)
    class Meta:
        ordering = ['team__name', 'name']
        verbose_name_plural = 'categories'
        constraints = [models.UniqueConstraint(fields=['team', 'name'], name='tracker_category_team_name_uniq')]
    def __str__(self): return f'{self.team} · {self.name}' if self.team_id else self.name


class Sprint(models.Model):
    class State(models.TextChoices):
        PLANNED = 'PLANNED', 'Planned'
        ACTIVE = 'ACTIVE', 'Active'
        CLOSED = 'CLOSED', 'Closed'
    name = models.CharField(max_length=100)
    goal = models.CharField(max_length=255, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    state = models.CharField(max_length=20, choices=State.choices, default=State.PLANNED, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    closed_at = models.DateTimeField(null=True, blank=True)
    class Meta: ordering = ['-start_date', '-id']
    def __str__(self): return self.name
    @property
    def days_left(self): return (self.end_date - timezone.localdate()).days
    @property
    def length_days(self): return (self.end_date - self.start_date).days + 1
    @property
    def elapsed_pct(self):
        done = (timezone.localdate() - self.start_date).days + 1
        return max(0, min(100, round(done * 100 / max(self.length_days, 1))))


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
    # The work clock runs from the moment a task enters In Progress until it is Completed.
    # Moving it back to Backlog pauses the clock; reopening a completed task resumes it.
    TIMED_STATUSES = (Status.IN_PROGRESS, Status.READY_TO_TEST)

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.BACKLOG, db_index=True)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM, db_index=True)
    team = models.ForeignKey(Team, null=True, blank=True, on_delete=models.SET_NULL, related_name='tickets')
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name='tickets')
    sprint = models.ForeignKey(Sprint, null=True, blank=True, on_delete=models.SET_NULL, related_name='tickets')
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='submitted_tickets')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_tickets')
    submitted_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    timer_started_at = models.DateTimeField(null=True, blank=True)
    time_spent_seconds = models.BigIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-updated_at', '-id']
        indexes = [
            models.Index(fields=['status','priority'], name='tracker_tic_status_82c68a_idx'),
            models.Index(fields=['assigned_to','status'], name='tracker_tic_assigne_b50b07_idx'),
        ]
    @property
    def ticket_number(self): return f'{settings.TICKET_PREFIX}-{self.pk:06d}' if self.pk else f'{settings.TICKET_PREFIX}-NEW'
    def __str__(self): return f'{self.ticket_number} - {self.title}'

    @property
    def timer_running(self): return self.timer_started_at is not None

    @property
    def elapsed_seconds(self):
        """Time worked so far, including the interval currently running."""
        running = (timezone.now() - self.timer_started_at).total_seconds() if self.timer_started_at else 0
        return int(self.time_spent_seconds + max(running, 0))

    def apply_status(self, new):
        """Change status and keep the work clock and completion time in step. Caller saves."""
        now = timezone.now()
        timed = new in self.TIMED_STATUSES
        if self.timer_started_at and not timed:
            self.time_spent_seconds += max(int((now - self.timer_started_at).total_seconds()), 0)
            self.timer_started_at = None
        elif timed and not self.timer_started_at:
            self.timer_started_at = now
            self.started_at = self.started_at or now
        self.status = new
        self.completed_at = now if new == self.Status.COMPLETED else None


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
