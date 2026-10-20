from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from .forms import AdminPasswordResetForm, AdminUserCreationForm, CommentForm, TicketEditForm, TicketForm
from .models import ProjectArea, Ticket, TicketHistory

STATUS_ORDER = [Ticket.Status.BACKLOG, Ticket.Status.IN_PROGRESS, Ticket.Status.READY_TO_TEST, Ticket.Status.COMPLETED]
def is_admin(user): return user.is_authenticated and user.is_staff

class LocalLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

@login_required
def board(request):
    qs = filtered_tickets(request)
    columns = [(value, label, qs.filter(status=value)) for value, label in Ticket.Status.choices]
    return render(request, 'tracker/board.html', common_context(request, qs) | {'columns': columns})

@login_required
def backlog(request):
    qs = filtered_tickets(request)
    return render(request, 'tracker/backlog.html', common_context(request, qs) | {'tickets': qs})

def filtered_tickets(request):
    qs = Ticket.objects.select_related('area','submitted_by','assigned_to')
    q = request.GET.get('q','').strip()
    if q: qs = qs.filter(Q(title__icontains=q)|Q(description__icontains=q)|Q(area__name__icontains=q)|Q(submitted_by__username__icontains=q)|Q(assigned_to__username__icontains=q))
    if request.GET.get('status'): qs = qs.filter(status=request.GET['status'])
    if request.GET.get('priority'): qs = qs.filter(priority=request.GET['priority'])
    if request.GET.get('area'): qs = qs.filter(area_id=request.GET['area'])
    if request.GET.get('submitter'): qs = qs.filter(submitted_by_id=request.GET['submitter'])
    return qs

def common_context(request, qs):
    counts = {value: Ticket.objects.filter(status=value).count() for value, _ in Ticket.Status.choices}
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return {'counts':counts,'statuses':Ticket.Status.choices,'priorities':Ticket.Priority.choices,'areas':ProjectArea.objects.filter(is_active=True),'submitters':User.objects.filter(submitted_tickets__isnull=False).distinct().order_by('username'),'filtered_count':qs.count(),'total_count':Ticket.objects.count()}

@login_required
@transaction.atomic
def ticket_create(request):
    if request.method == 'POST':
        form = TicketForm(request.POST)
        if form.is_valid():
            ticket=form.save(commit=False); ticket.submitted_by=request.user; ticket.save()
            TicketHistory.objects.create(ticket=ticket,changed_by=request.user,change_type='Created',new_value=Ticket.Status.BACKLOG)
            messages.success(request, f'{ticket.ticket_number} created.')
            return redirect('backlog')
    else: form=TicketForm()
    return render(request,'tracker/ticket_form.html',{'form':form,'title':'Create Ticket'})

@login_required
def ticket_detail(request, pk):
    ticket=get_object_or_404(Ticket.objects.select_related('area','submitted_by','assigned_to'),pk=pk)
    if request.method=='POST':
        form=CommentForm(request.POST)
        if form.is_valid():
            obj=form.save(commit=False); obj.ticket=ticket; obj.created_by=request.user; obj.save()
            TicketHistory.objects.create(ticket=ticket,changed_by=request.user,change_type='CommentAdded',new_value=obj.text)
            return redirect('ticket_detail',pk=pk)
    else: form=CommentForm()
    return render(request,'tracker/ticket_detail.html',{'ticket':ticket,'comment_form':form})

@login_required
@transaction.atomic
def ticket_edit(request, pk):
    ticket=get_object_or_404(Ticket,pk=pk); old_status=ticket.status
    if request.method=='POST':
        form=TicketEditForm(request.POST,instance=ticket)
        if form.is_valid():
            updated=form.save(commit=False)
            updated.completed_at=timezone.now() if updated.status==Ticket.Status.COMPLETED else None
            updated.save()
            if old_status!=updated.status: TicketHistory.objects.create(ticket=updated,changed_by=request.user,change_type='StatusChanged',old_value=old_status,new_value=updated.status)
            else: TicketHistory.objects.create(ticket=updated,changed_by=request.user,change_type='Updated')
            messages.success(request,f'{updated.ticket_number} updated.')
            return redirect('ticket_detail',pk=pk)
    else: form=TicketEditForm(instance=ticket)
    return render(request,'tracker/ticket_form.html',{'form':form,'title':f'Edit {ticket.ticket_number}'})

@login_required
@require_POST
@transaction.atomic
def ticket_move(request, pk):
    ticket=get_object_or_404(Ticket,pk=pk); new=request.POST.get('status')
    if new not in dict(Ticket.Status.choices): return HttpResponseForbidden('Invalid status')
    old=ticket.status; ticket.status=new; ticket.completed_at=timezone.now() if new==Ticket.Status.COMPLETED else None; ticket.save()
    TicketHistory.objects.create(ticket=ticket,changed_by=request.user,change_type='StatusChanged',old_value=old,new_value=new)
    return redirect(request.POST.get('next') or 'board')

@login_required
def logout_view(request): logout(request); return redirect('login')

@user_passes_test(is_admin, login_url='login')
def users(request):
    from django.contrib.auth import get_user_model
    return render(request,'tracker/users.html',{'users':get_user_model().objects.order_by('username')})

@user_passes_test(is_admin, login_url='login')
def user_create(request):
    if request.method=='POST':
        form=AdminUserCreationForm(request.POST)
        if form.is_valid(): form.save(); messages.success(request,'Account created.'); return redirect('users')
    else: form=AdminUserCreationForm()
    return render(request,'tracker/user_form.html',{'form':form,'title':'Create Account'})

@user_passes_test(is_admin, login_url='login')
def user_reset_password(request, pk):
    from django.contrib.auth import get_user_model
    target=get_object_or_404(get_user_model(),pk=pk)
    if target.pk==request.user.pk: return HttpResponseForbidden('Administrators may reset only another user from this screen.')
    if request.method=='POST':
        form=AdminPasswordResetForm(request.POST)
        if form.is_valid(): target.set_password(form.cleaned_data['password1']); target.save(update_fields=['password']); messages.success(request,'Password updated.'); return redirect('users')
    else: form=AdminPasswordResetForm()
    return render(request,'tracker/user_form.html',{'form':form,'title':f'Reset Password: {target.username}'})
