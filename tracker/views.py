import csv
import re
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from .forms import AdminPasswordResetForm, AdminUserCreationForm, BulkUpdateForm, CommentForm, TicketEditForm, TicketForm
from .models import ProjectArea, Ticket, TicketHistory

User = get_user_model()
STATUS_ORDER = [Ticket.Status.BACKLOG, Ticket.Status.IN_PROGRESS, Ticket.Status.READY_TO_TEST, Ticket.Status.COMPLETED]
PRIORITY_ORDER = [Ticket.Priority.CRITICAL, Ticket.Priority.HIGH, Ticket.Priority.MEDIUM, Ticket.Priority.LOW]
BOARD_COMPLETED_LIMIT = 25
TICKET_NUMBER = re.compile(r'^(?:ACMI-?|#)?0*(\d{1,9})$', re.IGNORECASE)

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

def filtered_tickets(request):
    qs = Ticket.objects.select_related('area','submitted_by','assigned_to')
    g = request.GET
    q = g.get('q','').strip()
    if q:
        text = Q(title__icontains=q)|Q(description__icontains=q)|Q(area__name__icontains=q)|Q(submitted_by__username__icontains=q)|Q(assigned_to__username__icontains=q)|Q(assigned_to__first_name__icontains=q)
        number = TICKET_NUMBER.match(q)
        qs = qs.filter(text | Q(pk=int(number.group(1)))) if number else qs.filter(text)
    if g.get('status') in dict(Ticket.Status.choices): qs = qs.filter(status=g['status'])
    if g.get('open') == '1': qs = qs.exclude(status=Ticket.Status.COMPLETED)
    if g.get('priority') in dict(Ticket.Priority.choices): qs = qs.filter(priority=g['priority'])
    if g.get('area', '').isdigit(): qs = qs.filter(area_id=g['area'])
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

def common_context(request, qs):
    counts = dict(Ticket.objects.values_list('status').annotate(n=Count('id')).order_by())
    counts = {value: counts.get(value, 0) for value in STATUS_ORDER}
    return {
        'counts': counts, 'statuses': Ticket.Status.choices, 'priorities': Ticket.Priority.choices,
        'areas': ProjectArea.objects.filter(is_active=True),
        'submitters': User.objects.filter(submitted_tickets__isnull=False).distinct().order_by('username'),
        'assignees': User.objects.filter(is_active=True).order_by('first_name', 'username'),
        'filtered_count': qs.count(), 'total_count': sum(counts.values()), 'today': timezone.localdate(),
        'has_filters': any(request.GET.get(k) for k in ('q','status','priority','area','submitter','assignee','due','open')),
    }

# ---------------------------------------------------------------- views

@login_required
def board(request):
    qs = filtered_tickets(request).order_by(rank('priority', PRIORITY_ORDER), 'due_date', '-updated_at')
    columns = []
    for value, label in Ticket.Status.choices:
        items = qs.filter(status=value)
        hidden = 0
        if value == Ticket.Status.COMPLETED:
            total = items.count()
            items = list(items.order_by('-completed_at', '-updated_at')[:BOARD_COMPLETED_LIMIT])
            hidden = total - len(items)
        columns.append({'value': value, 'label': label, 'items': items, 'hidden': hidden})
    return render(request, 'tracker/board.html', common_context(request, qs) | {'columns': columns})

SORTS = {
    'number': ('id',), 'title': ('title',), 'status': (rank('status', STATUS_ORDER),), 'priority': (rank('priority', PRIORITY_ORDER),),
    'area': ('area__name',), 'assignee': ('assigned_to__first_name', 'assigned_to__username'), 'due': ('due_date',), 'updated': ('updated_at',),
}

SORT_COLUMNS = [('number','Ticket'),('title','Title'),('status','Status'),('priority','Priority'),('area','Area'),('assignee','Assigned to'),('due','Due'),('updated','Updated')]

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
    response['Content-Disposition'] = f'attachment; filename="tickets-{timezone.localdate():%Y%m%d}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Ticket','Title','Status','Priority','Area','Submitted by','Assigned to','Submitted','Due','Completed','Last updated','Description'])
    for t in qs:
        writer.writerow([t.ticket_number, t.title, t.get_status_display(), t.priority, t.area or 'Other', display_name(t.submitted_by),
                         display_name(t.assigned_to), timezone.localtime(t.submitted_at).strftime('%Y-%m-%d %H:%M'), t.due_date or '',
                         timezone.localtime(t.completed_at).strftime('%Y-%m-%d %H:%M') if t.completed_at else '',
                         timezone.localtime(t.updated_at).strftime('%Y-%m-%d %H:%M'), t.description])
    return response

