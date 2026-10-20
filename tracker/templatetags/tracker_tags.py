from django import template

register = template.Library()


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
