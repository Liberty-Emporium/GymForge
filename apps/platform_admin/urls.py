from django.urls import path
from . import views

app_name = 'platform_admin'

urlpatterns = [
    path('',              views.dashboard,     name='dashboard'),
    path('gym/',          views.gym_detail,    name='gym_detail'),
    path('gym/suspend/',  views.gym_suspend,   name='gym_suspend'),
    path('gym/reactivate/', views.gym_reactivate, name='gym_reactivate'),
    path('audit-log/',    views.audit_log,     name='audit_log'),
]