@login_required
def my_work(request):
    today = timezone.localdate()
    mine = Ticket.objects.select_related('area','assigned_to').filter(assigned_to=request.user).exclude(status=Ticket.Status.COMPLETED)
    mine = mine.order_by(rank('priority', PRIORITY_ORDER), 'due_date', '-updated_at')
    attention = [t for t in mine if t.due_date and t.due_date <= today + timedelta(days=7)]
    groups = [(value, label, [t for t in mine if t.status == value]) for value, label in Ticket.Status.choices if value != Ticket.Status.COMPLETED]
    ready = Ticket.objects.select_related('area','assigned_to').filter(status=Ticket.Status.READY_TO_TEST).order_by(rank('priority', PRIORITY_ORDER), 'updated_at')[:10]
    activity = TicketHistory.objects.select_related('ticket','changed_by').order_by('-changed_at')[:15]
    month_ago = timezone.now() - timedelta(days=30)
    return render(request, 'tracker/my_work.html', {
        'today': today, 'attention': attention, 'groups': groups, 'ready': ready, 'activity': activity,
        'stats': {
            'open': len(mine), 'overdue': sum(1 for t in mine if t.due_date and t.due_date < today),
            'week': sum(1 for t in mine if t.due_date and today <= t.due_date <= today + timedelta(days=7)),
            'done': Ticket.objects.filter(assigned_to=request.user, status=Ticket.Status.COMPLETED, completed_at__gte=month_ago).count(),
            'submitted_open': Ticket.objects.filter(submitted_by=request.user).exclude(status=Ticket.Status.COMPLETED).count(),
        },
    })

