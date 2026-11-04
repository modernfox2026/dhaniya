import csv
import re
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Q, Sum, Value, When
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from .forms import (AdminPasswordResetForm, AdminUserCreationForm, BulkUpdateForm, CategoryForm, CommentForm, SprintForm, TeamForm,
                    TicketEditForm, TicketForm, UserEditForm, open_sprints)
from .models import Category, Profile, Sprint, Team, Ticket, TicketHistory, team_of

User = get_user_model()
STATUS_ORDER = [Ticket.Status.BACKLOG, Ticket.Status.IN_PROGRESS, Ticket.Status.READY_TO_TEST, Ticket.Status.COMPLETED]
PRIORITY_ORDER = [Ticket.Priority.CRITICAL, Ticket.Priority.HIGH, Ticket.Priority.MEDIUM, Ticket.Priority.LOW]
BOARD_COMPLETED_LIMIT = 25
TICKET_NUMBER = re.compile(rf'^(?:{re.escape(settings.TICKET_PREFIX)}-?|#)?0*(\d{{1,9}})$', re.IGNORECASE)

def is_admin(user): return user.is_authenticated and user.is_staff

def rank(field, values): return Case(*[When(**{field: v}, then=Value(i)) for i, v in enumerate(values)], output_field=IntegerField())

def display_name(user): return (user.get_full_name() or user.username) if user else 'Unassigned'

def safe_next(request, fallback):
    target = request.POST.get('next') or request.GET.get('next')
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()): return target
    return fallback

def wants_json(request): return request.headers.get('x-requested-with') == 'fetch'

class LocalLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

# ---------------------------------------------------------------- filtering

def filtered_tickets(request, default_sprint='', skip_status=False):
    qs = Ticket.objects.select_related('team','category','sprint','submitted_by','assigned_to')
    g = request.GET
    q = g.get('q','').strip()
    if q:
        text = Q(title__icontains=q)|Q(description__icontains=q)|Q(category__name__icontains=q)|Q(team__name__icontains=q)|Q(submitted_by__username__icontains=q)|Q(assigned_to__username__icontains=q)|Q(assigned_to__first_name__icontains=q)
        number = TICKET_NUMBER.match(q)
        qs = qs.filter(text | Q(pk=int(number.group(1)))) if number else qs.filter(text)
    if not skip_status and g.get('status') in dict(Ticket.Status.choices): qs = qs.filter(status=g['status'])
    if g.get('open') == '1': qs = qs.exclude(status=Ticket.Status.COMPLETED)
    if g.get('priority') in dict(Ticket.Priority.choices): qs = qs.filter(priority=g['priority'])
    if g.get('category', '').isdigit(): qs = qs.filter(category_id=g['category'])
    team = g.get('team', '')
    if team == 'mine': qs = qs.filter(team=team_of(request.user))
    elif team == 'none': qs = qs.filter(team__isnull=True)
    elif team.isdigit(): qs = qs.filter(team_id=team)
    sprint = g.get('sprint', default_sprint)
    if sprint == 'active': qs = qs.filter(sprint__state=Sprint.State.ACTIVE)
    elif sprint == 'none': qs = qs.filter(sprint__isnull=True)
    elif sprint.isdigit(): qs = qs.filter(sprint_id=sprint)
    if g.get('submitter', '').isdigit(): qs = qs.filter(submitted_by_id=g['submitter'])
    assignee = g.get('assignee', '')
    if assignee == 'me': qs = qs.filter(assigned_to=request.user)
    elif assignee == 'none': qs = qs.filter(assigned_to__isnull=True)
    elif assignee.isdigit(): qs = qs.filter(assigned_to_id=assignee)
    today = timezone.localdate()
    due = g.get('due')
    if due == 'overdue': qs = qs.filter(due_date__lt=today).exclude(status=Ticket.Status.COMPLETED)
    elif due == 'week': qs = qs.filter(due_date__gte=today, due_date__lte=today + timedelta(days=7))
    elif due == 'none': qs = qs.filter(due_date__isnull=True)
    return qs

FILTER_KEYS = ('q','status','priority','category','team','sprint','submitter','assignee','due','open')

