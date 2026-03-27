from django.urls import path
from apps.cleaner import views

app_name = 'cleaner'

urlpatterns = [
    path('',                            views.dashboard,      name='dashboard'),
    path('tasks/',                      views.task_list,      name='task_list'),
    path('tasks/<int:task_pk>/complete/', views.complete_task, name='complete_task'),
    path('equipment/',                  views.report_fault,   name='report_fault'),
    path('supplies/',                   views.supply_request, name='supply_request'),
    path('summary/',                    views.shift_summary,  name='shift_summary'),
]
