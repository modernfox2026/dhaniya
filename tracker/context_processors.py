from django.utils import timezone
from .models import Ticket


def navigation(request):
    """Badge counts shown in the navigation drawer."""
    if not request.user.is_authenticated:
        return {}
    open_tickets = Ticket.objects.exclude(status=Ticket.Status.COMPLETED)
    return {
        'nav_my_open': open_tickets.filter(assigned_to=request.user).count(),
        'nav_overdue': open_tickets.filter(due_date__lt=timezone.localdate()).count(),
    }