def common_context(request, qs, default_sprint=''):
    # Status cards count everything in scope except the status filter itself, so they double as status toggles.
    scope = filtered_tickets(request, default_sprint, skip_status=True)
    counts = dict(scope.order_by().values_list('status').annotate(n=Count('id')))
    counts = {value: counts.get(value, 0) for value in STATUS_ORDER}
    return {
        'counts': counts, 'statuses': Ticket.Status.choices, 'priorities': Ticket.Priority.choices,
        'categories': Category.objects.filter(is_active=True).select_related('team'),
        'teams': Team.objects.filter(is_active=True), 'my_team': team_of(request.user),
        'sprints': Sprint.objects.exclude(state=Sprint.State.CLOSED).order_by('start_date'),
        'submitters': User.objects.filter(submitted_tickets__isnull=False).distinct().order_by('username'),
        'assignees': User.objects.filter(is_active=True).order_by('first_name', 'username'),
        'filtered_count': qs.count(), 'total_count': Ticket.objects.count(), 'today': timezone.localdate(),
        'has_filters': any(request.GET.get(k) for k in FILTER_KEYS),
        'sprint_param': request.GET.get('sprint', default_sprint),
    }

# ---------------------------------------------------------------- views

@login_required
def board(request):
    # The home board shows the active sprint for the whole team when one is running.
    default_sprint = 'active' if Sprint.objects.filter(state=Sprint.State.ACTIVE).exists() else ''
    qs = filtered_tickets(request, default_sprint).order_by(rank('priority', PRIORITY_ORDER), 'due_date', '-updated_at')
    columns = []
    for value, label in Ticket.Status.choices:
        items = qs.filter(status=value)
        hidden = 0
        if value == Ticket.Status.COMPLETED:
            total = items.count()
            items = list(items.order_by('-completed_at', '-updated_at')[:BOARD_COMPLETED_LIMIT])
            hidden = total - len(items)
        columns.append({'value': value, 'label': label, 'items': items, 'hidden': hidden})
    sprint_param = request.GET.get('sprint', default_sprint)
    if sprint_param.isdigit(): shown = Sprint.objects.filter(pk=sprint_param)
    elif sprint_param == 'active': shown = Sprint.objects.filter(state=Sprint.State.ACTIVE).order_by('start_date')
    else: shown = []
    return render(request, 'tracker/board.html', common_context(request, qs, default_sprint) | {
        'columns': columns, 'sprint_cards': [sprint_summary(s) for s in shown],
    })

def sprint_summary(sprint):
    tasks = list(sprint.tickets.only('status', 'time_spent_seconds', 'timer_started_at'))
    done = sum(1 for t in tasks if t.status == Ticket.Status.COMPLETED)
    return {'sprint': sprint, 'total': len(tasks), 'done': done, 'done_pct': round(done * 100 / (len(tasks) or 1)),
            'seconds': sum(t.elapsed_seconds for t in tasks)}

SORTS = {
    'number': ('id',), 'title': ('title',), 'status': (rank('status', STATUS_ORDER),), 'priority': (rank('priority', PRIORITY_ORDER),),
    'team': ('team__name',), 'category': ('category__name',), 'sprint': ('sprint__start_date',), 'time': ('time_spent_seconds',), 'assignee': ('assigned_to__first_name', 'assigned_to__username'), 'due': ('due_date',), 'updated': ('updated_at',),
}

SORT_COLUMNS = [('number','Task'),('title','Title'),('status','Status'),('priority','Priority'),('team','Team'),('category','Category'),('sprint','Sprint'),('assignee','Assigned to'),('due','Due'),('time','Time'),('updated','Updated')]

def sorted_tickets(request):
    qs = filtered_tickets(request)
    sort = request.GET.get('sort', '-updated')
    key = sort.lstrip('-')
    if key not in SORTS: sort, key = '-updated', 'updated'
    fields = [f.desc() if sort.startswith('-') and hasattr(f, 'desc') else (f'-{f}' if sort.startswith('-') else f) for f in SORTS[key]]
    return qs.order_by(*fields, '-id'), sort

