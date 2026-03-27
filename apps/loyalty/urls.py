from django.urls import path
from apps.loyalty import views

app_name = 'loyalty'

urlpatterns = [
    path('',                          views.dashboard,    name='dashboard'),
    path('transactions/',             views.transactions, name='transactions'),
    path('badges/',                   views.badges,       name='badges'),
    path('rewards/',                  views.rewards,      name='rewards'),
    path('rewards/<int:reward_pk>/redeem/', views.redeem, name='redeem'),
]
