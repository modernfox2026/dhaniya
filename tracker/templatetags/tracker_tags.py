from django import template
from django.utils import timezone

from tracker.models import Ticket

register = template.Library()

STATUS_LABELS = dict(Ticket.Status.choices)


@register.filter
def get_item(mapping, key):
    if mapping is None:
        return 0

    return mapping.get(key, 0)


@register.filter
def status_class(value):
    status_classes = {
        "BACKLOG": "status-backlog",
        "IN_PROGRESS": "status-progress",
        "READY_TO_TEST": "status-testing",
        "COMPLETED": "status-completed",
    }

    return status_classes.get(value, "status-backlog")


@register.filter
def priority_class(value):
    priority_classes = {
        "Critical": "priority-critical",
        "High": "priority-high",
        "Medium": "priority-medium",
        "Low": "priority-low",
    }

    return priority_classes.get(value, "priority-low")


@register.filter
def status_label(value):
    """Turn a stored status code such as IN_PROGRESS into its display label."""
    return STATUS_LABELS.get(value, value)


@register.filter
def status_icon(value):
    icons = {
        "BACKLOG": "inbox",
        "IN_PROGRESS": "timer",
        "READY_TO_TEST": "task_alt",
        "COMPLETED": "check_circle",
    }

    return icons.get(value, "inbox")


@register.filter
def initials(user):
    if not user:
        return "?"

    name = user.get_full_name() or user.username
    parts = name.split()
    letters = (parts[0][:1] + parts[-1][:1]) if len(parts) > 1 else name[:1]
    return letters.upper()


@register.filter
def display_name(user):
    if not user:
        return "Unassigned"

    return user.get_full_name() or user.username


@register.filter
def due_state(ticket):
    """Return overdue, soon, or an empty string for a ticket's due date."""
    if not ticket.due_date or ticket.status == Ticket.Status.COMPLETED:
        return ""

    days = (ticket.due_date - timezone.localdate()).days
    if days < 0:
        return "overdue"
    if days <= 3:
        return "soon"
    return ""


@register.filter
def duration(seconds):
    """Compact work time such as 2d 3h, 4h 05m, or 12m."""
    if seconds is None:
        return ""

    minutes = int(seconds) // 60
    if minutes < 1:
        return "<1m"

    days, rest = divmod(minutes, 60 * 24)
    hours, mins = divmod(rest, 60)
    if days:
        return f"{days}d {hours}h" if hours else f"{days}d"
    if hours:
        return f"{hours}h {mins:02d}m"
    return f"{mins}m"


@register.filter
def team_style(team):
    """Inline CSS custom property for a team's color chip."""
    color = getattr(team, "color", "") or ""
    if len(color) == 7 and color.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in color[1:]):
        return f"--team: {color}"
    return ""


@register.simple_tag
def query(params, **changes):
    """Rebuild the current query string with some keys replaced or removed (value None or '')."""
    updated = params.copy()
    updated.pop("page", None)

    for key, value in changes.items():
        if value in (None, ""):
            updated.pop(key, None)
        else:
            updated[key] = value

    encoded = updated.urlencode()
    return f"?{encoded}" if encoded else "?"


@register.simple_tag
def toggle(params, key, value):
    """Query string that switches a quick filter on, or off when it is already active."""
    return query(params, **{key: None if params.get(key) == value else value})


@register.simple_tag
def sort_link(params, current, key):
    """Query string for a sortable column header: ascending first, then descending."""
    return query(params, sort=f"-{key}" if current == key else key)