@login_required
def backlog(request):
    qs, sort = sorted_tickets(request)
    per_page = request.GET.get('per_page') if request.GET.get('per_page') in ('25', '50', '100') else '50'
    page = Paginator(qs, int(per_page)).get_page(request.GET.get('page'))
    return render(request, 'tracker/backlog.html', common_context(request, qs) | {
        'page': page, 'tickets': page.object_list, 'sort': sort, 'per_page': per_page, 'sort_columns': SORT_COLUMNS,
        'bulk_users': User.objects.filter(is_active=True).order_by('first_name', 'username'),
    })

@login_required
def backlog_export(request):
    qs, _ = sorted_tickets(request)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="tasks-{timezone.localdate():%Y%m%d}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Task','Title','Status','Priority','Team','Category','Sprint','Submitted by','Assigned to','Submitted','Due','Started','Completed','Hours worked','Last updated','Description'])
    stamp = lambda value: timezone.localtime(value).strftime('%Y-%m-%d %H:%M') if value else ''
    for t in qs:
        writer.writerow([t.ticket_number, t.title, t.get_status_display(), t.priority, t.team or '', t.category.name if t.category else '', t.sprint or '', display_name(t.submitted_by),
                         display_name(t.assigned_to), stamp(t.submitted_at), t.due_date or '', stamp(t.started_at), stamp(t.completed_at),
                         round(t.elapsed_seconds / 3600, 2), stamp(t.updated_at), t.description])
    return response

@login_required
def my_work(request):
    today = timezone.localdate()
    mine = Ticket.objects.select_related('team','category','assigned_to').filter(assigned_to=request.user).exclude(status=Ticket.Status.COMPLETED)
    mine = mine.order_by(rank('priority', PRIORITY_ORDER), 'due_date', '-updated_at')
    attention = [t for t in mine if t.due_date and t.due_date <= today + timedelta(days=7)]
    groups = [(value, label, [t for t in mine if t.status == value]) for value, label in Ticket.Status.choices if value != Ticket.Status.COMPLETED]
    ready = Ticket.objects.select_related('team','category','assigned_to').filter(status=Ticket.Status.READY_TO_TEST).order_by(rank('priority', PRIORITY_ORDER), 'updated_at')[:10]
    activity = TicketHistory.objects.select_related('ticket','changed_by').order_by('-changed_at')[:15]
    month_ago = timezone.now() - timedelta(days=30)
    done_recent = Ticket.objects.filter(assigned_to=request.user, status=Ticket.Status.COMPLETED, completed_at__gte=month_ago)
    return render(request, 'tracker/my_work.html', {
        'today': today, 'attention': attention, 'groups': groups, 'ready': ready, 'activity': activity,
        'running': [t for t in mine if t.timer_running], 'my_team': team_of(request.user),
        'active_sprints': [sprint_summary(s) for s in Sprint.objects.filter(state=Sprint.State.ACTIVE).order_by('start_date')],
        'stats': {
            'open': len(mine), 'overdue': sum(1 for t in mine if t.due_date and t.due_date < today),
            'week': sum(1 for t in mine if t.due_date and today <= t.due_date <= today + timedelta(days=7)),
            'done': done_recent.count(),
            'hours': round((done_recent.aggregate(t=Sum('time_spent_seconds'))['t'] or 0) / 3600, 1),
            'submitted_open': Ticket.objects.filter(submitted_by=request.user).exclude(status=Ticket.Status.COMPLETED).count(),
        },
    })

