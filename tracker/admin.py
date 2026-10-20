from django.contrib import admin
from .models import ProjectArea, Ticket, TicketComment, TicketHistory
admin.site.register(ProjectArea)
admin.site.register(Ticket)
admin.site.register(TicketComment)
admin.site.register(TicketHistory)