@login_required
def insights(request):
    today = timezone.localdate()
    tickets = list(Ticket.objects.select_related('area','assigned_to').only('status','priority','area__name','assigned_to__username','assigned_to__first_name','assigned_to__last_name','submitted_at','completed_at','due_date'))
    total = len(tickets)
    status_counts = {value: 0 for value in STATUS_ORDER}
    areas, people = {}, {}
    for t in tickets:
        status_counts[t.status] = status_counts.get(t.status, 0) + 1
        area = areas.setdefault((t.area.name, t.area_id) if t.area else ('Other', None), {value: 0 for value in STATUS_ORDER})
        area[t.status] = area.get(t.status, 0) + 1
        if t.status != Ticket.Status.COMPLETED:
            person = people.setdefault(display_name(t.assigned_to), {'open': 0, 'overdue': 0, **{p: 0 for p in PRIORITY_ORDER}})
            person['open'] += 1
            person[t.priority] = person.get(t.priority, 0) + 1
            if t.due_date and t.due_date < today: person['overdue'] += 1
    def segments(counts):
        n = sum(counts.values()) or 1
        return [{'value': value, 'label': label, 'count': counts.get(value, 0), 'pct': round(counts.get(value, 0) * 100 / n, 1)} for value, label in Ticket.Status.choices]
    area_rows = sorted(({'name': name, 'id': area_id, 'total': sum(c.values()), 'done_pct': round(c[Ticket.Status.COMPLETED] * 100 / (sum(c.values()) or 1)), 'segments': segments(c)} for (name, area_id), c in areas.items()), key=lambda r: -r['total'])
    max_open = max((p['open'] for p in people.values()), default=1)
    people_rows = sorted(({'name': name, **p, 'bars': [{'priority': pr, 'count': p[pr], 'pct': p[pr] * 100 / max_open} for pr in PRIORITY_ORDER]} for name, p in people.items()), key=lambda r: -r['open'])

    start = today - timedelta(days=today.weekday() + 7 * 11)  # Monday, 12 weeks back
    weeks = [{'start': start + timedelta(weeks=i), 'created': 0, 'completed': 0} for i in range(12)]
    cycle_days = []
    for t in tickets:
        created = timezone.localtime(t.submitted_at).date()
        if created >= start: weeks[(created - start).days // 7]['created'] += 1
        if t.completed_at:
            done = timezone.localtime(t.completed_at).date()
            if done >= start: weeks[(done - start).days // 7]['completed'] += 1
            if done >= today - timedelta(days=90): cycle_days.append((t.completed_at - t.submitted_at).total_seconds() / 86400)
    peak = max((max(w['created'], w['completed']) for w in weeks), default=0) or 1
    for w in weeks: w['created_pct'], w['completed_pct'] = w['created'] * 100 / peak, w['completed'] * 100 / peak
    return render(request, 'tracker/insights.html', {
        'total': total, 'status_segments': segments(status_counts),
        'done_pct': round(status_counts[Ticket.Status.COMPLETED] * 100 / (total or 1)),
        'open_count': total - status_counts[Ticket.Status.COMPLETED],
        'overdue': sum(1 for t in tickets if t.due_date and t.due_date < today and t.status != Ticket.Status.COMPLETED),
        'unassigned': sum(1 for t in tickets if not t.assigned_to_id and t.status != Ticket.Status.COMPLETED),
        'cycle_time': round(sum(cycle_days) / len(cycle_days), 1) if cycle_days else None,
        'area_rows': area_rows, 'people_rows': people_rows, 'weeks': weeks, 'peak': peak,
        'completed_recent': sum(w['completed'] for w in weeks[-4:]),
    })

# ---------------------------------------------------------------- tickets

TRACKED_FIELDS = ['title', 'description', 'priority', 'area', 'assigned_to', 'due_date']

def field_text(ticket, field):
    value = getattr(ticket, field)
    if field == 'assigned_to': return display_name(value)
    if field == 'area': return str(value) if value else 'Other'
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
    """Move a ticket to a new workflow status, recording history. Caller saves."""
    old = ticket.status
    if old == new: return False
    ticket.status = new
    if new == Ticket.Status.COMPLETED: ticket.completed_at = timezone.now()
    else: ticket.completed_at = None
    TicketHistory.objects.create(ticket=ticket, changed_by=user, change_type='StatusChanged', old_value=old, new_value=new)
    return True

@login_required
@transaction.atomic
def ticket_create(request):
    if request.method == 'POST':
        form = TicketForm(request.POST)
        if form.is_valid():
            ticket=form.save(commit=False); ticket.submitted_by=request.user; ticket.save()
            TicketHistory.objects.create(ticket=ticket,changed_by=request.user,change_type='Created',new_value=Ticket.Status.BACKLOG)
            messages.success(request, f'{ticket.ticket_number} created.')
            if 'add_another' in request.POST:
                return redirect(f"{request.path}?area={ticket.area_id or ''}&priority={ticket.priority}")
            return redirect('ticket_detail', pk=ticket.pk)
    else:
        initial = {k: request.GET[k] for k in ('area', 'priority', 'assigned_to') if request.GET.get(k)}
        source = request.GET.get('from')
        if source and source.isdigit():
            original = Ticket.objects.filter(pk=source).first()
            if original:
                initial.update(title=f'Copy of {original.title}'[:200], description=original.description, priority=original.priority,
                               area=original.area_id, assigned_to=original.assigned_to_id)
        form=TicketForm(initial=initial)
    return render(request,'tracker/ticket_form.html',{'form':form,'title':'Create Ticket','creating':True})

@login_required
def ticket_detail(request, pk):
    ticket=get_object_or_404(Ticket.objects.select_related('area','submitted_by','assigned_to'),pk=pk)
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
        form=TicketEditForm(request.POST,instance=ticket)
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
    else: form=TicketEditForm(instance=ticket)
    return render(request,'tracker/ticket_form.html',{'form':form,'title':f'Edit {ticket.ticket_number}','ticket':ticket})

@login_required
@require_POST
@transaction.atomic
def ticket_move(request, pk):
    ticket=get_object_or_404(Ticket.objects.select_for_update(),pk=pk); new=request.POST.get('status')
    if new not in dict(Ticket.Status.choices): return HttpResponseBadRequest('Invalid status')
    if set_status(ticket, new, request.user): ticket.save()
    if wants_json(request):
        return JsonResponse({'ok': True, 'ticket': ticket.ticket_number, 'status': ticket.status, 'label': ticket.get_status_display()})
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
        messages.error(request, 'Select at least one ticket and a valid change.')
        return redirect(target)
    data = form.cleaned_data
    if not any([data['status'], data['priority'], data['area'], data['assigned_to']]):
        messages.info(request, 'Choose a field to change before applying.')
        return redirect(target)
    changed = 0
    for ticket in data['tickets'].select_related('area', 'assigned_to'):
        before, touched = snapshot(ticket), False
        if data['status']: touched = set_status(ticket, data['status'], request.user)
        if data['priority']: ticket.priority = data['priority']
        if data['area']: ticket.area = data['area']
        if data['assigned_to'] == 'none': ticket.assigned_to = None
        elif data['assigned_to']: ticket.assigned_to = data['assigned_to']
        ticket.save()
        if record_changes(ticket, request.user, before) or touched: changed += 1
    messages.success(request, f'{changed} ticket{"s" if changed != 1 else ""} updated.')
    return redirect(target)

@login_required
def logout_view(request): logout(request); return redirect('login')

# ---------------------------------------------------------------- user administration

@user_passes_test(is_admin, login_url='login')
def users(request):
    people = User.objects.order_by('-is_active', 'username').annotate(
        open_count=Count('assigned_tickets', filter=~Q(assigned_tickets__status=Ticket.Status.COMPLETED)))
    return render(request,'tracker/users.html',{'users':people})

@user_passes_test(is_admin, login_url='login')
def user_create(request):
    if request.method=='POST':
        form=AdminUserCreationForm(request.POST)
        if form.is_valid(): form.save(); messages.success(request,'Account created.'); return redirect('users')
    else: form=AdminUserCreationForm()
    return render(request,'tracker/user_form.html',{'form':form,'title':'Create Account'})

@user_passes_test(is_admin, login_url='login')
def user_reset_password(request, pk):
    target=get_object_or_404(User,pk=pk)
    if target.pk==request.user.pk: return HttpResponseForbidden('Administrators may reset only another user from this screen.')
    if request.method=='POST':
        form=AdminPasswordResetForm(request.POST)
        if form.is_valid(): target.set_password(form.cleaned_data['password1']); target.save(update_fields=['password']); messages.success(request,'Password updated.'); return redirect('users')
    else: form=AdminPasswordResetForm()
    return render(request,'tracker/user_form.html',{'form':form,'title':f'Reset Password: {target.username}'})

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