@login_required
def insights(request):
    today = timezone.localdate()
    tickets = list(Ticket.objects.select_related('team','category','assigned_to'))
    total = len(tickets)
    status_counts = {value: 0 for value in STATUS_ORDER}
    categories, teams, people = {}, {}, {}
    for t in tickets:
        status_counts[t.status] = status_counts.get(t.status, 0) + 1
        team = teams.setdefault((t.team.name, t.team_id, t.team.color) if t.team else ('No team', None, ''), {'counts': {v: 0 for v in STATUS_ORDER}, 'seconds': 0, 'timed': 0})
        team['counts'][t.status] += 1
        if t.status == Ticket.Status.COMPLETED and t.time_spent_seconds:
            team['seconds'] += t.time_spent_seconds
            team['timed'] += 1
        cat = categories.setdefault((str(t.category), t.category_id) if t.category else ('Uncategorized', None), {'counts': {v: 0 for v in STATUS_ORDER}, 'seconds': 0, 'timed': 0})
        cat['counts'][t.status] += 1
        if t.status == Ticket.Status.COMPLETED and t.time_spent_seconds:
            cat['seconds'] += t.time_spent_seconds
            cat['timed'] += 1
        if t.status != Ticket.Status.COMPLETED:
            person = people.setdefault(display_name(t.assigned_to), {'open': 0, 'overdue': 0, **{p: 0 for p in PRIORITY_ORDER}})
            person['open'] += 1
            person[t.priority] = person.get(t.priority, 0) + 1
            if t.due_date and t.due_date < today: person['overdue'] += 1
    def segments(counts):
        n = sum(counts.values()) or 1
        return [{'value': value, 'label': label, 'count': counts.get(value, 0), 'pct': round(counts.get(value, 0) * 100 / n, 1)} for value, label in Ticket.Status.choices]
    def rows(groups, key):
        out = []
        for ident, g in groups.items():
            n = sum(g['counts'].values())
            out.append({'name': ident[0], 'id': ident[1], 'color': ident[2] if len(ident) > 2 else '', 'total': n, 'key': key,
                        'done_pct': round(g['counts'][Ticket.Status.COMPLETED] * 100 / (n or 1)), 'segments': segments(g['counts']),
                        'avg_seconds': g['seconds'] // g['timed'] if g['timed'] else None})
        return sorted(out, key=lambda r: -r['total'])
    max_open = max((p['open'] for p in people.values()), default=1)
    people_rows = sorted(({'name': name, **p, 'bars': [{'priority': pr, 'count': p[pr], 'pct': p[pr] * 100 / max_open} for pr in PRIORITY_ORDER]} for name, p in people.items()), key=lambda r: -r['open'])

    start = today - timedelta(days=today.weekday() + 7 * 11)  # Monday, 12 weeks back
    weeks = [{'start': start + timedelta(weeks=i), 'created': 0, 'completed': 0} for i in range(12)]
    worked = []
    for t in tickets:
        created = timezone.localtime(t.submitted_at).date()
        if created >= start: weeks[(created - start).days // 7]['created'] += 1
        if t.completed_at:
            done = timezone.localtime(t.completed_at).date()
            if done >= start: weeks[(done - start).days // 7]['completed'] += 1
            if done >= today - timedelta(days=90) and t.time_spent_seconds: worked.append(t.time_spent_seconds)
    peak = max((max(w['created'], w['completed']) for w in weeks), default=0) or 1
    for w in weeks: w['created_pct'], w['completed_pct'] = w['created'] * 100 / peak, w['completed'] * 100 / peak
    return render(request, 'tracker/insights.html', {
        'total': total, 'status_segments': segments(status_counts),
        'done_pct': round(status_counts[Ticket.Status.COMPLETED] * 100 / (total or 1)),
        'open_count': total - status_counts[Ticket.Status.COMPLETED],
        'overdue': sum(1 for t in tickets if t.due_date and t.due_date < today and t.status != Ticket.Status.COMPLETED),
        'unassigned': sum(1 for t in tickets if not t.assigned_to_id and t.status != Ticket.Status.COMPLETED),
        'avg_worked': sum(worked) // len(worked) if worked else None,
        'breakdowns': [('By role', 'badge', rows(teams, 'team')), ('By category', 'label', rows(categories, 'category'))], 'people_rows': people_rows,
        'weeks': weeks, 'peak': peak, 'completed_recent': sum(w['completed'] for w in weeks[-4:]),
    })

# ---------------------------------------------------------------- tickets

TRACKED_FIELDS = ['title', 'description', 'priority', 'team', 'category', 'sprint', 'assigned_to', 'due_date']

def field_text(ticket, field):
    value = getattr(ticket, field)
    if field == 'assigned_to': return display_name(value)
    if field == 'category': return value.name if value else 'Uncategorized'
    if field in ('team', 'sprint'): return str(value) if value else f'No {field}'
    if field == 'description': return value if len(value) <= 300 else value[:297] + '...'
    return str(value) if value not in (None, '') else 'Not set'

def snapshot(ticket): return {f: field_text(ticket, f) for f in TRACKED_FIELDS}

def record_changes(ticket, user, before):
    label = {f: Ticket._meta.get_field(f).verbose_name.capitalize() for f in TRACKED_FIELDS}
    rows = [TicketHistory(ticket=ticket, changed_by=user, change_type='Updated', old_value=f'{label[f]}: {before[f]}', new_value=f'{label[f]}: {text}')
            for f, text in snapshot(ticket).items() if text != before[f]]
    TicketHistory.objects.bulk_create(rows)
    return len(rows)

def set_status(ticket, new, user):
    """Move a ticket to a new workflow status, recording history and the work clock. Caller saves."""
    old = ticket.status
    if old == new: return False
    ticket.apply_status(new)
    TicketHistory.objects.create(ticket=ticket, changed_by=user, change_type='StatusChanged', old_value=old, new_value=new)
    return True

@login_required
@transaction.atomic
def ticket_create(request):
    if request.method == 'POST':
        form = TicketForm(request.POST, user=request.user)
        if form.is_valid():
            ticket=form.save(commit=False); ticket.submitted_by=request.user; ticket.save()
            TicketHistory.objects.create(ticket=ticket,changed_by=request.user,change_type='Created',new_value=Ticket.Status.BACKLOG)
            messages.success(request, f'{ticket.ticket_number} created.')
            if 'add_another' in request.POST:
                keep = {'priority': ticket.priority, 'team': ticket.team_id, 'category': ticket.category_id, 'sprint': ticket.sprint_id}
                return redirect(request.path + '?' + '&'.join(f'{k}={v}' for k, v in keep.items() if v))
            return redirect('ticket_detail', pk=ticket.pk)
    else:
        initial = {k: request.GET[k] for k in ('team', 'category', 'sprint', 'priority', 'assigned_to') if request.GET.get(k)}
        source = request.GET.get('from')
        if source and source.isdigit():
            original = Ticket.objects.filter(pk=source).first()
            if original:
                initial.update(title=f'Copy of {original.title}'[:200], description=original.description, priority=original.priority,
                               team=original.team_id, category=original.category_id, sprint=original.sprint_id, assigned_to=original.assigned_to_id)
        form=TicketForm(initial=initial, user=request.user)
    return render(request,'tracker/ticket_form.html',{'form':form,'title':'New task','creating':True})

@login_required
def ticket_detail(request, pk):
    ticket=get_object_or_404(Ticket.objects.select_related('team','category','sprint','submitted_by','assigned_to'),pk=pk)
    if request.method=='POST':
        form=CommentForm(request.POST)
        if form.is_valid():
            obj=form.save(commit=False); obj.ticket=ticket; obj.created_by=request.user; obj.save()
            TicketHistory.objects.create(ticket=ticket,changed_by=request.user,change_type='CommentAdded',new_value=obj.text)
            Ticket.objects.filter(pk=pk).update(updated_at=timezone.now())
            return redirect('ticket_detail',pk=pk)
    else: form=CommentForm()
    return render(request,'tracker/ticket_detail.html',{
        'ticket':ticket,'comment_form':form,'statuses':Ticket.Status.choices,'today':timezone.localdate(),
        'comments':ticket.comments.select_related('created_by'),'history':ticket.history.select_related('changed_by'),
    })

@login_required
@transaction.atomic
def ticket_edit(request, pk):
    ticket=get_object_or_404(Ticket,pk=pk)
    before, old_status = snapshot(ticket), ticket.status
    if request.method=='POST':
        form=TicketEditForm(request.POST,instance=ticket,user=request.user)
        if form.is_valid():
            updated=form.save(commit=False)
            new_status, updated.status = updated.status, old_status
            set_status(updated, new_status, request.user)
            updated.save()
            if not record_changes(updated, request.user, before) and old_status == new_status:
                messages.info(request, 'No changes to save.')
            else:
                messages.success(request,f'{updated.ticket_number} updated.')
            return redirect('ticket_detail',pk=pk)
    else: form=TicketEditForm(instance=ticket,user=request.user)
    return render(request,'tracker/ticket_form.html',{'form':form,'title':f'Edit {ticket.ticket_number}','ticket':ticket})

@login_required
@require_POST
@transaction.atomic
def ticket_move(request, pk):
    ticket=get_object_or_404(Ticket.objects.select_for_update(),pk=pk); new=request.POST.get('status')
    if new not in dict(Ticket.Status.choices): return HttpResponseBadRequest('Invalid status')
    if set_status(ticket, new, request.user): ticket.save()
    if wants_json(request):
        return JsonResponse({'ok': True, 'ticket': ticket.ticket_number, 'status': ticket.status, 'label': ticket.get_status_display(),
                             'elapsed': ticket.elapsed_seconds, 'running': ticket.timer_running})
    messages.success(request, f'{ticket.ticket_number} moved to {ticket.get_status_display()}.')
    return redirect(safe_next(request, 'board'))

@login_required
@require_POST
@transaction.atomic
def ticket_assign_me(request, pk):
    ticket=get_object_or_404(Ticket.objects.select_related('assigned_to'),pk=pk)
    if ticket.assigned_to_id != request.user.pk:
        before = snapshot(ticket)
        ticket.assigned_to = request.user
        ticket.save()
        record_changes(ticket, request.user, before)
        messages.success(request, f'{ticket.ticket_number} assigned to you.')
    return redirect(safe_next(request, reverse('ticket_detail', args=[pk])))

@login_required
@require_POST
@transaction.atomic
def ticket_bulk(request):
    form = BulkUpdateForm(request.POST)
    target = safe_next(request, 'backlog')
    if not form.is_valid():
        messages.error(request, 'Select at least one task and a valid change.')
        return redirect(target)
    data = form.cleaned_data
    if not any([data['status'], data['priority'], data['category'], data['assigned_to'], data['sprint']]):
        messages.info(request, 'Choose a field to change before applying.')
        return redirect(target)
    changed = 0
    for ticket in data['tickets'].select_related('team', 'category', 'sprint', 'assigned_to'):
        before, touched = snapshot(ticket), False
        if data['status']: touched = set_status(ticket, data['status'], request.user)
        if data['priority']: ticket.priority = data['priority']
        if data['category']:
            ticket.category = data['category']
            if data['category'].team_id: ticket.team = data['category'].team
        if data['assigned_to'] == 'none': ticket.assigned_to = None
        elif data['assigned_to']: ticket.assigned_to = data['assigned_to']
        if data['sprint'] == 'none': ticket.sprint = None
        elif data['sprint']: ticket.sprint = data['sprint']
        ticket.save()
        if record_changes(ticket, request.user, before) or touched: changed += 1
    messages.success(request, f'{changed} task{"s" if changed != 1 else ""} updated.')
    return redirect(target)

@login_required
def logout_view(request): logout(request); return redirect('login')

# ---------------------------------------------------------------- sprints

@login_required
def sprints(request):
    rows = [sprint_summary(s) for s in Sprint.objects.all()]
    order = {Sprint.State.ACTIVE: 0, Sprint.State.PLANNED: 1, Sprint.State.CLOSED: 2}
    rows.sort(key=lambda r: (order[r['sprint'].state], r['sprint'].start_date if r['sprint'].state != Sprint.State.CLOSED else -r['sprint'].start_date.toordinal()))
    return render(request, 'tracker/sprints.html', {
        'rows': rows, 'backlog_open': Ticket.objects.filter(sprint__isnull=True).exclude(status=Ticket.Status.COMPLETED).count(),
        'next_sprints': open_sprints(),
    })

@user_passes_test(is_admin, login_url='login')
def sprint_form(request, pk=None):
    sprint = get_object_or_404(Sprint, pk=pk) if pk else None
    if request.method == 'POST':
        form = SprintForm(request.POST, instance=sprint)
        if form.is_valid():
            obj = form.save(commit=False)
            if not pk: obj.created_by = request.user
            obj.closed_at = timezone.now() if obj.state == Sprint.State.CLOSED and not obj.closed_at else (obj.closed_at if obj.state == Sprint.State.CLOSED else None)
            obj.save()
            messages.success(request, f'Sprint "{obj.name}" saved.')
            return redirect('sprints')
    else:
        if sprint: form = SprintForm(instance=sprint)
        else:
            last = Sprint.objects.order_by('-end_date').first()
            start = max(timezone.localdate(), last.end_date + timedelta(days=1)) if last else timezone.localdate()
            form = SprintForm(initial={'name': f'Sprint {Sprint.objects.count() + 1}', 'start_date': start, 'end_date': start + timedelta(days=13)})
    return render(request, 'tracker/simple_form.html', {'form': form, 'title': f'Edit {sprint}' if sprint else 'New sprint', 'back': reverse('sprints'), 'icon': 'directions_run'})

@user_passes_test(is_admin, login_url='login')
@require_POST
@transaction.atomic
def sprint_state(request, pk):
    sprint = get_object_or_404(Sprint, pk=pk)
    action = request.POST.get('action')
    if action == 'start':
        sprint.state, sprint.closed_at = Sprint.State.ACTIVE, None
        messages.success(request, f'{sprint.name} started. It is now on the home board.')
    elif action == 'close':
        target = request.POST.get('move_to', '')
        nxt = open_sprints().exclude(pk=sprint.pk).filter(pk=target).first() if target.isdigit() else None
        moved = sprint.tickets.exclude(status=Ticket.Status.COMPLETED).update(sprint=nxt)
        sprint.state, sprint.closed_at = Sprint.State.CLOSED, timezone.now()
        messages.success(request, f'{sprint.name} closed. {moved} unfinished task{"s" if moved != 1 else ""} moved to {nxt or "the backlog"}.')
    else:
        return HttpResponseBadRequest('Unknown action')
    sprint.save()
    return redirect('sprints')

# ---------------------------------------------------------------- categories

def can_manage_category(user, category):
    return user.is_staff or (category.team_id is not None and category.team_id == getattr(team_of(user), 'pk', None))

@login_required
def categories(request):
    groups = {}
    for cat in Category.objects.select_related('team', 'created_by').annotate(open_count=Count('tickets', filter=~Q(tickets__status=Ticket.Status.COMPLETED))):
        cat.editable = can_manage_category(request.user, cat)
        groups.setdefault(cat.team, []).append(cat)
    ordered = sorted(groups.items(), key=lambda kv: (kv[0] is not None, kv[0].name if kv[0] else ''))
    my_team = team_of(request.user)
    ordered.sort(key=lambda kv: kv[0] != my_team)  # the user's own team first
    return render(request, 'tracker/categories.html', {'groups': ordered, 'my_team': my_team})

@login_required
def category_form(request, pk=None):
    category = get_object_or_404(Category, pk=pk) if pk else None
    if category and not can_manage_category(request.user, category):
        return HttpResponseForbidden('You can only edit categories that belong to your team.')
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            if not pk: obj.created_by = request.user
            obj.save()
            messages.success(request, f'Category "{obj.name}" saved.')
            return redirect(safe_next(request, reverse('categories')))
    else:
        form = CategoryForm(instance=category, user=request.user)
    return render(request, 'tracker/simple_form.html', {'form': form, 'title': f'Edit {category.name}' if category else 'New category', 'back': reverse('categories'), 'icon': 'label'})

# ---------------------------------------------------------------- user administration

@user_passes_test(is_admin, login_url='login')
def users(request):
    people = User.objects.select_related('profile__team').order_by('-is_active', 'username').annotate(
        open_count=Count('assigned_tickets', filter=~Q(assigned_tickets__status=Ticket.Status.COMPLETED)))
    team = request.GET.get('team', '')
    if team == 'none': people = people.filter(Q(profile__isnull=True) | Q(profile__team__isnull=True))
    elif team.isdigit(): people = people.filter(profile__team_id=team)
    return render(request,'tracker/users.html',{'users':people,'teams':Team.objects.all(),'team_param':team})

@user_passes_test(is_admin, login_url='login')
def user_create(request):
    if request.method=='POST':
        form=AdminUserCreationForm(request.POST)
        if form.is_valid(): form.save(); messages.success(request,'Account created.'); return redirect('users')
    else: form=AdminUserCreationForm(initial={'team': request.GET.get('team')})
    return render(request,'tracker/user_form.html',{'form':form,'title':'Create account'})

@user_passes_test(is_admin, login_url='login')
@transaction.atomic
def user_edit(request, pk):
    target=get_object_or_404(User,pk=pk)
    profile, _ = Profile.objects.get_or_create(user=target)
    self_edit = target.pk == request.user.pk
    if request.method=='POST':
        form=UserEditForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            target.first_name = data['display_name']
            if not self_edit:  # admins cannot lock themselves out
                target.is_staff = data['role'] == 'Admin'
                target.is_active = data['is_active']
            target.save()
            profile.team = data['team']; profile.save()
            messages.success(request, f'{target.username} updated.')
            return redirect('users')
    else:
        form=UserEditForm(initial={'display_name': target.first_name or target.username, 'team': profile.team_id,
                                   'role': 'Admin' if target.is_staff else 'Member', 'is_active': target.is_active})
    if self_edit:
        form.fields['role'].disabled = form.fields['is_active'].disabled = True
        form.fields['role'].help_text = 'You cannot change your own access level or disable yourself.'
    return render(request,'tracker/user_form.html',{'form':form,'title':f'Edit {target.username}'})

@user_passes_test(is_admin, login_url='login')
def user_reset_password(request, pk):
    target=get_object_or_404(User,pk=pk)
    if target.pk==request.user.pk: return HttpResponseForbidden('Administrators may reset only another user from this screen.')
    if request.method=='POST':
        form=AdminPasswordResetForm(request.POST)
        if form.is_valid(): target.set_password(form.cleaned_data['password1']); target.save(update_fields=['password']); messages.success(request,'Password updated.'); return redirect('users')
    else: form=AdminPasswordResetForm()
    return render(request,'tracker/user_form.html',{'form':form,'title':f'Reset password: {target.username}'})

@user_passes_test(is_admin, login_url='login')
@require_POST
def user_toggle(request, pk, field):
    target=get_object_or_404(User,pk=pk)
    if target.pk==request.user.pk: return HttpResponseForbidden('Administrators cannot change their own access from this screen.')
    if field == 'active':
        target.is_active = not target.is_active
        target.save(update_fields=['is_active'])
        messages.success(request, f'{target.username} {"enabled" if target.is_active else "disabled"}.')
    else:
        target.is_staff = not target.is_staff
        target.save(update_fields=['is_staff'])
        messages.success(request, f'{target.username} is now {"an Admin" if target.is_staff else "a Member"}.')
    return redirect('users')

# ---------------------------------------------------------------- roles / teams

@user_passes_test(is_admin, login_url='login')
def teams(request):
    rows = Team.objects.annotate(
        member_count=Count('members', filter=Q(members__user__is_active=True), distinct=True),
        category_count=Count('categories', distinct=True),
        open_count=Count('tickets', filter=~Q(tickets__status=Ticket.Status.COMPLETED), distinct=True))
    return render(request, 'tracker/teams.html', {'teams': rows, 'unassigned': User.objects.filter(is_active=True).filter(Q(profile__isnull=True) | Q(profile__team__isnull=True)).count()})

@user_passes_test(is_admin, login_url='login')
def team_form(request, pk=None):
    team = get_object_or_404(Team, pk=pk) if pk else None
    if request.method == 'POST':
        form = TeamForm(request.POST, instance=team)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Role "{obj.name}" saved.')
            return redirect('teams')
    else:
        form = TeamForm(instance=team)
    return render(request, 'tracker/simple_form.html', {'form': form, 'title': f'Edit {team.name}' if team else 'New role', 'back': reverse('teams'), 'icon': 'badge'})
