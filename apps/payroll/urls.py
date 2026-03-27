from django.urls import path
from apps.payroll import views

app_name = 'payroll'

urlpatterns = [
    path('',                                views.period_list,       name='period_list'),
    path('<int:pk>/',                       views.period_detail,     name='period_detail'),
    path('<int:pk>/export/',                views.period_export_csv, name='period_export_csv'),
    path('rates/',                          views.rate_list,         name='rate_list'),
    path('rates/new/',                      views.rate_create,       name='rate_create'),
    path('rates/<int:pk>/edit/',            views.rate_edit,         name='rate_edit'),
    path('rates/staff/<int:staff_pk>/',     views.rate_history,      name='rate_history'),
]
