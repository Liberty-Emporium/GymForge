from django.urls import path
from . import views

app_name = 'landing'

urlpatterns = [
    path('', views.landing_page, name='home'),
    path('lead/', views.submit_lead, name='submit_lead'),
]
