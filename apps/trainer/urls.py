from django.urls import path
from apps.trainer import views

app_name = 'trainer'

urlpatterns = [
    path('', views.client_list, name='client_list'),
    path('clients/', views.client_list, name='clients'),
    path('clients/<int:member_pk>/', views.client_detail, name='client_detail'),
    path('clients/<int:member_pk>/generate-plan/', views.generate_plan, name='generate_plan'),
    path('workout-plans/', views.workout_plan_list, name='workout_plan_list'),
    path('workout-plans/<int:plan_pk>/review/', views.plan_review, name='plan_review'),
    path('appointments/', views.schedule, name='schedule'),
    path('appointments/<int:appointment_pk>/log/', views.session_log, name='session_log'),
]
