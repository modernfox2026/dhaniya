from django.contrib import admin
from .models import Category, Profile, Sprint, Team, Ticket, TicketComment, TicketHistory
admin.site.register(Team)
admin.site.register(Profile)
admin.site.register(Category)
admin.site.register(Sprint)
admin.site.register(Ticket)
admin.site.register(TicketComment)
admin.site.register(TicketHistory)
