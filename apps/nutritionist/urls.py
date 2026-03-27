from django.urls import path
from apps.nutritionist import views

app_name = 'nutritionist'

urlpatterns = [
    path('',                                            views.client_list,        name='dashboard'),
    path('clients/',                                    views.client_list,        name='client_list'),
    path('clients/<int:member_pk>/',                    views.client_detail,      name='client_detail'),
    path('clients/<int:member_pk>/plan/',               views.plan_form,          name='plan_create'),
    path('clients/<int:member_pk>/plan/<int:plan_pk>/', views.plan_form,          name='plan_edit'),
    path('plans/',                                      views.plan_list,          name='plan_list'),
    path('supplements/<int:supplement_pk>/',            views.supplement_review,  name='supplement_review'),
    path('appointments/',                               views.appointments,       name='appointments'),
    path('appointments/<int:appointment_pk>/log/',      views.appointment_log,    name='appointment_log'),
]
