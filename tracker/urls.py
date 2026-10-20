from django.urls import path
from . import views
urlpatterns = [
    path('login/', views.LocalLoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.board, name='board'),
    path('backlog/', views.backlog, name='backlog'),
    path('tickets/new/', views.ticket_create, name='ticket_create'),
    path('tickets/<int:pk>/', views.ticket_detail, name='ticket_detail'),
    path('tickets/<int:pk>/edit/', views.ticket_edit, name='ticket_edit'),
    path('tickets/<int:pk>/move/', views.ticket_move, name='ticket_move'),
    path('users/', views.users, name='users'),
    path('users/new/', views.user_create, name='user_create'),
    path('users/<int:pk>/password/', views.user_reset_password, name='user_reset_password'),
]
