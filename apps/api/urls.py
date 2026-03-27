from django.urls import path

from . import views

app_name = 'api'

urlpatterns = [
    path('door/validate/', views.validate,    name='door_validate'),
    path('door/status/',   views.door_status, name='door_status'),
]
