from django.urls import path
from . import views
urlpatterns = [
    path('login/', views.LocalLoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.board, name='board'),
    path('my-work/', views.my_work, name='my_work'),
    path('insights/', views.insights, name='insights'),
    path('backlog/', views.backlog, name='backlog'),
    path('backlog/export.csv', views.backlog_export, name='backlog_export'),
    path('tickets/new/', views.ticket_create, name='ticket_create'),
    path('tickets/bulk/', views.ticket_bulk, name='ticket_bulk'),
    path('tickets/<int:pk>/', views.ticket_detail, name='ticket_detail'),
    path('tickets/<int:pk>/edit/', views.ticket_edit, name='ticket_edit'),
    path('tickets/<int:pk>/move/', views.ticket_move, name='ticket_move'),
    path('tickets/<int:pk>/assign-me/', views.ticket_assign_me, name='ticket_assign_me'),
    path('users/', views.users, name='users'),
    path('users/new/', views.user_create, name='user_create'),
    path('users/<int:pk>/password/', views.user_reset_password, name='user_reset_password'),
    path('users/<int:pk>/toggle-active/', views.user_toggle, {'field': 'active'}, name='user_toggle_active'),
    path('users/<int:pk>/toggle-admin/', views.user_toggle, {'field': 'admin'}, name='user_toggle_admin'),
]
